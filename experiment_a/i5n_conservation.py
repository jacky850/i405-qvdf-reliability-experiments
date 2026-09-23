from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from experiment_a.core import _qualifying_runs, fit_power_curve


def load_i5_config(repo_root: Path) -> dict:
    path = repo_root / "config" / "experiment_a_i5n_pm.json"
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def split_link_ids(value: object) -> list[str]:
    if pd.isna(value) or not str(value).strip():
        return []
    return [item for item in str(value).split(";") if item]


def build_segment_definitions(source_root: Path, config: dict) -> list[dict]:
    network = source_root / "network"
    topology = pd.read_csv(network / "lwr_sensor_topology.csv").sort_values(
        "segment_index"
    )
    ramps = pd.read_csv(
        network / "ramp_control_map.csv", dtype={"station_id": str}
    )
    fd = pd.read_csv(
        network / "fd_parameters.csv", dtype={"station_id": str}
    ).set_index("station_id")

    selected = set(int(value) for value in config["segment_indices"])
    rows: list[dict] = []
    for _, row in topology[topology["segment_index"].isin(selected)].iterrows():
        path_links = split_link_ids(row["mainline_path_links"])
        attached = ramps[ramps["nearest_mainline_link_id"].isin(path_links)]
        downstream = str(int(row["downstream_detector"]))
        upstream = str(int(row["upstream_detector"]))
        rows.append({
            "segment_id": f"I5N-S{int(row['segment_index']):02d}",
            "segment_index": int(row["segment_index"]),
            "upstream_station_id": upstream,
            "downstream_station_id": downstream,
            "on_ramp_station_ids": attached.loc[
                attached["ramp_type"].eq("OR"), "station_id"
            ].astype(str).tolist(),
            "off_ramp_station_ids": attached.loc[
                attached["ramp_type"].eq("FR"), "station_id"
            ].astype(str).tolist(),
            "mainline_path_links": path_links,
            "length_km": float(row["length_km"]),
            "capacity_vph_link": float(fd.loc[downstream, "capacity_vph"]),
            "capacity_speed_kmh": float(fd.loc[downstream, "v_cut"]),
        })
    rows.sort(key=lambda item: item["segment_index"])
    if [row["segment_index"] for row in rows] != sorted(selected):
        raise ValueError("Not all configured I-5 sensor segments were found")
    return rows


def sample_weekdays(config: dict) -> list[str]:
    dates = pd.date_range(
        config["sample_start_date"], config["sample_end_date"], freq="B"
    )
    result = dates.strftime("%Y-%m-%d").tolist()
    if len(result) != int(config["expected_weekdays"]):
        raise ValueError(
            f"Expected {config['expected_weekdays']} weekdays, found {len(result)}"
        )
    return result


def _daily_path(source_root: Path, kind: str, date: str) -> Path:
    month = date[:7]
    token = date.replace("-", "_")
    path = (
        source_root / "train" / kind / f"year_month={month}"
        / f"d12_text_station_5min_{token}.parquet"
    )
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def _station_matrix(
    frame: pd.DataFrame, value: str, station_ids: list[str], times: pd.Index
) -> pd.DataFrame:
    matrix = frame.pivot(index="time_local", columns="station_id", values=value)
    return matrix.reindex(index=times, columns=station_ids)


def load_selected_timeseries(
    source_root: Path, config: dict, segments: list[dict]
) -> pd.DataFrame:
    threshold = float(config["minimum_pct_observed"])
    start, end = config["period_start"], config["period_end"]
    mainline_ids = sorted({
        station
        for segment in segments
        for station in (
            segment["upstream_station_id"], segment["downstream_station_id"]
        )
    })
    ramp_ids = sorted({
        station
        for segment in segments
        for station in (
            segment["on_ramp_station_ids"] + segment["off_ramp_station_ids"]
        )
    })

    pieces: list[pd.DataFrame] = []
    for date in sample_weekdays(config):
        mainline = pd.read_parquet(
            _daily_path(source_root, "mainline_states", date),
            columns=[
                "timestamp", "station_id", "speed_kmh", "flow_vph",
                "density_occ_linear_vehpkm", "pct_observed",
            ],
        )
        ramps = pd.read_parquet(
            _daily_path(source_root, "ramp_states", date),
            columns=["timestamp", "station_id", "flow_vph", "pct_observed"],
        )
        mainline["station_id"] = mainline["station_id"].astype(str)
        ramps["station_id"] = ramps["station_id"].astype(str)
        mainline["time_local"] = mainline["timestamp"].str.slice(11, 16)
        ramps["time_local"] = ramps["timestamp"].str.slice(11, 16)
        mainline = mainline[
            mainline["station_id"].isin(mainline_ids)
            & mainline["time_local"].ge(start)
            & mainline["time_local"].lt(end)
        ].copy()
        ramps = ramps[
            ramps["station_id"].isin(ramp_ids)
            & ramps["time_local"].ge(start)
            & ramps["time_local"].lt(end)
        ].copy()

        times = pd.Index(sorted(mainline["time_local"].unique()), name="time_local")
        if len(times) != 48:
            raise ValueError(f"Expected 48 PM bins on {date}, found {len(times)}")
        ml_flow = _station_matrix(mainline, "flow_vph", mainline_ids, times)
        ml_speed = _station_matrix(mainline, "speed_kmh", mainline_ids, times)
        ml_density = _station_matrix(
            mainline, "density_occ_linear_vehpkm", mainline_ids, times
        )
        ml_pct = _station_matrix(mainline, "pct_observed", mainline_ids, times)
        ramp_flow = _station_matrix(ramps, "flow_vph", ramp_ids, times)
        ramp_pct = _station_matrix(ramps, "pct_observed", ramp_ids, times)

        for segment in segments:
            up = segment["upstream_station_id"]
            down = segment["downstream_station_id"]
            on_ids = segment["on_ramp_station_ids"]
            off_ids = segment["off_ramp_station_ids"]
            required_pct = pd.concat(
                [
                    ml_pct[[up, down]],
                    ramp_pct[on_ids + off_ids] if on_ids + off_ids
                    else pd.DataFrame(index=times),
                ], axis=1,
            )
            valid = required_pct.ge(threshold).all(axis=1)
            valid &= ml_flow[[up, down]].notna().all(axis=1)
            valid &= ml_speed[[up, down]].notna().all(axis=1)
            valid &= ml_density[[up, down]].notna().all(axis=1)
            if on_ids + off_ids:
                valid &= ramp_flow[on_ids + off_ids].notna().all(axis=1)

            on_flow = (
                ramp_flow[on_ids].sum(axis=1, min_count=len(on_ids))
                if on_ids else pd.Series(0.0, index=times)
            )
            off_flow = (
                ramp_flow[off_ids].sum(axis=1, min_count=len(off_ids))
                if off_ids else pd.Series(0.0, index=times)
            )
            frame = pd.DataFrame({
                "date_local": date,
                "time_local": times,
                "segment_id": segment["segment_id"],
                "segment_index": segment["segment_index"],
                "upstream_flow_vph": ml_flow[up].to_numpy(),
                "downstream_flow_vph": ml_flow[down].to_numpy(),
                "on_ramp_flow_vph": on_flow.to_numpy(),
                "off_ramp_flow_vph": off_flow.to_numpy(),
                "upstream_density_vehpkm": ml_density[up].to_numpy(),
                "downstream_density_vehpkm": ml_density[down].to_numpy(),
                "downstream_speed_kmh": ml_speed[down].to_numpy(),
                "minimum_pct_observed": required_pct.min(axis=1).to_numpy(),
                "valid_joint_cell": valid.to_numpy(),
                "length_km": segment["length_km"],
                "capacity_vph_link": segment["capacity_vph_link"],
                "capacity_speed_kmh": segment["capacity_speed_kmh"],
                "on_ramp_count": len(on_ids),
                "off_ramp_count": len(off_ids),
            })
            frame["timestamp_local"] = pd.to_datetime(
                frame["date_local"] + " " + frame["time_local"]
            )
            pieces.append(frame)

    result = pd.concat(pieces, ignore_index=True).sort_values(
        ["segment_index", "timestamp_local"]
    ).reset_index(drop=True)
    result.loc[~result["valid_joint_cell"], [
        "upstream_flow_vph", "downstream_flow_vph", "on_ramp_flow_vph",
        "off_ramp_flow_vph", "upstream_density_vehpkm",
        "downstream_density_vehpkm", "downstream_speed_kmh",
    ]] = np.nan
    return add_conservation_terms(result, float(config["bin_hours"]))


def add_conservation_terms(frame: pd.DataFrame, bin_hours: float) -> pd.DataFrame:
    result = frame.copy()
    result["net_arrival_vph"] = (
        result["upstream_flow_vph"] + result["on_ramp_flow_vph"]
        - result["off_ramp_flow_vph"]
    )
    result["stored_vehicles"] = 0.5 * (
        result["upstream_density_vehpkm"]
        + result["downstream_density_vehpkm"]
    ) * result["length_km"]
    result["storage_change_vph"] = (
        result.groupby(["segment_id", "date_local"], sort=False)[
            "stored_vehicles"
        ].shift(-1) - result["stored_vehicles"]
    ) / bin_hours
    result["storage_implied_arrival_vph"] = (
        result["downstream_flow_vph"] + result["storage_change_vph"]
    )
    result["residual_no_storage_vph"] = (
        result["net_arrival_vph"] - result["downstream_flow_vph"]
    )
    result["residual_with_storage_vph"] = (
        result["net_arrival_vph"] - result["storage_implied_arrival_vph"]
    )
    return result


def maximum_rolling_mean(values: pd.Series, bins: int) -> float:
    rolling = pd.Series(values, dtype=float).rolling(bins, min_periods=bins).mean()
    return float(rolling.max()) if rolling.notna().any() else np.nan


def summarize_link_days(frame: pd.DataFrame, config: dict) -> pd.DataFrame:
    bins = int(config["demand_window_bins"])
    rows: list[dict] = []
    demand_columns = {
        "downstream": "downstream_flow_vph",
        "upstream": "upstream_flow_vph",
        "net_arrival": "net_arrival_vph",
        "storage_implied_arrival": "storage_implied_arrival_vph",
    }
    for (segment, date), group in frame.groupby(
        ["segment_id", "date_local"], sort=False
    ):
        group = group.sort_values("timestamp_local")
        first = group.iloc[0]
        row = {
            "segment_id": segment,
            "segment_index": int(first["segment_index"]),
            "date_local": date,
            "valid_joint_cells": int(group["valid_joint_cell"].sum()),
            "joint_coverage": float(group["valid_joint_cell"].mean()),
            "capacity_vph_link": float(first["capacity_vph_link"]),
            "capacity_speed_kmh": float(first["capacity_speed_kmh"]),
        }
        capacity = row["capacity_vph_link"]
        for label, column in demand_columns.items():
            demand = maximum_rolling_mean(group[column], bins)
            row[f"{label}_D60_vph"] = demand
            row[f"{label}_dc"] = demand / capacity
        rows.append(row)
    return pd.DataFrame(rows).sort_values(
        ["segment_index", "date_local"]
    ).reset_index(drop=True)


def detect_durations(frame: pd.DataFrame, config: dict) -> pd.DataFrame:
    smooth_bins = int(config["smoothing_bins"])
    minimum_bins = int(config["minimum_episode_bins"])
    bin_hours = float(config["bin_hours"])
    rows: list[dict] = []
    for (segment, date), group in frame.groupby(
        ["segment_id", "date_local"], sort=False
    ):
        group = group.sort_values("timestamp_local").reset_index(drop=True)
        speed = group["downstream_speed_kmh"].rolling(
            smooth_bins, center=True, min_periods=1
        ).median()
        capacity_speed = float(group.iloc[0]["capacity_speed_kmh"])
        for multiplier in config["speed_threshold_multipliers"]:
            threshold = float(multiplier) * capacity_speed
            runs = _qualifying_runs(speed.le(threshold).to_numpy(), minimum_bins)
            if runs:
                start, end = max(
                    runs,
                    key=lambda run: (
                        run[1] - run[0] + 1,
                        -float(speed.iloc[run[0]:run[1] + 1].min()),
                        -run[0],
                    ),
                )
                duration_bins = end - start + 1
            else:
                start = end = None
                duration_bins = 0
            rows.append({
                "segment_id": segment,
                "segment_index": int(group.iloc[0]["segment_index"]),
                "date_local": date,
                "threshold_multiplier": float(multiplier),
                "threshold_speed_kmh": threshold,
                "episode_identified": bool(runs),
                "duration_bins": int(duration_bins),
                "duration_h": float(duration_bins * bin_hours),
                "episode_start_local": (
                    group.iloc[start]["timestamp_local"].isoformat()
                    if start is not None else ""
                ),
                "episode_end_local": (
                    (group.iloc[end]["timestamp_local"] + pd.Timedelta(minutes=5))
                    .isoformat() if end is not None else ""
                ),
            })
    return pd.DataFrame(rows).sort_values(
        ["threshold_multiplier", "segment_index", "date_local"]
    ).reset_index(drop=True)


def fit_demand_bases(
    durations: pd.DataFrame, link_days: pd.DataFrame, config: dict
) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = durations.merge(
        link_days, on=["segment_id", "segment_index", "date_local"],
        how="left", validate="many_to_one",
    )
    support = data.groupby(["segment_id", "date_local"])[
        "episode_identified"
    ].all()
    keys = support[support].reset_index()[["segment_id", "date_local"]]
    data = data.merge(keys, on=["segment_id", "date_local"], how="inner")
    bases = {
        "downstream_throughput": "downstream_dc",
        "upstream_mainline": "upstream_dc",
        "upstream_plus_on_minus_off": "net_arrival_dc",
        "downstream_plus_storage": "storage_implied_arrival_dc",
    }
    summaries: list[dict] = []
    predictions: list[dict] = []
    for multiplier, threshold_data in data.groupby("threshold_multiplier"):
        for label, column in bases.items():
            sample = threshold_data[np.isfinite(threshold_data[column])].copy()
            fit = fit_power_curve(
                sample[column].to_numpy(float),
                sample["duration_h"].to_numpy(float),
                config,
            )
            summaries.append({
                "demand_basis": label,
                "x_column": column,
                "threshold_multiplier": float(multiplier),
                "observations": int(len(sample)),
                "segments": int(sample["segment_id"].nunique()),
                "fd_h": fit["fd_h"],
                "n": fit["n"],
                "r_squared": fit["r_squared"],
                "rmse_h": fit["rmse_h"],
                "pearson_r": sample[column].corr(sample["duration_h"]),
                "spearman_rho": sample[column].corr(
                    sample["duration_h"], method="spearman"
                ),
                "n_at_boundary": fit["n_at_boundary"],
            })
            for (_, row), predicted in zip(sample.iterrows(), fit["predicted"]):
                predictions.append({
                    "demand_basis": label,
                    "threshold_multiplier": float(multiplier),
                    "segment_id": row["segment_id"],
                    "date_local": row["date_local"],
                    "dc_ratio": row[column],
                    "duration_h": row["duration_h"],
                    "predicted_duration_h": predicted,
                })
    return pd.DataFrame(summaries), pd.DataFrame(predictions)


def closure_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for segment, group in frame.groupby("segment_id", sort=False):
        raw = group[["net_arrival_vph", "downstream_flow_vph"]].dropna()
        stored = group[[
            "net_arrival_vph", "storage_implied_arrival_vph",
            "residual_with_storage_vph",
        ]].dropna()
        raw_residual = raw["net_arrival_vph"] - raw["downstream_flow_vph"]
        rows.append({
            "segment_id": segment,
            "valid_raw_cells": int(len(raw)),
            "valid_storage_cells": int(len(stored)),
            "raw_correlation": raw.corr().iloc[0, 1],
            "raw_bias_vph": raw_residual.mean(),
            "raw_mae_vph": raw_residual.abs().mean(),
            "raw_rmse_vph": np.sqrt(np.mean(raw_residual**2)),
            "storage_correlation": stored[
                ["net_arrival_vph", "storage_implied_arrival_vph"]
            ].corr().iloc[0, 1],
            "storage_bias_vph": stored["residual_with_storage_vph"].mean(),
            "storage_mae_vph": stored["residual_with_storage_vph"].abs().mean(),
            "storage_rmse_vph": np.sqrt(
                np.mean(stored["residual_with_storage_vph"]**2)
            ),
        })
    return pd.DataFrame(rows)
