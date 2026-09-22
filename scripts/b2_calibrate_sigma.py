#!/usr/bin/env python3
"""Estimate day-to-day sigma[ln(D/C)] and select a simple sigma model."""

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

from experiment_b.core import fit_sigma_models, normal_qq_r2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path, default=ROOT / "config" / "experiment_b.json"
    )
    return parser.parse_args()


def detector_statistics(detector_days: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    identity = ["link_id", "station_name", "milepost", "direction", "lanes", "C_vph_link"]
    for station_id, group in detector_days.groupby("station_id"):
        log_values = group["ln_dc"].to_numpy(float)
        dc_values = group["dc_ratio"].to_numpy(float)
        row: dict[str, object] = {
            "station_id": int(station_id),
            **{column: group[column].iloc[0] for column in identity},
            "detector_days": len(group),
            "mean_dc": float(dc_values.mean()),
            "median_dc": float(np.median(dc_values)),
            "min_dc": float(dc_values.min()),
            "max_dc": float(dc_values.max()),
            "mu_ln_dc": float(log_values.mean()),
            "sigma_ln_dc": float(log_values.std(ddof=1)),
            "skew_ln_dc": float(pd.Series(log_values).skew()),
            "excess_kurtosis_ln_dc": float(pd.Series(log_values).kurt()),
            "normal_qq_r2": normal_qq_r2(log_values),
        }
        row["lognormal_mean_dc"] = float(
            np.exp(row["mu_ln_dc"] + 0.5 * row["sigma_ln_dc"] ** 2)
        )
        row["lognormal_p95_dc"] = float(
            np.exp(row["mu_ln_dc"] + 1.6448536269514722 * row["sigma_ln_dc"])
        )
        rows.append(row)
    return pd.DataFrame(rows).sort_values("mean_dc")


def binned_statistics(stats: pd.DataFrame, lower: float, upper: float, width: float) -> pd.DataFrame:
    edges = np.round(np.arange(lower, upper + width / 2, width), 10)
    labels = [f"{edges[index]:.1f}-{edges[index + 1]:.1f}" for index in range(len(edges) - 1)]
    work = stats.copy()
    work["dc_bin"] = pd.cut(
        work["mean_dc"], bins=edges, labels=labels, right=False, include_lowest=True
    )
    output = (
        work.groupby("dc_bin", observed=False)
        .agg(
            detector_count=("station_id", "size"),
            detector_days=("detector_days", "sum"),
            mean_dc=("mean_dc", "mean"),
            mean_mu_ln_dc=("mu_ln_dc", "mean"),
            mean_sigma_ln_dc=("sigma_ln_dc", "mean"),
            min_sigma_ln_dc=("sigma_ln_dc", "min"),
            max_sigma_ln_dc=("sigma_ln_dc", "max"),
        )
        .reset_index()
    )
    output.insert(1, "dc_bin_lower", edges[:-1])
    output.insert(2, "dc_bin_upper", edges[1:])
    return output


def choose_model(comparison: pd.DataFrame, threshold: float) -> tuple[str, str]:
    ordered = comparison.sort_values(["aicc", "parameter_count"])
    best = ordered.iloc[0]
    constant = comparison.loc[comparison["model"].eq("constant")].iloc[0]
    if float(constant["aicc"] - best["aicc"]) <= threshold:
        return "constant", (
            f"Constant selected by parsimony because its AICc is within {threshold:g} "
            "of the minimum."
        )
    return str(best["model"]), "Model with the minimum AICc selected."


def make_figure(
    stats: pd.DataFrame,
    comparison: pd.DataFrame,
    selected_model: str,
    lower: float,
    upper: float,
    output: Path,
) -> None:
    x_grid = np.linspace(lower, upper, 400)
    constant = comparison.set_index("model").loc["constant"]
    linear = comparison.set_index("model").loc["linear"]
    empirical_min = float(stats["mean_dc"].min())
    empirical_max = float(stats["mean_dc"].max())

    fig, axis = plt.subplots(figsize=(9.2, 5.3))
    axis.axvspan(lower, empirical_min, color="#f1f5f9", zorder=0)
    axis.axvspan(empirical_max, upper, color="#f1f5f9", zorder=0, label="Extrapolation")
    axis.scatter(
        stats["mean_dc"], stats["sigma_ln_dc"], s=55,
        color="#2563eb", edgecolor="white", linewidth=0.7,
        label=f"PeMS detectors (n={len(stats)})", zorder=3,
    )
    axis.plot(
        x_grid, np.full_like(x_grid, constant["intercept"]),
        color="#0f766e", linewidth=2.4,
        label=f"Selected constant: sigma = {constant['intercept']:.4f}",
        zorder=2,
    )
    axis.plot(
        x_grid, linear["intercept"] + linear["slope"] * x_grid,
        color="#64748b", linewidth=1.6, linestyle="--",
        label="Linear alternative", zorder=1,
    )
    axis.axvline(empirical_min, color="#94a3b8", linewidth=1, linestyle=":")
    axis.axvline(empirical_max, color="#94a3b8", linewidth=1, linestyle=":")
    axis.set_xlim(lower, upper)
    axis.set_ylim(bottom=0)
    axis.set_xlabel("Mean daily D/C")
    axis.set_ylabel(r"Day-to-day $\sigma[\ln(D/C)]$")
    axis.set_title("I-405 South AM day-to-day D/C variability", loc="left", weight="bold")
    axis.grid(axis="y", alpha=0.2)
    axis.legend(frameon=False, loc="upper right")
    fig.tight_layout()
    output.parent.mkdir(exist_ok=True)
    fig.savefig(output, dpi=220, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    config = json.loads(args.config.read_text())
    detector_days = pd.read_csv(ROOT / "results" / "b1_detector_day_dc.csv")
    stats = detector_statistics(detector_days)
    comparison = fit_sigma_models(stats["mean_dc"], stats["sigma_ln_dc"])
    selected_model, selection_reason = choose_model(
        comparison, float(config["aicc_simplicity_threshold"])
    )
    comparison["selected"] = comparison["model"].eq(selected_model)
    comparison["selection_reason"] = np.where(
        comparison["selected"], selection_reason, ""
    )

    bins = binned_statistics(
        stats, float(config["dc_analysis_min"]), float(config["dc_analysis_max"]),
        float(config["dc_bin_width"]),
    )
    selected = comparison.set_index("model").loc[selected_model]
    x_grid = np.round(
        np.arange(float(config["dc_analysis_min"]), float(config["dc_analysis_max"]) + 0.001, 0.01),
        2,
    )
    curve = pd.DataFrame({"mean_dc": x_grid})
    curve["sigma_ln_dc"] = selected["intercept"] + selected["slope"] * curve["mean_dc"]
    curve["empirical_support"] = curve["mean_dc"].between(
        stats["mean_dc"].min(), stats["mean_dc"].max(), inclusive="both"
    )
    curve["model"] = selected_model

    results = ROOT / "results"
    stats.to_csv(results / "b2_detector_log_stats.csv", index=False)
    bins.to_csv(results / "b2_dc_bins.csv", index=False)
    comparison.to_csv(results / "b2_sigma_model_comparison.csv", index=False)
    curve.to_csv(results / "b2_sigma_curve.csv", index=False)
    make_figure(
        stats, comparison, selected_model,
        float(config["dc_analysis_min"]), float(config["dc_analysis_max"]),
        ROOT / "figures" / "experiment_b_sigma_calibration.png",
    )

    constant = comparison.set_index("model").loc["constant"]
    linear = comparison.set_index("model").loc["linear"]
    summary = {
        "analysis_unit": "PeMS mainline detector-day",
        "stochastic_dimension": "variation across weekdays within each detector",
        "detectors": int(len(stats)),
        "detector_days": int(stats["detector_days"].sum()),
        "empirical_mean_dc_min": float(stats["mean_dc"].min()),
        "empirical_mean_dc_max": float(stats["mean_dc"].max()),
        "selected_sigma_model": selected_model,
        "selected_sigma_intercept": float(selected["intercept"]),
        "selected_sigma_slope": float(selected["slope"]),
        "selection_reason": selection_reason,
        "constant_aicc": float(constant["aicc"]),
        "linear_aicc": float(linear["aicc"]),
        "constant_loocv_rmse": float(constant["loocv_rmse"]),
        "linear_loocv_rmse": float(linear["loocv_rmse"]),
        "median_normal_qq_r2": float(stats["normal_qq_r2"].median()),
        "minimum_normal_qq_r2": float(stats["normal_qq_r2"].min()),
        "extrapolation_note": (
            "The fitted sample does not empirically cover the full 0.4-1.3 range. "
            "Predictions outside the observed detector-mean D/C range are extrapolation."
        ),
    }
    (results / "b2_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
