"""C4: decompose PM reliability into D/C and residual variability.

Inputs are the link-day and TMC outputs from C3.  The primary sample contains
only link-specific high/medium QVDF parameter fits.  Residual augmentation is
evaluated leave-one-TMC-out so a TMC never supplies its own correction term.
"""

from __future__ import annotations

from pathlib import Path
import warnings
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import CBI as CBI_ROOT, NVTA_DIR, RITIS_RAW, experiment_dirs  # noqa: E402

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import ConstantInputWarning, norm, pearsonr, spearmanr


ROOT = NVTA_DIR / "c3-qvdf-reliability" / "output"
LINK_DAY_INPUT = ROOT / "nvta_c3_i95_sb_pm_link_day_audit.csv"
TMC_INPUT = ROOT / "nvta_c3_i95_sb_pm_tmc_validation.csv"

OUTPUT, FIGURES = experiment_dirs("c4-variability-decomposition")

Z95 = float(norm.ppf(0.95))
BOOTSTRAP_REPLICATES = 1000
RANDOM_SEED = 405


def safe_corr(x: pd.Series, y: pd.Series, method: str) -> float:
    pair = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(pair) < 3 or pair["x"].nunique() < 2 or pair["y"].nunique() < 2:
        return np.nan
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConstantInputWarning)
        if method == "pearson":
            return float(pearsonr(pair["x"], pair["y"]).statistic)
        return float(spearmanr(pair["x"], pair["y"]).statistic)


def r2_fixed(observed: np.ndarray, predicted: np.ndarray) -> float:
    observed = np.asarray(observed, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    mask = np.isfinite(observed) & np.isfinite(predicted)
    observed = observed[mask]
    predicted = predicted[mask]
    if len(observed) < 2:
        return np.nan
    denominator = float(np.sum((observed - observed.mean()) ** 2))
    if denominator <= 0:
        return np.nan
    return float(1.0 - np.sum((observed - predicted) ** 2) / denominator)


def load_primary_data() -> tuple[pd.DataFrame, pd.DataFrame]:
    day = pd.read_csv(LINK_DAY_INPUT, dtype={"tmc_code": "string"})
    tmc = pd.read_csv(TMC_INPUT, dtype={"tmc_code": "string"})
    primary_tmcs = set(tmc.loc[tmc["primary_c3_subset"], "tmc_code"])
    day = day[
        day["analysis_eligible"]
        & day["tmc_code"].isin(primary_tmcs)
        & day["observed_daily_pm_tti"].gt(1.0)
        & day["demand_capacity_ratio"].gt(0.0)
    ].copy()
    tmc = tmc[tmc["primary_c3_subset"]].copy()
    if day["tmc_code"].nunique() != len(tmc):
        raise ValueError("Primary TMC coverage differs between C3 inputs")
    return day, tmc


def prepare_residuals(day: pd.DataFrame) -> pd.DataFrame:
    day = day.sort_values(["tmc_code", "date_local"]).copy()
    day["log_dc"] = np.log(day["demand_capacity_ratio"])
    day["observed_delay_tti"] = day["observed_daily_pm_tti"] - 1.0
    day["log_observed_delay"] = np.log(day["observed_delay_tti"])
    day["log_qvdf_delay"] = np.log(day["alpha"]) + day["beta"] * day["log_dc"]
    day["qvdf_daily_tti"] = 1.0 + np.exp(day["log_qvdf_delay"])
    day["log_delay_residual"] = (
        day["log_observed_delay"] - day["log_qvdf_delay"]
    )
    for column in ["log_observed_delay", "log_qvdf_delay", "log_delay_residual"]:
        day[f"{column}_within_tmc"] = day[column] - day.groupby("tmc_code")[
            column
        ].transform("mean")
    day["residual_interpretation"] = (
        "day-to-day log-delay variation not reproduced by calibrated D/C and QVDF"
    )
    return day


def pooled_residual_sigma(training: pd.DataFrame) -> float:
    centered = training["log_delay_residual_within_tmc"].to_numpy(float)
    tmcs = training["tmc_code"].nunique()
    denominator = len(centered) - tmcs
    if denominator <= 0:
        return np.nan
    return float(np.sqrt(np.sum(centered**2) / denominator))


def build_tmc_decomposition(day: pd.DataFrame, c3_tmc: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    for held_tmc, held in day.groupby("tmc_code", sort=True):
        train = day[day["tmc_code"] != held_tmc]
        c3 = c3_tmc[c3_tmc["tmc_code"] == held_tmc].iloc[0]

        residual_mean_loto = float(train["log_delay_residual"].mean())
        residual_sigma_loto = pooled_residual_sigma(train)
        mu_x = float(held["log_dc"].mean())
        sigma_x = float(held["log_dc"].std(ddof=1))
        alpha = float(c3["alpha"])
        beta = float(c3["beta"])

        demand_log_variance = beta * beta * sigma_x * sigma_x
        residual_log_variance = residual_sigma_loto * residual_sigma_loto
        total_log_variance = demand_log_variance + residual_log_variance
        demand_share = demand_log_variance / total_log_variance
        residual_share = residual_log_variance / total_log_variance

        corrected_log_mean = np.log(alpha) + beta * mu_x + residual_mean_loto
        corrected_mean_tti = 1.0 + np.exp(
            corrected_log_mean + 0.5 * total_log_variance
        )
        corrected_pti95 = 1.0 + np.exp(
            corrected_log_mean + Z95 * np.sqrt(total_log_variance)
        )
        # A mean-preserving version isolates the effect of adding residual
        # variability.  Setting E[exp(g)] to one requires mu_g=-sigma_g^2/2.
        variance_only_log_mean = (
            np.log(alpha) + beta * mu_x - 0.5 * residual_log_variance
        )
        variance_only_mean_tti = 1.0 + np.exp(
            variance_only_log_mean + 0.5 * total_log_variance
        )
        variance_only_pti95 = 1.0 + np.exp(
            variance_only_log_mean + Z95 * np.sqrt(total_log_variance)
        )

        held_residual = held["log_delay_residual"]
        rows.append(
            {
                "corridor": "I-95 SB",
                "facility": "GP",
                "period": "PM 15:00-19:00",
                "tmc_code": held_tmc,
                "network_link_id": int(c3["network_link_id"]),
                "road_order": float(c3["road_order"]),
                "accepted_episode_days": int(len(held)),
                "alpha": alpha,
                "beta": beta,
                "parameter_reliability": c3["parameter_reliability"],
                "mean_dc": float(held["demand_capacity_ratio"].mean()),
                "mu_ln_dc": mu_x,
                "sigma_ln_dc": sigma_x,
                "mean_log_delay_residual": float(held_residual.mean()),
                "within_tmc_sigma_log_delay_residual": float(
                    held_residual.std(ddof=1)
                ),
                "loto_residual_mean": residual_mean_loto,
                "loto_within_tmc_residual_sigma": residual_sigma_loto,
                "demand_log_variance": demand_log_variance,
                "unexplained_log_variance": residual_log_variance,
                "demand_explained_share_assuming_independence": demand_share,
                "unexplained_share_assuming_independence": residual_share,
                "observed_mean_tti": float(c3["observed_mean_tti"]),
                "raw_qvdf_mean_tti": float(c3["model_mean_tti"]),
                "residual_variance_only_mean_tti_loto": variance_only_mean_tti,
                "residual_bias_and_variance_mean_tti_loto": corrected_mean_tti,
                "observed_pti95": float(c3["observed_pti95"]),
                "raw_qvdf_pti95": float(c3["model_pti95"]),
                "residual_variance_only_pti95_loto": variance_only_pti95,
                "residual_bias_and_variance_pti95_loto": corrected_pti95,
                "raw_pti95_error": float(c3["model_pti95"] - c3["observed_pti95"]),
                "residual_variance_only_pti95_error": float(
                    variance_only_pti95 - c3["observed_pti95"]
                ),
                "residual_bias_and_variance_pti95_error": float(
                    corrected_pti95 - c3["observed_pti95"]
                ),
                "variance_share_note": (
                    "shares use beta^2 Var[ln(D/C)] and leave-one-TMC-out "
                    "within-link residual variance; independence assumed"
                ),
            }
        )
    return pd.DataFrame(rows).sort_values(["road_order", "tmc_code"])


def bootstrap_metric(
    data: pd.DataFrame,
    observed_col: str,
    predicted_col: str,
    statistic: str,
    seed: int,
) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    values: list[float] = []
    for _ in range(BOOTSTRAP_REPLICATES):
        sample = data.iloc[rng.integers(0, len(data), size=len(data))]
        observed = sample[observed_col]
        predicted = sample[predicted_col]
        if statistic == "pearson":
            value = safe_corr(observed, predicted, "pearson")
        elif statistic == "mae":
            value = float((predicted - observed).abs().mean())
        else:
            raise ValueError(statistic)
        if np.isfinite(value):
            values.append(value)
    if not values:
        return np.nan, np.nan
    return tuple(np.quantile(values, [0.025, 0.975]).astype(float))


def build_summary(day: pd.DataFrame, tmc: pd.DataFrame) -> pd.DataFrame:
    y = day["log_observed_delay"]
    x = day["log_qvdf_delay"]
    yw = day["log_observed_delay_within_tmc"]
    xw = day["log_qvdf_delay_within_tmc"]

    pooled_r = safe_corr(x, y, "pearson")
    within_r = safe_corr(xw, yw, "pearson")
    tmc_means = (
        day.groupby("tmc_code", as_index=False)[
            ["log_observed_delay", "log_qvdf_delay"]
        ].mean()
    )
    between_r = safe_corr(
        tmc_means["log_qvdf_delay"], tmc_means["log_observed_delay"], "pearson"
    )

    rows = [
        {
            "result_group": "variability_decomposition",
            "metric": "pooled_log_delay_association_r_squared",
            "value": pooled_r**2,
            "unit": "share",
            "sample": f"{len(day)} episode-days across {day.tmc_code.nunique()} TMCs",
            "interpretation": "pooled association; includes between-link differences",
        },
        {
            "result_group": "variability_decomposition",
            "metric": "within_tmc_day_to_day_association_r_squared",
            "value": within_r**2,
            "unit": "share",
            "sample": f"{len(day)} episode-days across {day.tmc_code.nunique()} TMCs",
            "interpretation": "primary explained-variability statistic for day-to-day reliability",
        },
        {
            "result_group": "variability_decomposition",
            "metric": "between_tmc_mean_association_r_squared",
            "value": between_r**2,
            "unit": "share",
            "sample": f"{day.tmc_code.nunique()} TMC means",
            "interpretation": "association between link-average D/C signal and link-average delay",
        },
        {
            "result_group": "variability_decomposition",
            "metric": "fixed_qvdf_within_tmc_r_squared",
            "value": r2_fixed(yw.to_numpy(float), xw.to_numpy(float)),
            "unit": "share",
            "sample": f"{len(day)} episode-days across {day.tmc_code.nunique()} TMCs",
            "interpretation": "uses QVDF magnitude without refitting; can be negative",
        },
        {
            "result_group": "variance_components",
            "metric": "median_demand_explained_share",
            "value": float(tmc["demand_explained_share_assuming_independence"].median()),
            "unit": "share",
            "sample": f"{len(tmc)} TMCs",
            "interpretation": "median beta-squared log-D/C variance share",
        },
        {
            "result_group": "variance_components",
            "metric": "median_unexplained_share",
            "value": float(tmc["unexplained_share_assuming_independence"].median()),
            "unit": "share",
            "sample": f"{len(tmc)} TMCs",
            "interpretation": "median residual log-delay variance share",
        },
    ]

    seed = RANDOM_SEED
    for model_name, predicted_col in [
        ("raw_qvdf", "raw_qvdf_pti95"),
        ("residual_variance_only_loto", "residual_variance_only_pti95_loto"),
        (
            "residual_bias_and_variance_loto",
            "residual_bias_and_variance_pti95_loto",
        ),
    ]:
        observed_col = "observed_pti95"
        error = tmc[predicted_col] - tmc[observed_col]
        pearson = safe_corr(tmc[observed_col], tmc[predicted_col], "pearson")
        spearman = safe_corr(tmc[observed_col], tmc[predicted_col], "spearman")
        r_low, r_high = bootstrap_metric(
            tmc, observed_col, predicted_col, "pearson", seed
        )
        mae_low, mae_high = bootstrap_metric(
            tmc, observed_col, predicted_col, "mae", seed + 1
        )
        for metric, value, unit, interpretation in [
            ("pti95_pearson_r", pearson, "correlation", "observed versus modeled PTI95"),
            ("pti95_spearman_rho", spearman, "correlation", "observed versus modeled PTI95 ranks"),
            ("pti95_mae", float(error.abs().mean()), "PTI points", f"bootstrap 95% interval {mae_low:.3f} to {mae_high:.3f}"),
            ("pti95_rmse", float(np.sqrt(np.mean(error**2))), "PTI points", "root mean squared error"),
            ("pti95_bias", float(error.mean()), "PTI points", "model minus observed"),
        ]:
            rows.append(
                {
                    "result_group": model_name,
                    "metric": metric,
                    "value": value,
                    "unit": unit,
                    "sample": f"{len(tmc)} TMCs",
                    "interpretation": (
                        f"{interpretation}; Pearson bootstrap 95% interval "
                        f"{r_low:.3f} to {r_high:.3f}"
                        if metric == "pti95_pearson_r"
                        else interpretation
                    ),
                }
            )
        seed += 2
    return pd.DataFrame(rows)


def plot_pti95_comparison(tmc: pd.DataFrame, output: Path) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(10.8, 5.0), sharex=True, sharey=True, constrained_layout=True)
    configurations = [
        ("raw_qvdf_pti95", "QVDF demand variability only"),
        (
            "residual_variance_only_pti95_loto",
            "Add unexplained variance; preserve mean",
        ),
    ]
    values = np.concatenate(
        [
            tmc["observed_pti95"].to_numpy(float),
            tmc["raw_qvdf_pti95"].to_numpy(float),
            tmc["residual_variance_only_pti95_loto"].to_numpy(float),
        ]
    )
    lower = max(1.0, float(np.nanmin(values) - 0.1))
    upper = float(np.nanmax(values) + 0.15)
    colors = {"high": "#1f77b4", "medium": "#f28e2b"}
    markers = {"high": "o", "medium": "s"}
    for axis, (column, title) in zip(axes, configurations):
        for reliability, group in tmc.groupby("parameter_reliability", sort=True):
            axis.scatter(
                group["observed_pti95"],
                group[column],
                s=52,
                color=colors[reliability],
                marker=markers[reliability],
                edgecolors="white",
                linewidths=0.6,
                label=f"{reliability} fit",
            )
        axis.plot([lower, upper], [lower, upper], color="#222222", ls="--", lw=1.0)
        axis.set_xlim(lower, upper)
        axis.set_ylim(lower, upper)
        axis.set_aspect("equal", adjustable="box")
        axis.set_title(title, fontsize=11)
        axis.set_xlabel("Observed PTI95")
        axis.grid(color="#d9d9d9", linewidth=0.8)
        axis.set_axisbelow(True)
        axis.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Modeled PTI95")
    axes[0].legend(frameon=False, fontsize=8, loc="upper left")
    figure.suptitle(
        "I-95 South GP PM: effect of adding unexplained day-to-day variability",
        fontsize=13,
    )
    figure.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(figure)


def plot_variance_shares(tmc: pd.DataFrame, output: Path) -> None:
    plot = tmc.sort_values("demand_explained_share_assuming_independence").copy()
    positions = np.arange(len(plot))
    figure, axis = plt.subplots(figsize=(8.0, 5.2), constrained_layout=True)
    axis.barh(
        positions,
        100.0 * plot["demand_explained_share_assuming_independence"],
        color="#4e79a7",
        label="D/C variability",
    )
    axis.barh(
        positions,
        100.0 * plot["unexplained_share_assuming_independence"],
        left=100.0 * plot["demand_explained_share_assuming_independence"],
        color="#f28e2b",
        label="Unexplained variability",
    )
    axis.set_yticks(positions, plot["tmc_code"])
    axis.set_xlim(0, 100)
    axis.set_xlabel("Share of modeled log-delay variance (%)")
    axis.set_title(
        "I-95 South GP PM: day-to-day reliability variance decomposition\n"
        "Independence assumption; leave-one-TMC-out residual variance",
        fontsize=12,
    )
    axis.grid(axis="x", color="#d9d9d9", linewidth=0.8)
    axis.set_axisbelow(True)
    axis.spines[["top", "right", "left"]].set_visible(False)
    axis.legend(
        frameon=False,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.10),
        ncol=2,
    )
    figure.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    FIGURES.mkdir(parents=True, exist_ok=True)
    day, c3_tmc = load_primary_data()
    day = prepare_residuals(day)
    tmc = build_tmc_decomposition(day, c3_tmc)
    summary = build_summary(day, tmc)

    day.to_csv(OUTPUT / "nvta_c4_link_day_log_delay_residuals.csv", index=False)
    tmc.to_csv(OUTPUT / "nvta_c4_tmc_variability_and_pti95.csv", index=False)
    summary.to_csv(OUTPUT / "nvta_c4_summary.csv", index=False)
    plot_pti95_comparison(tmc, FIGURES / "nvta_c4_pti95_residual_augmentation.png")
    plot_variance_shares(tmc, FIGURES / "nvta_c4_variability_decomposition.png")

    print("Primary episode-days:", len(day))
    print("Primary TMCs:", len(tmc))
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
