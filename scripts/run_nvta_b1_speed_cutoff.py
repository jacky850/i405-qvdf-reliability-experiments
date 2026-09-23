"""Compare B1 severe-congestion cutoffs at 0.50 and 0.25 of TMC free flow."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    from scripts.run_nvta_experiment_a import (
        detect_threshold_episodes,
        load_config,
        prepare_inputs,
    )
except ModuleNotFoundError:
    from run_nvta_experiment_a import (
        detect_threshold_episodes,
        load_config,
        prepare_inputs,
    )


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "nvta_b1_i95_nb_am_speed_ratio.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    return parser.parse_args()


def add_b1_fields(episodes: pd.DataFrame) -> pd.DataFrame:
    result = episodes.copy()
    result["uncensored_episode"] = (
        result["episode_identified"]
        & ~result["touches_data_start"]
        & ~result["touches_data_end"]
    )
    result["congested_link_mile_hours"] = np.where(
        result["uncensored_episode"],
        result["duration_h"] * result["length_mi"],
        0.0,
    )
    result["qualifying_link_miles"] = np.where(
        result["uncensored_episode"], result["length_mi"], 0.0
    )
    return result


def aggregate_daily(episodes: pd.DataFrame) -> pd.DataFrame:
    group_columns = [
        "corridor",
        "facility",
        "date_local",
        "threshold_multiplier",
        "threshold_speed_ratio_to_vf",
    ]
    daily = (
        episodes.groupby(group_columns, as_index=False)
        .agg(
            total_tmc_count=("tmc_code", "nunique"),
            total_link_miles=("length_mi", "sum"),
            qualifying_tmc_count=("uncensored_episode", "sum"),
            qualifying_link_miles=("qualifying_link_miles", "sum"),
            congested_link_mile_hours=("congested_link_mile_hours", "sum"),
        )
    )
    daily["qualifying_tmc_share"] = (
        daily["qualifying_tmc_count"] / daily["total_tmc_count"]
    )

    combined_columns = [
        "date_local",
        "threshold_multiplier",
        "threshold_speed_ratio_to_vf",
    ]
    combined = (
        daily.groupby(combined_columns, as_index=False)
        .agg(
            total_tmc_count=("total_tmc_count", "sum"),
            total_link_miles=("total_link_miles", "sum"),
            qualifying_tmc_count=("qualifying_tmc_count", "sum"),
            qualifying_link_miles=("qualifying_link_miles", "sum"),
            congested_link_mile_hours=("congested_link_mile_hours", "sum"),
        )
    )
    combined.insert(0, "facility", "ALL")
    combined.insert(0, "corridor", "I-95 NB combined")
    combined["qualifying_tmc_share"] = (
        combined["qualifying_tmc_count"] / combined["total_tmc_count"]
    )
    return pd.concat([daily, combined], ignore_index=True).sort_values(
        ["corridor", "threshold_multiplier", "date_local"]
    )


def summarize(episodes: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    scopes = [
        (corridor, facility, group)
        for (corridor, facility), group in episodes.groupby(["corridor", "facility"])
    ]
    scopes.append(("I-95 NB combined", "ALL", episodes))

    for corridor, facility, scope in scopes:
        scope_daily = daily[
            (daily["corridor"] == corridor) & (daily["facility"] == facility)
        ]
        for ratio, group in scope.groupby("threshold_speed_ratio_to_vf", sort=True):
            day_group = scope_daily[np.isclose(scope_daily["threshold_speed_ratio_to_vf"], ratio)]
            qualifying = group[group["uncensored_episode"]]
            rows.append(
                {
                    "corridor": corridor,
                    "facility": facility,
                    "threshold_speed_ratio_to_vf": float(ratio),
                    "median_threshold_speed_mph": float(group["threshold_speed_mph"].median()),
                    "weekday_dates": int(group["date_local"].nunique()),
                    "tmcs": int(group["tmc_code"].nunique()),
                    "tmc_days": int(len(group)),
                    "qualifying_tmc_days": int(group["uncensored_episode"].sum()),
                    "qualifying_tmc_day_share": float(group["uncensored_episode"].mean()),
                    "qualifying_tmcs": int(qualifying["tmc_code"].nunique()),
                    "censored_episode_tmc_days": int(
                        (group["episode_identified"] & ~group["uncensored_episode"]).sum()
                    ),
                    "median_episode_duration_h": (
                        float(qualifying["duration_h"].median()) if len(qualifying) else np.nan
                    ),
                    "total_congested_link_mile_hours": float(
                        day_group["congested_link_mile_hours"].sum()
                    ),
                    "mean_daily_congested_link_mile_hours": float(
                        day_group["congested_link_mile_hours"].mean()
                    ),
                    "median_daily_congested_link_mile_hours": float(
                        day_group["congested_link_mile_hours"].median()
                    ),
                    "maximum_daily_congested_link_mile_hours": float(
                        day_group["congested_link_mile_hours"].max()
                    ),
                }
            )

    summary = pd.DataFrame(rows)
    summary["mean_daily_reduction_vs_050_percent"] = np.nan
    for (corridor, facility), group in summary.groupby(["corridor", "facility"]):
        baseline = group[np.isclose(group["threshold_speed_ratio_to_vf"], 0.50)]
        if baseline.empty or baseline.iloc[0]["mean_daily_congested_link_mile_hours"] == 0:
            continue
        mask = (summary["corridor"] == corridor) & (summary["facility"] == facility)
        baseline_value = float(baseline.iloc[0]["mean_daily_congested_link_mile_hours"])
        summary.loc[mask, "mean_daily_reduction_vs_050_percent"] = (
            1.0
            - summary.loc[mask, "mean_daily_congested_link_mile_hours"] / baseline_value
        ) * 100.0
    return summary.sort_values(["corridor", "threshold_speed_ratio_to_vf"])


def make_figure(summary: pd.DataFrame, output: Path) -> None:
    combined = summary[summary["facility"] == "ALL"].sort_values(
        "threshold_speed_ratio_to_vf"
    )
    facility = summary[summary["facility"].isin(["GP", "HOV"])].copy()
    ratios = sorted(summary["threshold_speed_ratio_to_vf"].unique())
    labels = [f"{ratio:.2f} $v_f$" for ratio in ratios]

    figure, axes = plt.subplots(1, 2, figsize=(9.2, 4.0), constrained_layout=True)
    axes[0].bar(
        labels,
        combined["mean_daily_congested_link_mile_hours"],
        color=["#d95f02", "#1f77b4"],
    )
    axes[0].set_ylabel("Mean daily congested link-mile-hours")
    axes[0].set_title("Combined I-95 Northbound")

    colors = {"GP": "#1f77b4", "HOV": "#2a9d8f"}
    x = np.arange(len(ratios))
    width = 0.34
    for offset, label in zip([-width / 2, width / 2], ["GP", "HOV"]):
        values = (
            facility[facility["facility"] == label]
            .set_index("threshold_speed_ratio_to_vf")
            .reindex(ratios)["qualifying_tmc_day_share"]
            * 100.0
        )
        axes[1].bar(x + offset, values, width, label=label, color=colors[label])
    axes[1].set_xticks(x, labels)
    axes[1].set_ylabel("Qualifying TMC-days (%)")
    axes[1].set_title("Frequency by facility")
    axes[1].legend(frameon=False)

    for axis in axes:
        axis.grid(axis="y", color="#d9d9d9", linewidth=0.8)
        axis.set_axisbelow(True)
        axis.spines[["top", "right"]].set_visible(False)
    figure.suptitle("I-95 Northbound AM severe-congestion cutoff test", fontsize=14)
    figure.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    results_dir = ROOT / "results"
    figures_dir = ROOT / "figures"
    results_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    _, data, _ = prepare_inputs(config)
    episodes = add_b1_fields(detect_threshold_episodes(data, config))
    daily = aggregate_daily(episodes)
    summary = summarize(episodes, daily)

    episodes.to_csv(results_dir / "nvta_b1_speed_cutoff_episodes.csv", index=False)
    daily.to_csv(results_dir / "nvta_b1_speed_cutoff_daily_metrics.csv", index=False)
    summary.to_csv(results_dir / "nvta_b1_speed_cutoff_summary.csv", index=False)
    make_figure(summary, figures_dir / "nvta_b1_speed_cutoff_sensitivity.png")

    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
