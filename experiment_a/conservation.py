from __future__ import annotations

import gzip
from pathlib import Path

import numpy as np
import pandas as pd


FLOW_TO_VPH = 12.0


def read_pems_station_flows(
    raw_dir: Path,
    dates: list[str],
    station_ids: set[int],
    period_start: str = "06:00",
    period_end: str = "10:00",
) -> pd.DataFrame:
    """Read selected PeMS station totals from daily station_5min files.

    PeMS total flow is vehicles per 5 minutes. Values are converted to veh/h.
    A cell is usable only when percent observed is positive and flow is present.
    """
    rows: list[dict] = []
    for date in dates:
        path = raw_dir / f"d12_text_station_5min_{date.replace('-', '_')}.txt.gz"
        if not path.exists():
            raise FileNotFoundError(f"Missing PeMS station file: {path}")
        with gzip.open(path, "rt") as source:
            for line in source:
                fields = line.rstrip("\n").split(",")
                try:
                    station_id = int(fields[1])
                except (IndexError, ValueError):
                    continue
                if station_id not in station_ids:
                    continue
                time_local = fields[0][11:16]
                if not period_start <= time_local < period_end:
                    continue
                try:
                    pct_observed = float(fields[8])
                except (IndexError, ValueError):
                    pct_observed = np.nan
                try:
                    raw_flow = float(fields[9])
                except (IndexError, ValueError):
                    raw_flow = np.nan
                usable = bool(
                    np.isfinite(pct_observed)
                    and pct_observed > 0
                    and np.isfinite(raw_flow)
                )
                rows.append({
                    "date_local": date,
                    "time_local": time_local,
                    "station_id": station_id,
                    "pct_observed": pct_observed,
                    "flow_vph": raw_flow * FLOW_TO_VPH if usable else np.nan,
                })
    result = pd.DataFrame(rows)
    if result.empty:
        raise ValueError("No selected PeMS station observations were found.")
    return result.sort_values(
        ["station_id", "date_local", "time_local"]
    ).reset_index(drop=True)


def maximum_rolling_hour(values: pd.Series, bins_per_hour: int = 12) -> float:
    values = pd.Series(values, dtype=float)
    rolling = values.rolling(bins_per_hour, min_periods=bins_per_hour).mean()
    return float(rolling.max()) if rolling.notna().any() else np.nan


def build_section_timeseries(
    station_flows: pd.DataFrame,
    sections: list[dict],
) -> pd.DataFrame:
    flow = station_flows.pivot(
        index=["date_local", "time_local"],
        columns="station_id",
        values="flow_vph",
    )
    observed = station_flows.pivot(
        index=["date_local", "time_local"],
        columns="station_id",
        values="pct_observed",
    )
    rows: list[pd.DataFrame] = []
    for section in sections:
        station_columns = [
            section["upstream_station_id"],
            section["on_ramp_station_id"],
            section["off_ramp_station_id"],
            section["downstream_station_id"],
        ]
        for station_id in station_columns:
            if station_id not in flow.columns:
                flow[station_id] = np.nan
                observed[station_id] = np.nan

        frame = flow[station_columns].copy()
        frame.columns = [
            "upstream_flow_vph", "on_ramp_flow_vph", "off_ramp_flow_vph",
            "downstream_flow_vph",
        ]
        frame = frame.reset_index()
        frame["link_id"] = section["link_id"]
        frame["upstream_station_id"] = section["upstream_station_id"]
        frame["on_ramp_station_id"] = section["on_ramp_station_id"]
        frame["off_ramp_station_id"] = section["off_ramp_station_id"]
        frame["downstream_station_id"] = section["downstream_station_id"]
        frame["upstream_plus_on_vph"] = (
            frame["upstream_flow_vph"] + frame["on_ramp_flow_vph"]
        )
        frame["conservation_arrival_vph"] = (
            frame["upstream_flow_vph"]
            + frame["on_ramp_flow_vph"]
            - frame["off_ramp_flow_vph"]
        )
        frame["conservation_minus_downstream_vph"] = (
            frame["conservation_arrival_vph"] - frame["downstream_flow_vph"]
        )
        section_observed = observed[station_columns].copy()
        frame["minimum_pct_observed"] = section_observed.min(axis=1).to_numpy()
        rows.append(frame)
    return pd.concat(rows, ignore_index=True).sort_values(
        ["link_id", "date_local", "time_local"]
    ).reset_index(drop=True)


def summarize_daily_demands(
    timeseries: pd.DataFrame,
    capacities: pd.Series,
    expected_bins: int = 48,
) -> pd.DataFrame:
    rows: list[dict] = []
    for (link_id, date), group in timeseries.groupby(
        ["link_id", "date_local"], sort=False
    ):
        group = group.sort_values("time_local")
        complete_upstream = bool(
            len(group) == expected_bins and group["upstream_flow_vph"].notna().all()
        )
        complete_on = bool(
            len(group) == expected_bins and group["on_ramp_flow_vph"].notna().all()
        )
        complete_off = bool(
            len(group) == expected_bins and group["off_ramp_flow_vph"].notna().all()
        )
        complete_conservation = complete_upstream and complete_on and complete_off
        capacity = float(capacities.loc[link_id])
        upstream = maximum_rolling_hour(group["upstream_flow_vph"])
        upstream_on = maximum_rolling_hour(group["upstream_plus_on_vph"])
        conservation = maximum_rolling_hour(group["conservation_arrival_vph"])
        rows.append({
            "link_id": link_id,
            "date_local": date,
            "capacity_vph_link": capacity,
            "complete_upstream": complete_upstream,
            "complete_on_ramp": complete_on,
            "complete_off_ramp": complete_off,
            "complete_conservation": complete_conservation,
            "upstream_D60_vph": upstream,
            "upstream_plus_on_D60_vph": upstream_on,
            "conservation_D60_vph": conservation,
            "upstream_dc": upstream / capacity if np.isfinite(upstream) else np.nan,
            "upstream_plus_on_dc": (
                upstream_on / capacity if np.isfinite(upstream_on) else np.nan
            ),
            "conservation_dc": (
                conservation / capacity if np.isfinite(conservation) else np.nan
            ),
        })
    return pd.DataFrame(rows).sort_values(
        ["link_id", "date_local"]
    ).reset_index(drop=True)


def closure_quality(timeseries: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for link_id, group in timeseries.groupby("link_id", sort=False):
        valid = group[
            ["conservation_arrival_vph", "downstream_flow_vph"]
        ].dropna()
        residual = (
            valid["conservation_arrival_vph"] - valid["downstream_flow_vph"]
        )
        rows.append({
            "link_id": link_id,
            "valid_5min_cells": int(len(valid)),
            "correlation_with_downstream": (
                float(valid.corr().iloc[0, 1]) if len(valid) > 1 else np.nan
            ),
            "mean_error_vph": float(residual.mean()) if len(valid) else np.nan,
            "mae_vph": float(residual.abs().mean()) if len(valid) else np.nan,
            "rmse_vph": (
                float(np.sqrt(np.mean(residual**2))) if len(valid) else np.nan
            ),
        })
    return pd.DataFrame(rows).sort_values("link_id").reset_index(drop=True)
