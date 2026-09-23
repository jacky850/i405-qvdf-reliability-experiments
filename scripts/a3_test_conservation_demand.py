#!/usr/bin/env python3
"""Test upstream and ramp-conservation demand proxies on Experiment A."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiment_a.conservation import (
    build_section_timeseries,
    closure_quality,
    read_pems_station_flows,
    summarize_daily_demands,
)
from experiment_a.core import fit_power_curve, load_config


SECTIONS = [
    {
        "link_id": "L405S-132",
        "upstream_station_id": 1222286,
        "on_ramp_station_id": 1201711,
        "off_ramp_station_id": 1201715,
        "downstream_station_id": 1222749,
        "interchange": "Magnolia 1",
    },
    {
        "link_id": "L405S-115",
        "upstream_station_id": 1222804,
        "on_ramp_station_id": 1201757,
        "off_ramp_station_id": 1201763,
        "downstream_station_id": 1222327,
        "interchange": "Edinger",
    },
    {
        "link_id": "L405S-114",
        "upstream_station_id": 1222327,
        "on_ramp_station_id": 1201793,
        "off_ramp_station_id": 1201797,
        "downstream_station_id": 1201805,
        "interchange": "Beach 1",
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=ROOT / "raw_data" / "station_5min",
        help="Directory containing d12_text_station_5min_YYYY_MM_DD.txt.gz files.",
    )
    return parser.parse_args()


def fit_rows(
    data: pd.DataFrame,
    config: dict,
    sample_name: str,
    columns: list[tuple[str, str]],
) -> tuple[list[dict], list[dict]]:
    summaries: list[dict] = []
    predictions: list[dict] = []
    for threshold, group in data.groupby("threshold_multiplier"):
        for basis, column in columns:
            sample = group.loc[np.isfinite(group[column])].copy()
            fit = fit_power_curve(
                sample[column].to_numpy(float),
                sample["duration_h"].to_numpy(float),
                config,
            )
            summaries.append({
                "sample": sample_name,
                "demand_basis": basis,
                "x_column": column,
                "threshold_multiplier": float(threshold),
                "observations": int(len(sample)),
                "links": int(sample["link_id"].nunique()),
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
                    "sample": sample_name,
                    "demand_basis": basis,
                    "threshold_multiplier": float(threshold),
                    "link_id": row["link_id"],
                    "date_local": row["date_local"],
                    "dc_ratio": row[column],
                    "duration_h": row["duration_h"],
                    "predicted_duration_h": predicted,
                })
    return summaries, predictions


def make_figure(summary: pd.DataFrame, predictions: pd.DataFrame, output: Path) -> None:
    bases = [
        ("original_link_throughput", "Original link throughput"),
        ("upstream_mainline", "Upstream mainline"),
        ("upstream_plus_on", "Upstream + on-ramp"),
        ("upstream_plus_on_minus_off", "Upstream + on - off"),
    ]
    selected = predictions[
        predictions["sample"].eq("matched_complete_conservation")
        & np.isclose(predictions["threshold_multiplier"], 1.0)
    ]
    diagnostics = summary[
        summary["sample"].eq("matched_complete_conservation")
        & np.isclose(summary["threshold_multiplier"], 1.0)
    ].set_index("demand_basis")

    figure, axes = plt.subplots(2, 2, figsize=(10, 8), sharey=True)
    for axis, (basis, title) in zip(axes.flat, bases):
        group = selected[selected["demand_basis"].eq(basis)]
        axis.scatter(
            group["dc_ratio"], group["duration_h"],
            color="#1769aa", s=28, alpha=0.75,
        )
        order = np.argsort(group["dc_ratio"].to_numpy())
        axis.plot(
            group["dc_ratio"].to_numpy()[order],
            group["predicted_duration_h"].to_numpy()[order],
            color="#c62828", linewidth=1.8,
        )
        row = diagnostics.loc[basis]
        axis.set_title(
            f"{title}\n$R^2$={row.r_squared:.3f}, "
            f"Spearman={row.spearman_rho:.3f}",
            fontsize=11,
        )
        axis.set_xlabel("Dimensionless peak-hour D/C")
        axis.grid(alpha=0.2)
    axes[0, 0].set_ylabel("Congestion duration P (hours)")
    axes[1, 0].set_ylabel("Congestion duration P (hours)")
    figure.suptitle(
        "Internal diagnostic: upstream and ramp-conservation demand proxies\n"
        "Matched complete sections, threshold = 1.00 × capacity speed",
        fontsize=14,
    )
    figure.tight_layout()
    figure.savefig(output, dpi=220, bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    args = parse_args()
    config = load_config(ROOT)
    results_dir = ROOT / "results"
    figures_dir = ROOT / "figures"
    data_dir = ROOT / "data"
    results_dir.mkdir(exist_ok=True)
    figures_dir.mkdir(exist_ok=True)
    data_dir.mkdir(exist_ok=True)

    dates = sorted(
        pd.read_csv(results_dir / "step2_daily_demand.csv")["date_local"]
        .astype(str)
        .unique()
        .tolist()
    )
    station_ids = {
        int(section[key])
        for section in SECTIONS
        for key in (
            "upstream_station_id", "on_ramp_station_id",
            "off_ramp_station_id", "downstream_station_id",
        )
    }
    station_flows = read_pems_station_flows(
        args.raw_dir,
        dates,
        station_ids,
        period_start="06:00",
        period_end="10:00",
    )
    timeseries = build_section_timeseries(station_flows, SECTIONS)
    timeseries.to_csv(
        data_dir / "i405s_pems_am_15_weekdays_conservation_5min.csv.gz",
        index=False,
        compression="gzip",
        float_format="%.6f",
    )

    section_map = pd.DataFrame(SECTIONS)
    section_map.to_csv(results_dir / "a3_conservation_section_map.csv", index=False)

    station_coverage = (
        station_flows.groupby("station_id", as_index=False)
        .agg(
            rows=("time_local", "size"),
            dates=("date_local", "nunique"),
            usable_cells=("flow_vph", "count"),
            minimum_pct_observed=("pct_observed", "min"),
            median_pct_observed=("pct_observed", "median"),
        )
    )
    station_coverage["usable_fraction"] = (
        station_coverage["usable_cells"] / station_coverage["rows"]
    )
    station_coverage.to_csv(
        results_dir / "a3_conservation_station_coverage.csv", index=False
    )

    capacities = pd.read_csv(
        results_dir / "step1_link_parameters.csv"
    ).set_index("link_id")["capacity_vph_link"]
    daily = summarize_daily_demands(timeseries, capacities)
    original = pd.read_csv(results_dir / "step2_daily_demand.csv")[[
        "link_id", "date_local", "demand_capacity_ratio"
    ]].rename(columns={"demand_capacity_ratio": "original_link_dc"})
    daily = daily.merge(
        original, on=["link_id", "date_local"], how="left", validate="one_to_one"
    )
    daily.to_csv(results_dir / "a3_conservation_link_day.csv", index=False)

    closure = closure_quality(timeseries)
    closure.to_csv(results_dir / "a3_conservation_closure_quality.csv", index=False)

    episodes = pd.read_csv(results_dir / "step3_threshold_episodes.csv")
    support = pd.read_csv(results_dir / "step3_common_support.csv")
    keys = support.loc[support["common_support"], ["link_id", "date_local"]]
    fit_data = (
        episodes.merge(keys, on=["link_id", "date_local"], how="inner")
        .merge(daily, on=["link_id", "date_local"], how="left")
    )
    complete_keys = daily.loc[
        daily["complete_conservation"], ["link_id", "date_local"]
    ]
    matched = fit_data.merge(
        complete_keys, on=["link_id", "date_local"], how="inner"
    )

    summaries, predictions = fit_rows(
        fit_data,
        config,
        "all_common_support",
        [("original_link_throughput", "demand_capacity_ratio")],
    )
    matched_summary, matched_predictions = fit_rows(
        matched,
        config,
        "matched_complete_conservation",
        [
            ("original_link_throughput", "demand_capacity_ratio"),
            ("upstream_mainline", "upstream_dc"),
            ("upstream_plus_on", "upstream_plus_on_dc"),
            ("upstream_plus_on_minus_off", "conservation_dc"),
        ],
    )
    summaries.extend(matched_summary)
    predictions.extend(matched_predictions)
    fit_summary = pd.DataFrame(summaries)
    fit_predictions = pd.DataFrame(predictions)
    fit_summary.to_csv(
        results_dir / "a3_conservation_fit_summary.csv",
        index=False,
        float_format="%.6f",
    )
    fit_predictions.to_csv(
        results_dir / "a3_conservation_fit_predictions.csv",
        index=False,
        float_format="%.6f",
    )

    make_figure(
        fit_summary,
        fit_predictions,
        figures_dir / "a3_conservation_internal_diagnostic.png",
    )

    at_capacity = fit_summary[
        fit_summary["sample"].eq("matched_complete_conservation")
        & np.isclose(fit_summary["threshold_multiplier"], 1.0)
    ].set_index("demand_basis")
    incomplete_stations = set(
        station_coverage.loc[
            station_coverage["usable_fraction"].lt(1.0), "station_id"
        ].astype(int)
    )
    incomplete_sections = []
    for section in SECTIONS:
        missing_roles = [
            role
            for role, key in (
                ("upstream", "upstream_station_id"),
                ("on_ramp", "on_ramp_station_id"),
                ("off_ramp", "off_ramp_station_id"),
            )
            if int(section[key]) in incomplete_stations
        ]
        if missing_roles:
            incomplete_sections.append({
                "link_id": section["link_id"],
                "unusable_roles": missing_roles,
            })
    verdict = {
        "dataset": "Caltrans PeMS",
        "scope": "I-405 South, AM 06:00-10:00, 15 weekdays",
        "common_support_link_days": int(len(keys)),
        "complete_conservation_link_days": int(len(complete_keys)),
        "complete_conservation_links": sorted(
            complete_keys["link_id"].unique().tolist()
        ),
        "incomplete_sections": incomplete_sections,
        "threshold_1p00_r_squared": {
            basis: float(at_capacity.loc[basis, "r_squared"])
            for basis in at_capacity.index
        },
        "threshold_1p00_spearman": {
            basis: float(at_capacity.loc[basis, "spearman_rho"])
            for basis in at_capacity.index
        },
        "conclusion": (
            "Upstream and ramp-conservation proxies do not remove the negative "
            "duration relationship on this minimum sample. The complete "
            "conservation estimate remains a diagnostic, not a validated demand "
            "measure."
        ),
    }
    (results_dir / "a3_conservation_summary.json").write_text(
        json.dumps(verdict, indent=2) + "\n", encoding="utf-8"
    )

    print(fit_summary[
        fit_summary["sample"].eq("matched_complete_conservation")
        & np.isclose(fit_summary["threshold_multiplier"], 1.0)
    ][[
        "demand_basis", "observations", "links", "fd_h", "n",
        "r_squared", "pearson_r", "spearman_rho",
    ]].to_string(index=False))
    print("\nClosure quality:")
    print(closure.to_string(index=False))
    print("\n", verdict["conclusion"])


if __name__ == "__main__":
    main()
