#!/usr/bin/env python3
"""Fit the PeMS delay curve and create the QVDF reliability envelope."""

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

from experiment_b.core import fit_delay_power_curve, reliability_envelope


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path, default=ROOT / "config" / "experiment_b.json"
    )
    return parser.parse_args()


def make_calibration_figure(
    observations: pd.DataFrame,
    fit: dict[str, float | int],
    empirical_min: float,
    empirical_max: float,
    output: Path,
) -> None:
    x_grid = np.linspace(empirical_min, empirical_max, 400)
    fitted = 1.0 + float(fit["alpha"]) * x_grid ** float(fit["beta"])
    fig, axis = plt.subplots(figsize=(8.7, 5.2))
    axis.scatter(
        observations["dc_ratio"], observations["peak_window_tti"],
        s=13, alpha=0.24, color="#64748b", edgecolor="none",
        label=f"Detector-days (n={len(observations):,})",
    )
    axis.plot(
        x_grid, fitted, color="#0f766e", linewidth=2.5,
        label=(
            r"Fitted $1+\alpha(D/C)^\beta$: "
            f"alpha={float(fit['alpha']):.3f}, beta={float(fit['beta']):.3f}"
        ),
    )
    axis.set_xlabel("Daily peak-hour D/C")
    axis.set_ylabel("Observed peak-hour TTI")
    axis.set_title("PeMS delay-curve calibration", loc="left", weight="bold")
    axis.grid(axis="y", alpha=0.2)
    axis.legend(frameon=False, loc="upper left")
    axis.text(
        0.98, 0.05,
        f"R² = {float(fit['r_squared_tti']):.3f}\nRMSE = {float(fit['rmse_tti']):.3f}",
        transform=axis.transAxes, ha="right", va="bottom", color="#334155",
    )
    fig.tight_layout()
    output.parent.mkdir(exist_ok=True)
    fig.savefig(output, dpi=220, bbox_inches="tight")
    plt.close(fig)


def make_envelope_figure(
    curve: pd.DataFrame,
    empirical_min: float,
    empirical_max: float,
    output: Path,
) -> None:
    colors = {
        "tti_50": "#0f766e",
        "tti_80": "#2563eb",
        "tti_90": "#7c3aed",
        "tti_95": "#dc2626",
    }
    fig, axis = plt.subplots(figsize=(9.2, 5.4))
    lower = float(curve["mean_dc"].min())
    upper = float(curve["mean_dc"].max())
    axis.axvspan(lower, empirical_min, color="#f1f5f9", zorder=0)
    axis.axvspan(
        empirical_max, upper, color="#f1f5f9", zorder=0, label="Extrapolation"
    )
    for column, color in colors.items():
        percentile = column.split("_")[1]
        axis.plot(
            curve["mean_dc"], curve[column], color=color, linewidth=2.2,
            label=rf"TTI$_{{{percentile}}}$",
        )
    axis.plot(
        curve["mean_dc"], curve["shrp2_tti95"], color="#111827",
        linewidth=1.8, linestyle="--", label="SHRP2 L03 benchmark",
    )
    axis.axvline(empirical_min, color="#94a3b8", linewidth=1, linestyle=":")
    axis.axvline(empirical_max, color="#94a3b8", linewidth=1, linestyle=":")
    axis.set_xlim(lower, upper)
    axis.set_ylim(bottom=1.0)
    axis.set_xlabel("Mean daily D/C")
    axis.set_ylabel("Travel Time Index")
    axis.set_title("I-405 South AM reliability envelope", loc="left", weight="bold")
    axis.grid(axis="y", alpha=0.2)
    axis.legend(frameon=False, ncol=2, loc="upper left")
    fig.tight_layout()
    output.parent.mkdir(exist_ok=True)
    fig.savefig(output, dpi=220, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    args = parse_args()
    config = json.loads(args.config.read_text())
    detector_days = pd.read_csv(ROOT / "results" / "b1_detector_day_dc.csv")
    sigma_summary = json.loads((ROOT / "results" / "b2_summary.json").read_text())

    fit_sample = detector_days.loc[
        detector_days["dc_ratio"].between(
            float(config["dc_analysis_min"]),
            float(config["dc_analysis_max"]),
            inclusive="both",
        )
        & detector_days["peak_window_tti"].notna()
    ].copy()
    fit = fit_delay_power_curve(
        fit_sample["dc_ratio"].to_numpy(float),
        fit_sample["peak_window_tti"].to_numpy(float),
        beta_min=float(config["delay_beta_min"]),
        beta_max=float(config["delay_beta_max"]),
    )
    fit_sample["tti_fitted"] = 1.0 + float(fit["alpha"]) * (
        fit_sample["dc_ratio"] ** float(fit["beta"])
    )
    fit_sample["tti_residual"] = (
        fit_sample["peak_window_tti"] - fit_sample["tti_fitted"]
    )
    fit_sample["delay_ratio_observed"] = fit_sample["peak_window_tti"] - 1.0
    fit_sample["delay_ratio_fitted"] = fit_sample["tti_fitted"] - 1.0

    lower = float(config["dc_analysis_min"])
    upper = float(config["dc_analysis_max"])
    step = float(config["reliability_curve_step"])
    mean_dc = np.round(np.arange(lower, upper + step / 2.0, step), 10)
    sigma = (
        float(sigma_summary["selected_sigma_intercept"])
        + float(sigma_summary["selected_sigma_slope"]) * mean_dc
    )
    curve = reliability_envelope(
        mean_dc,
        alpha=float(fit["alpha"]),
        beta=float(fit["beta"]),
        sigma_ln_dc=sigma,
        percentiles=[float(value) for value in config["reliability_percentiles"]],
    )
    empirical_min = float(fit_sample.groupby("station_id")["dc_ratio"].mean().min())
    empirical_max = float(fit_sample.groupby("station_id")["dc_ratio"].mean().max())
    curve["empirical_support"] = curve["mean_dc"].between(
        empirical_min, empirical_max, inclusive="both"
    )
    curve["sigma_model"] = sigma_summary["selected_sigma_model"]
    curve["alpha"] = float(fit["alpha"])
    curve["beta"] = float(fit["beta"])

    results = ROOT / "results"
    figures = ROOT / "figures"
    predictions_columns = [
        "station_id", "link_id", "station_name", "date_local", "dc_ratio",
        "peak_window_tti", "delay_ratio_observed", "tti_fitted",
        "delay_ratio_fitted", "tti_residual",
    ]
    fit_sample[predictions_columns].to_csv(
        results / "b3_delay_fit_predictions.csv", index=False
    )
    curve.to_csv(results / "b3_reliability_envelope.csv", index=False)
    make_calibration_figure(
        fit_sample, fit, empirical_min, empirical_max,
        figures / "experiment_b_delay_calibration.png",
    )
    make_envelope_figure(
        curve, empirical_min, empirical_max,
        figures / "experiment_b_reliability_envelope.png",
    )

    summary = {
        "delay_model": "TTI = 1 + alpha * (D/C)^beta",
        "delay_fit_method": "nonlinear least squares in observed TTI space",
        **fit,
        "sigma_model": sigma_summary["selected_sigma_model"],
        "sigma_intercept": float(sigma_summary["selected_sigma_intercept"]),
        "sigma_slope": float(sigma_summary["selected_sigma_slope"]),
        "empirical_mean_dc_min": empirical_min,
        "empirical_mean_dc_max": empirical_max,
        "curve_dc_min": lower,
        "curve_dc_max": upper,
        "percentiles": config["reliability_percentiles"],
        "shrp2_benchmark": "TTI_95 = 1 + 3.67 * ln(expected TTI)",
        "interpretation_limit": (
            "The reliability pipeline is complete, but the pooled PeMS delay-curve "
            "calibration must be judged from its R-squared and RMSE before the "
            "envelope is used as a validated forecasting model."
        ),
    }
    (results / "b3_summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
