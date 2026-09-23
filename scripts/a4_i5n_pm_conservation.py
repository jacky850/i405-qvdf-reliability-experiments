#!/usr/bin/env python3
"""Run the I-5 North PM ramp-conservation QVDF diagnostic."""

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

from experiment_a.i5n_conservation import (
    build_segment_definitions,
    closure_summary,
    detect_durations,
    fit_demand_bases,
    load_i5_config,
    load_selected_timeseries,
    summarize_link_days,
)


DEFAULT_SOURCE = Path(
    "/Users/jinxiwu/Library/CloudStorage/Dropbox-ASU/Jinxi Wu/IEEE Big Data/"
    "I210E_corridor_data_package/multicorridor_2026_pilot/"
    "trafficflowbench_five_corridors/data_public/kaggle_release/"
    "corridors/D12_I5_N"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE)
    return parser.parse_args()


def make_figure(summary: pd.DataFrame, predictions: pd.DataFrame, output: Path) -> None:
    bases = [
        ("downstream_throughput", "Downstream throughput"),
        ("upstream_mainline", "Upstream mainline"),
        ("upstream_plus_on_minus_off", "Upstream + on - off"),
        ("downstream_plus_storage", "Downstream + storage change"),
    ]
    selected = predictions[np.isclose(predictions["threshold_multiplier"], 1.0)]
    diagnostics = summary[
        np.isclose(summary["threshold_multiplier"], 1.0)
    ].set_index("demand_basis")
    figure, axes = plt.subplots(2, 2, figsize=(10, 8), sharey=True)
    for axis, (basis, title) in zip(axes.flat, bases):
        group = selected[selected["demand_basis"].eq(basis)]
        axis.scatter(group["dc_ratio"], group["duration_h"], s=28, alpha=0.75)
        order = np.argsort(group["dc_ratio"].to_numpy())
        axis.plot(
            group["dc_ratio"].to_numpy()[order],
            group["predicted_duration_h"].to_numpy()[order],
            color="#c62828", linewidth=1.8,
        )
        row = diagnostics.loc[basis]
        axis.set_title(
            f"{title}\n$R^2$={row.r_squared:.3f}, "
            f"Spearman={row.spearman_rho:.3f}, $n$={row.n:.3f}"
        )
        axis.set_xlabel("Dimensionless peak-hour D/C")
        axis.grid(alpha=0.2)
    axes[0, 0].set_ylabel("Congestion duration P (hours)")
    axes[1, 0].set_ylabel("Congestion duration P (hours)")
    figure.suptitle(
        "I-5 North PM: ramp conservation and storage diagnostic\n"
        "15 weekdays, threshold = 1.00 × capacity speed"
    )
    figure.tight_layout()
    figure.savefig(output, dpi=220, bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    args = parse_args()
    config = load_i5_config(ROOT)
    segments = build_segment_definitions(args.source_root, config)
    timeseries = load_selected_timeseries(args.source_root, config, segments)
    link_days = summarize_link_days(timeseries, config)
    durations = detect_durations(timeseries, config)
    fits, predictions = fit_demand_bases(durations, link_days, config)
    closure = closure_summary(timeseries)

    results = ROOT / "results"
    figures = ROOT / "figures"
    results.mkdir(exist_ok=True)
    figures.mkdir(exist_ok=True)
    segment_rows = []
    for segment in segments:
        segment_rows.append({
            **{
                key: value for key, value in segment.items()
                if key not in {
                    "on_ramp_station_ids", "off_ramp_station_ids",
                    "mainline_path_links",
                }
            },
            "on_ramp_station_ids": ";".join(segment["on_ramp_station_ids"]),
            "off_ramp_station_ids": ";".join(segment["off_ramp_station_ids"]),
            "mainline_path_links": ";".join(segment["mainline_path_links"]),
        })
    pd.DataFrame(segment_rows).to_csv(
        results / "a4_i5n_pm_segment_map.csv", index=False
    )
    link_days.to_csv(results / "a4_i5n_pm_link_day.csv", index=False)
    durations.to_csv(results / "a4_i5n_pm_durations.csv", index=False)
    fits.to_csv(results / "a4_i5n_pm_fit_summary.csv", index=False)
    predictions.to_csv(results / "a4_i5n_pm_fit_predictions.csv", index=False)
    closure.to_csv(results / "a4_i5n_pm_closure_summary.csv", index=False)
    make_figure(
        fits, predictions, figures / "a4_i5n_pm_conservation_diagnostic.png"
    )

    one = fits[np.isclose(fits["threshold_multiplier"], 1.0)].copy()
    verdict = {
        "corridor": config["corridor_id"],
        "period": f"{config['period_start']}-{config['period_end']}",
        "date_range": [config["sample_start_date"], config["sample_end_date"]],
        "weekdays": int(config["expected_weekdays"]),
        "segments": [segment["segment_id"] for segment in segments],
        "joint_coverage_min": float(link_days["joint_coverage"].min()),
        "common_support_link_days": int(
            durations.groupby(["segment_id", "date_local"])[
                "episode_identified"
            ].all().sum()
        ),
        "threshold_1_fit": one.set_index("demand_basis")[[
            "observations", "fd_h", "n", "r_squared", "rmse_h",
            "spearman_rho", "n_at_boundary",
        ]].to_dict(orient="index"),
        "storage_density_method": config["storage_density_method"],
        "raw_data_exported": False,
    }
    with (results / "a4_i5n_pm_summary.json").open("w", encoding="utf-8") as out:
        json.dump(verdict, out, indent=2)

    print("Selected segments:")
    print(pd.DataFrame(segment_rows).to_string(index=False))
    print("\nClosure quality:")
    print(closure.to_string(index=False))
    print("\nQVDF comparison at threshold 1.00 × capacity speed:")
    print(one[[
        "demand_basis", "observations", "fd_h", "n", "r_squared",
        "rmse_h", "spearman_rho", "n_at_boundary",
    ]].to_string(index=False))


if __name__ == "__main__":
    main()
