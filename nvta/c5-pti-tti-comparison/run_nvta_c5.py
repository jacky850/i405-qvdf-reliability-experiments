"""C5: compare the observed PTI95-TTI relationship with SHRP2 L03."""

from __future__ import annotations

from pathlib import Path
import warnings
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import CBI as CBI_ROOT, NVTA_DIR, RITIS_RAW, experiment_dirs  # noqa: E402

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import ConstantInputWarning, pearsonr, spearmanr


INPUT = NVTA_DIR / "c3-qvdf-reliability" / "output" / "nvta_c3_i95_sb_pm_tmc_validation.csv"
OUTPUT, FIGURES = experiment_dirs("c5-pti-tti-comparison")

SHRP2_K = 3.67
BOOTSTRAP_REPLICATES = 2000
RANDOM_SEED = 5066


def safe_corr(x: pd.Series, y: pd.Series, method: str) -> float:
    pair = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(pair) < 3 or pair["x"].nunique() < 2 or pair["y"].nunique() < 2:
        return np.nan
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConstantInputWarning)
        if method == "pearson":
            return float(pearsonr(pair["x"], pair["y"]).statistic)
        return float(spearmanr(pair["x"], pair["y"]).statistic)


def fit_constrained_k(tti: pd.Series, pti95: pd.Series) -> float:
    x = np.log(tti.to_numpy(float))
    y = pti95.to_numpy(float) - 1.0
    denominator = float(np.dot(x, x))
    if denominator <= 0:
        return np.nan
    return float(np.dot(x, y) / denominator)


def bootstrap_k(data: pd.DataFrame) -> tuple[float, float, int]:
    rng = np.random.default_rng(RANDOM_SEED)
    estimates: list[float] = []
    for _ in range(BOOTSTRAP_REPLICATES):
        sample = data.iloc[rng.integers(0, len(data), size=len(data))]
        value = fit_constrained_k(sample["observed_mean_tti"], sample["observed_pti95"])
        if np.isfinite(value):
            estimates.append(value)
    low, high = np.quantile(estimates, [0.025, 0.975])
    return float(low), float(high), len(estimates)


def prepare_tmc_results() -> tuple[pd.DataFrame, float, float, float]:
    data = pd.read_csv(INPUT, dtype={"tmc_code": "string"})
    data = data[data["primary_c3_subset"]].copy()
    data = data.sort_values(["road_order", "tmc_code"])
    if len(data) != 10:
        raise ValueError("Expected the 10-TMC primary C3 sample")

    local_k = fit_constrained_k(data["observed_mean_tti"], data["observed_pti95"])
    k_low, k_high, _ = bootstrap_k(data)
    data["ln_observed_mean_tti"] = np.log(data["observed_mean_tti"])
    data["shrp2_coefficient"] = SHRP2_K
    data["shrp2_predicted_pti95"] = 1.0 + SHRP2_K * data["ln_observed_mean_tti"]
    data["local_full_sample_coefficient"] = local_k
    data["local_full_sample_predicted_pti95"] = (
        1.0 + local_k * data["ln_observed_mean_tti"]
    )

    loto_coefficients: list[float] = []
    loto_predictions: list[float] = []
    for index, row in data.iterrows():
        training = data[data.index != index]
        coefficient = fit_constrained_k(
            training["observed_mean_tti"], training["observed_pti95"]
        )
        loto_coefficients.append(coefficient)
        loto_predictions.append(
            1.0 + coefficient * np.log(float(row["observed_mean_tti"]))
        )
    data["local_loto_coefficient"] = loto_coefficients
    data["local_loto_predicted_pti95"] = loto_predictions
    data["shrp2_error_predicted_minus_observed"] = (
        data["shrp2_predicted_pti95"] - data["observed_pti95"]
    )
    data["local_loto_error_predicted_minus_observed"] = (
        data["local_loto_predicted_pti95"] - data["observed_pti95"]
    )
    data["relationship_form"] = "PTI95 = 1 + k * ln(TTI)"
    data["analysis_scope"] = (
        "I-95 South GP PM; conditional on accepted congestion episodes"
    )
    return data, local_k, k_low, k_high


def model_metrics(data: pd.DataFrame, predicted: str) -> dict[str, float]:
    error = data[predicted] - data["observed_pti95"]
    return {
        "pearson_r": safe_corr(data["observed_pti95"], data[predicted], "pearson"),
        "spearman_rho": safe_corr(
            data["observed_pti95"], data[predicted], "spearman"
        ),
        "mae": float(error.abs().mean()),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "bias": float(error.mean()),
    }


def bootstrap_mae(data: pd.DataFrame, predicted: str, seed: int) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    values: list[float] = []
    for _ in range(BOOTSTRAP_REPLICATES):
        sample = data.iloc[rng.integers(0, len(data), size=len(data))]
        values.append(
            float((sample[predicted] - sample["observed_pti95"]).abs().mean())
        )
    return tuple(np.quantile(values, [0.025, 0.975]).astype(float))


def build_summary(
    data: pd.DataFrame, local_k: float, k_low: float, k_high: float
) -> pd.DataFrame:
    observed_pearson = safe_corr(
        data["observed_mean_tti"], data["observed_pti95"], "pearson"
    )
    observed_spearman = safe_corr(
        data["observed_mean_tti"], data["observed_pti95"], "spearman"
    )
    rows = [
        {
            "result_group": "observed_relationship",
            "metric": "tti_pti95_pearson_r",
            "value": observed_pearson,
            "unit": "correlation",
            "sample": "10 TMCs; 133 accepted episode-days",
            "interpretation": "strong within-corridor association",
        },
        {
            "result_group": "observed_relationship",
            "metric": "tti_pti95_spearman_rho",
            "value": observed_spearman,
            "unit": "correlation",
            "sample": "10 TMCs; 133 accepted episode-days",
            "interpretation": "strong monotonic association",
        },
        {
            "result_group": "coefficient_comparison",
            "metric": "shrp2_k",
            "value": SHRP2_K,
            "unit": "coefficient",
            "sample": "published benchmark supplied by project scope",
            "interpretation": "PTI95 = 1 + 3.67 ln(TTI)",
        },
        {
            "result_group": "coefficient_comparison",
            "metric": "i95_sb_gp_pm_local_k",
            "value": local_k,
            "unit": "coefficient",
            "sample": "10 TMCs",
            "interpretation": f"bootstrap 95% interval {k_low:.3f} to {k_high:.3f}",
        },
        {
            "result_group": "coefficient_comparison",
            "metric": "local_k_divided_by_shrp2_k",
            "value": local_k / SHRP2_K,
            "unit": "ratio",
            "sample": "10 TMCs",
            "interpretation": "local slope as a share of the SHRP2 slope",
        },
    ]

    for group, column, seed in [
        ("shrp2_benchmark", "shrp2_predicted_pti95", RANDOM_SEED + 1),
        ("local_loto", "local_loto_predicted_pti95", RANDOM_SEED + 2),
    ]:
        metrics = model_metrics(data, column)
        mae_low, mae_high = bootstrap_mae(data, column, seed)
        definitions = [
            ("pti95_pearson_r", metrics["pearson_r"], "correlation", "observed versus predicted PTI95"),
            ("pti95_spearman_rho", metrics["spearman_rho"], "correlation", "rank association"),
            ("pti95_mae", metrics["mae"], "PTI points", f"bootstrap 95% interval {mae_low:.3f} to {mae_high:.3f}"),
            ("pti95_rmse", metrics["rmse"], "PTI points", "root mean squared error"),
            ("pti95_bias", metrics["bias"], "PTI points", "predicted minus observed"),
        ]
        for metric, value, unit, interpretation in definitions:
            rows.append(
                {
                    "result_group": group,
                    "metric": metric,
                    "value": value,
                    "unit": unit,
                    "sample": "10 TMCs",
                    "interpretation": interpretation,
                }
            )

    rows.append(
        {
            "result_group": "transferability",
            "metric": "shrp2_k_outside_local_bootstrap_interval",
            "value": bool(SHRP2_K < k_low or SHRP2_K > k_high),
            "unit": "boolean",
            "sample": "10 TMCs",
            "interpretation": (
                "supports local recalibration of k; does not by itself establish "
                "cross-facility or cross-geography transferability"
            ),
        }
    )
    shrp2_mae = float(
        (data["shrp2_predicted_pti95"] - data["observed_pti95"]).abs().mean()
    )
    local_loto_mae = float(
        (data["local_loto_predicted_pti95"] - data["observed_pti95"])
        .abs()
        .mean()
    )
    rows.extend(
        [
            {
                "result_group": "comparison",
                "metric": "shrp2_overprediction_tmc_count",
                "value": int(
                    (data["shrp2_predicted_pti95"] > data["observed_pti95"]).sum()
                ),
                "unit": "TMCs",
                "sample": "10 TMCs",
                "interpretation": "number of TMCs for which SHRP2 predicts PTI95 above observed",
            },
            {
                "result_group": "comparison",
                "metric": "local_loto_mae_reduction_vs_shrp2",
                "value": (shrp2_mae - local_loto_mae) / shrp2_mae,
                "unit": "share",
                "sample": "10 TMCs",
                "interpretation": "relative reduction in PTI95 MAE",
            },
        ]
    )
    return pd.DataFrame(rows)


def plot_relationship(data: pd.DataFrame, local_k: float, k_low: float, k_high: float, output: Path) -> None:
    x_grid = np.linspace(
        max(1.01, float(data["observed_mean_tti"].min()) - 0.12),
        float(data["observed_mean_tti"].max()) + 0.20,
        250,
    )
    figure, axis = plt.subplots(figsize=(7.4, 5.6), constrained_layout=True)
    axis.scatter(
        data["observed_mean_tti"],
        data["observed_pti95"],
        s=62,
        color="#2a78d6",
        edgecolors="white",
        linewidths=0.7,
        label=f"Observed TMCs (n={len(data)})",
        zorder=3,
    )
    axis.plot(
        x_grid,
        1.0 + SHRP2_K * np.log(x_grid),
        color="#222222",
        linestyle="--",
        linewidth=1.6,
        label="SHRP2: k = 3.67",
    )
    axis.plot(
        x_grid,
        1.0 + local_k * np.log(x_grid),
        color="#4e79a7",
        linewidth=2.0,
        label=f"I-95 local fit: k = {local_k:.2f}",
    )
    axis.fill_between(
        x_grid,
        1.0 + k_low * np.log(x_grid),
        1.0 + k_high * np.log(x_grid),
        color="#4e79a7",
        alpha=0.14,
        label="Local k bootstrap 95% interval",
    )
    axis.set_xlabel("Observed mean TTI")
    axis.set_ylabel("Observed PTI95")
    axis.set_title(
        "I-95 South GP PM: PTI95-TTI relationship\n"
        "Accepted congestion episodes; 10 TMCs",
        fontsize=12,
    )
    axis.grid(color="#d9d9d9", linewidth=0.8)
    axis.set_axisbelow(True)
    axis.spines[["top", "right"]].set_visible(False)
    axis.legend(frameon=False, fontsize=8, loc="upper left")
    figure.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    data, local_k, k_low, k_high = prepare_tmc_results()
    summary = build_summary(data, local_k, k_low, k_high)
    data.to_csv(OUTPUT / "nvta_c5_pti_tti_tmc_comparison.csv", index=False)
    summary.to_csv(OUTPUT / "nvta_c5_pti_tti_summary.csv", index=False)
    plot_relationship(
        data,
        local_k,
        k_low,
        k_high,
        FIGURES / "nvta_c5_pti_tti_shrp2_comparison.png",
    )
    print("Local k:", local_k)
    print("Bootstrap 95% interval:", k_low, k_high)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
