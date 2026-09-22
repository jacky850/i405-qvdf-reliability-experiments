#!/usr/bin/env python3
"""Prepare the strict 100-weekday PeMS detector-day D/C sample."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiment_b.core import KMH_TO_MPH, detector_day_peaks, select_weekdays


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path, default=ROOT / "config" / "experiment_b.json"
    )
    return parser.parse_args()


def read_cell_quality(path: Path, selected_dates: set[str], start: str, end: str) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    for chunk in pd.read_csv(
        path,
        usecols=["station_id", "timestamp", "pct_observed"],
        dtype={"station_id": "int64", "timestamp": "string", "pct_observed": "float32"},
        chunksize=1_000_000,
    ):
        dates = chunk["timestamp"].str.slice(0, 10)
        times = chunk["timestamp"].str.slice(11, 16)
        keep = dates.isin(selected_dates) & times.ge(start) & times.lt(end)
        if keep.any():
            parts.append(chunk.loc[keep])
    if not parts:
        return pd.DataFrame(columns=["station_id", "timestamp", "pct_observed"])
    return pd.concat(parts, ignore_index=True)


def read_detector_states(path: Path, selected_dates: set[str], start: str, end: str) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    columns = [
        "date", "timestamp", "station_id", "link_id", "milepost", "direction",
        "speed", "flow",
    ]
    dtypes = {
        "date": "string", "timestamp": "string", "station_id": "int64",
        "link_id": "string", "milepost": "float64", "direction": "string",
        "speed": "float64", "flow": "float64",
    }
    for chunk in pd.read_csv(path, usecols=columns, dtype=dtypes, chunksize=1_000_000):
        times = chunk["timestamp"].str.slice(11, 16)
        keep = chunk["date"].isin(selected_dates) & times.ge(start) & times.lt(end)
        if keep.any():
            parts.append(chunk.loc[keep])
    if not parts:
        raise ValueError("No detector rows matched the configured dates and AM period.")
    return pd.concat(parts, ignore_index=True)


def main() -> None:
    args = parse_args()
    config = json.loads(args.config.read_text())
    source_paths = {
        key: Path(config[key]).expanduser()
        for key in (
            "source_detector_states",
            "source_cell_quality",
            "source_station_metadata",
        )
    }
    source_paths = {
        key: path if path.is_absolute() else ROOT / path
        for key, path in source_paths.items()
    }
    missing_sources = [str(path) for path in source_paths.values() if not path.exists()]
    if missing_sources:
        raise FileNotFoundError(
            "Experiment B1 requires the original PeMS source files. Missing: "
            + ", ".join(missing_sources)
        )
    dates = select_weekdays(
        config["sample_start"], config["sample_end"],
        int(config["number_of_weekdays"]), config["excluded_dates"],
    )
    selected_dates = set(dates)

    quality = read_cell_quality(
        source_paths["source_cell_quality"], selected_dates,
        config["period_start"], config["period_end"],
    )
    states = read_detector_states(
        source_paths["source_detector_states"], selected_dates,
        config["period_start"], config["period_end"],
    )
    states = states.merge(
        quality, on=["station_id", "timestamp"], how="left", validate="one_to_one"
    )
    # The quality file is sparse: an absent key means 100% observed.
    states["pct_observed"] = states["pct_observed"].fillna(100.0)
    strict = states.loc[
        states["pct_observed"].eq(float(config["required_pct_observed"]))
    ].copy()

    metadata = pd.read_csv(
        source_paths["source_station_metadata"], sep="\t",
        usecols=["ID", "Fwy", "Dir", "Type", "Lanes", "Name"],
    )
    metadata = metadata.loc[
        metadata["Fwy"].eq(405)
        & metadata["Dir"].eq("S")
        & metadata["Type"].eq("ML")
    ].rename(columns={"ID": "station_id", "Lanes": "lanes", "Name": "station_name"})
    strict = strict.merge(
        metadata[["station_id", "lanes", "station_name"]],
        on="station_id", how="inner", validate="many_to_one",
    )

    # Estimate one corridor-wide empirical per-lane capacity before applying
    # the complete-day availability screen. A station-specific P95 would
    # mechanically force every station's D/C close to one and erase the
    # between-station loading range needed by Experiment B.
    strict["flow_vph_per_lane"] = strict["flow"] / strict["lanes"]
    capacity_per_lane_vph = float(
        strict["flow_vph_per_lane"].quantile(float(config["capacity_percentile"]))
    )
    capacity_pool = strict[
        ["station_id", "link_id", "date", "timestamp", "lanes", "flow", "flow_vph_per_lane"]
    ].copy()

    expected_bins = int(
        (pd.Timestamp(config["period_end"]) - pd.Timestamp(config["period_start"]))
        / pd.Timedelta(minutes=int(config["resolution_minutes"]))
    )
    station_day_bins = strict.groupby(["station_id", "date"]).size()
    complete = station_day_bins.loc[station_day_bins.eq(expected_bins)].reset_index()[
        ["station_id", "date"]
    ]
    complete_days = complete.groupby("station_id").size()
    eligible_stations = complete_days.loc[
        complete_days.ge(int(config["minimum_complete_days_per_detector"]))
    ].index
    strict = strict.loc[strict["station_id"].isin(eligible_stations)].merge(
        complete, on=["station_id", "date"], how="inner", validate="many_to_one"
    )

    strict["timestamp_local"] = strict["timestamp"].str.rstrip("Z")
    strict["date_local"] = strict["date"]
    strict["time_local"] = strict["timestamp"].str.slice(11, 16)
    strict["speed_mph"] = strict["speed"] * KMH_TO_MPH
    strict["flow_vph_link"] = strict["flow"]
    strict["capacity_per_lane_vph"] = capacity_per_lane_vph
    strict["C_vph_link"] = strict["lanes"] * strict["capacity_per_lane_vph"]
    strict = strict.sort_values(["station_id", "date_local", "timestamp_local"])

    free_speed = strict.groupby("station_id")["speed_mph"].quantile(0.95)
    peaks = detector_day_peaks(
        strict,
        capacity_per_lane_vph=capacity_per_lane_vph,
        resolution_minutes=int(config["resolution_minutes"]),
    )
    peaks["free_flow_speed_p95_mph"] = peaks["station_id"].map(free_speed)
    peaks["peak_window_tti"] = (
        peaks["free_flow_speed_p95_mph"] / peaks["peak_window_harmonic_speed_mph"]
    )
    peaks["within_dc_analysis_range"] = peaks["dc_ratio"].between(
        float(config["dc_analysis_min"]), float(config["dc_analysis_max"]),
        inclusive="both",
    )

    results = ROOT / "results"
    data = ROOT / "data"
    results.mkdir(exist_ok=True)
    data.mkdir(exist_ok=True)

    sample_dates = pd.DataFrame({"date_local": dates})
    sample_dates["excluded_holiday"] = False
    sample_dates.to_csv(results / "b1_sample_dates.csv", index=False)

    capacity_pool.rename(
        columns={
            "date": "date_local",
            "timestamp": "timestamp_source_local_wall_clock",
            "flow": "flow_vph_link",
        }
    ).to_csv(
        data / "i405s_pems_am_100_weekdays_capacity_pool.csv.gz",
        index=False,
        compression="gzip",
    )

    five_min_columns = [
        "station_id", "link_id", "station_name", "milepost", "direction", "lanes",
        "timestamp_local", "date_local", "time_local", "pct_observed", "speed_mph",
        "flow_vph_link", "capacity_per_lane_vph", "C_vph_link",
    ]
    strict[five_min_columns].to_csv(
        data / "i405s_pems_am_100_weekdays_detector_5min.csv.gz",
        index=False, compression="gzip",
    )

    peak_columns = [
        "station_id", "link_id", "station_name", "milepost", "direction", "lanes",
        "date_local", "peak_window_start_local", "peak_window_end_local",
        "D_vph_link", "C_vph_link", "dc_ratio", "ln_dc",
        "free_flow_speed_p95_mph", "peak_window_harmonic_speed_mph",
        "peak_window_tti", "within_dc_analysis_range",
    ]
    peaks[peak_columns].sort_values(["station_id", "date_local"]).to_csv(
        results / "b1_detector_day_dc.csv", index=False
    )

    inventory = (
        peaks.groupby(
            ["station_id", "link_id", "station_name", "milepost", "direction", "lanes"],
            as_index=False,
        )
        .agg(
            complete_days=("date_local", "size"),
            mean_dc=("dc_ratio", "mean"),
            min_dc=("dc_ratio", "min"),
            max_dc=("dc_ratio", "max"),
            mu_ln_dc=("ln_dc", "mean"),
            sigma_ln_dc=("ln_dc", "std"),
            free_flow_speed_p95_mph=("free_flow_speed_p95_mph", "first"),
        )
        .sort_values("milepost")
    )
    inventory["capacity_per_lane_vph"] = capacity_per_lane_vph
    inventory["C_vph_link"] = inventory["lanes"] * inventory["capacity_per_lane_vph"]
    inventory.to_csv(results / "b1_detector_inventory.csv", index=False)

    summary = {
        "dataset": "Caltrans PeMS",
        "corridor": config["corridor"],
        "period": f"{config['period_start']}-{config['period_end']}",
        "selected_weekdays": len(dates),
        "retained_unique_dates": int(peaks["date_local"].nunique()),
        "dates_without_any_retained_detector_day": sorted(
            selected_dates - set(peaks["date_local"].astype(str))
        ),
        "first_date": dates[0],
        "last_date": dates[-1],
        "excluded_dates": config["excluded_dates"],
        "strict_quality_rule": "all 48 AM bins have pct_observed = 100",
        "minimum_complete_days_per_detector": int(config["minimum_complete_days_per_detector"]),
        "eligible_detectors": int(inventory["station_id"].nunique()),
        "represented_network_links": int(inventory["link_id"].nunique()),
        "detector_days": int(len(peaks)),
        "five_min_rows": int(len(strict)),
        "mean_dc_min_across_detectors": float(inventory["mean_dc"].min()),
        "mean_dc_max_across_detectors": float(inventory["mean_dc"].max()),
        "sigma_ln_dc_min": float(inventory["sigma_ln_dc"].min()),
        "sigma_ln_dc_max": float(inventory["sigma_ln_dc"].max()),
        "detector_days_in_0p4_to_1p3": int(peaks["within_dc_analysis_range"].sum()),
        "capacity_percentile": float(config["capacity_percentile"]),
        "capacity_pool": config["capacity_pool"],
        "capacity_pool_cells": int(len(capacity_pool)),
        "capacity_pool_detectors": int(capacity_pool["station_id"].nunique()),
        "capacity_per_lane_vph": capacity_per_lane_vph,
        "capacity_definition": "C = pooled PeMS P95 flow per lane times PeMS station lane count",
    }
    (results / "b1_data_quality_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
