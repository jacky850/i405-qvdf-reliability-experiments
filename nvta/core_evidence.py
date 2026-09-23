"""Memo Section 9, items 4-5: one correlation table and three scatterplots.

Sample: the C3 primary subset for I-95 SB GP PM, i.e. 10 TMCs with
link-specific high/medium QVDF fits and their 133 accepted PM congestion
episode-days. D/C is the dimensionless episode demand over PM-period capacity
from the CBI package. Episode demand is integrated over the same episode that
defines P, from flow reconstructed out of the same RITIS speeds, so D/C vs P is
an internal-consistency check, not independent validation (memo Section 5).
P is episode duration in hours; TTI is the day's 15:00-19:00 mean RITIS
travel time over free-flow time.

C1 correlates link-days. C2 correlates TMCs across their repeated weekdays.
Both are descriptive and conditional on accepted congestion episodes.

Outputs go to ``key_results/`` at the repository root.
"""

from __future__ import annotations

from pathlib import Path
import sys
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import ConstantInputWarning, pearsonr, spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import NVTA_DIR, REPO_ROOT  # noqa: E402


C3 = NVTA_DIR / "c3-qvdf-reliability" / "output"
C4 = NVTA_DIR / "c4-variability-decomposition" / "output"
C5 = NVTA_DIR / "c5-pti-tti-comparison" / "output"
C6 = NVTA_DIR / "c6-managed-lane-comparison" / "output"
B = NVTA_DIR / "b-dc-variability" / "output"
KEY = REPO_ROOT / "key_results"

BOOTSTRAP_REPLICATES = 2000
RANDOM_SEED = 2209

BLUE = "#2a78d6"
ORANGE = "#eb6834"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
GRID = "#e4e3df"


def load_sample() -> tuple[pd.DataFrame, pd.DataFrame]:
    day = pd.read_csv(C3 / "nvta_c3_i95_sb_pm_link_day_audit.csv", dtype={"tmc_code": "string"})
    tmc = pd.read_csv(C3 / "nvta_c3_i95_sb_pm_tmc_validation.csv", dtype={"tmc_code": "string"})
    tmc = tmc[tmc["primary_c3_subset"]].copy()
    day = day[day["analysis_eligible"] & day["tmc_code"].isin(set(tmc["tmc_code"]))].copy()
    day = day.rename(columns={"demand_capacity_ratio": "dc", "observed_daily_pm_tti": "tti"})

    per_tmc = day.groupby("tmc_code").agg(
        mean_P=("P_hr", "mean"),
        P95=("P_hr", lambda values: values.quantile(0.95)),
    )
    tmc = tmc.set_index("tmc_code").join(per_tmc).reset_index()
    return day, tmc


def correlation(x: pd.Series, y: pd.Series, method: str) -> float:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConstantInputWarning)
        if method == "pearson":
            return float(pearsonr(x, y).statistic)
        return float(spearmanr(x, y).statistic)


def bootstrap_interval(frame: pd.DataFrame, x: str, y: str, method: str, seed: int) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    values = []
    for _ in range(BOOTSTRAP_REPLICATES):
        sample = frame.iloc[rng.integers(0, len(frame), size=len(frame))]
        if sample[x].nunique() > 1 and sample[y].nunique() > 1:
            values.append(correlation(sample[x], sample[y], method))
    low, high = np.nanquantile(values, [0.025, 0.975])
    return float(low), float(high)


def correlation_table(day: pd.DataFrame, tmc: pd.DataFrame) -> pd.DataFrame:
    specs = [
        ("C1 link-day", day, "dc", "P_hr", "D/C vs P"),
        ("C1 link-day", day, "dc", "tti", "D/C vs TTI"),
        ("C1 link-day", day, "P_hr", "tti", "P vs TTI"),
        ("C2 TMC across days", tmc, "mean_P", "observed_mean_tti", "E[P] vs TTI"),
        ("C2 TMC across days", tmc, "P95", "observed_pti95", "P95 vs PTI95"),
        ("C2 TMC across days", tmc, "observed_mean_tti", "observed_pti95", "TTI vs PTI95"),
    ]
    rows = []
    seed = RANDOM_SEED
    for level, frame, x, y, label in specs:
        pearson_low, pearson_high = bootstrap_interval(frame, x, y, "pearson", seed)
        spearman_low, spearman_high = bootstrap_interval(frame, x, y, "spearman", seed + 1)
        seed += 2
        rows.append(
            {
                "level": level,
                "pair": label,
                "n": int(len(frame)),
                "unit": "episode-days" if frame is day else "TMCs",
                "pearson_r": correlation(frame[x], frame[y], "pearson"),
                "pearson_95_low": pearson_low,
                "pearson_95_high": pearson_high,
                "spearman_rho": correlation(frame[x], frame[y], "spearman"),
                "spearman_95_low": spearman_low,
                "spearman_95_high": spearman_high,
            }
        )
    return pd.DataFrame(rows)


def style(axis: plt.Axes) -> None:
    axis.grid(color=GRID, lw=0.8)
    axis.set_axisbelow(True)
    axis.spines[["top", "right"]].set_visible(False)


def set_rc() -> None:
    plt.rcParams.update(
        {"font.size": 9.5, "axes.edgecolor": INK_SECONDARY, "axes.labelcolor": INK,
         "xtick.color": INK_SECONDARY, "ytick.color": INK_SECONDARY}
    )


def plot_c1(day: pd.DataFrame, table: pd.DataFrame, output: Path) -> None:
    """Memo scatterplots 1-2: D/C vs P and P vs TTI, one point per episode-day."""
    set_rc()
    figure, axes = plt.subplots(1, 2, figsize=(9.6, 4.2), constrained_layout=True)

    def stat(pair: str) -> str:
        row = table[table["pair"].eq(pair)].iloc[0]
        return f"Pearson {row['pearson_r']:.2f}, Spearman {row['spearman_rho']:.2f} (n = {row['n']} {row['unit']})"

    axis = axes[0]
    axis.scatter(day["dc"], day["P_hr"], s=22, color=BLUE, edgecolors="white", linewidths=0.6, alpha=0.9)
    axis.set_xlabel(r"Episode loading $x = X_E/4\,$h")
    axis.set_ylabel("Congestion duration P (h)")
    axis.set_title(f"(a) $x$ vs $P$ (shared episode)\n{stat('D/C vs P')}", loc="left", fontsize=9.5, color=INK)

    axis = axes[1]
    axis.scatter(day["P_hr"], day["tti"], s=22, color=BLUE, edgecolors="white", linewidths=0.6, alpha=0.9)
    axis.set_xlabel("Congestion duration P (h)")
    axis.set_ylabel("Daily PM TTI")
    axis.set_title(f"(b) P vs TTI\n{stat('P vs TTI')}", loc="left", fontsize=9.5, color=INK)

    for axis in axes:
        style(axis)
    figure.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(figure)


def plot_c3(tmc: pd.DataFrame, output: Path) -> None:
    """Memo scatterplot 3 plus the gamma95 check: observed vs QVDF-implied."""
    set_rc()
    figure, axes = plt.subplots(1, 2, figsize=(9.6, 4.6), constrained_layout=True)
    for axis, (label, observed, model, pad) in zip(
        axes,
        [("PTI95", "observed_pti95", "model_pti95", 0.4), ("gamma95 = PTI95 / TTI", "observed_gamma95", "model_gamma95", 0.08)],
    ):
        axis.scatter(tmc[observed], tmc[model], s=46, color=BLUE, edgecolors="white", linewidths=0.8, zorder=3)
        values = np.r_[tmc[observed], tmc[model]]
        low, high = 1.0, float(values.max()) + pad
        axis.plot([low, high], [low, high], color=INK_SECONDARY, ls="--", lw=1.1)
        axis.text(high, high, "1:1 ", ha="right", va="bottom", fontsize=8.5, color=INK_SECONDARY)
        axis.set_xlim(low, high)
        axis.set_ylim(low, high)
        axis.set_aspect("equal", adjustable="box")
        error = tmc[model] - tmc[observed]
        rho = correlation(tmc[observed], tmc[model], "spearman")
        axis.set_xlabel(f"Observed {label}")
        axis.set_ylabel(f"QVDF-implied {label}")
        axis.set_title(
            f"({'a' if observed == 'observed_pti95' else 'b'}) {label}\nSpearman {rho:.2f}, MAE {error.abs().mean():.2f}, "
            f"bias {error.mean():+.2f} (n = {len(tmc)} TMCs)",
            loc="left", fontsize=9.5, color=INK,
        )
        style(axis)
    figure.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(figure)


def key_numbers(table: pd.DataFrame) -> pd.DataFrame:
    """Collect the few numbers the README quotes, with their source file."""
    c4 = pd.read_csv(C4 / "nvta_c4_summary.csv").set_index("metric")
    c5 = pd.read_csv(C5 / "nvta_c5_pti_tti_summary.csv").set_index("metric")
    c6 = pd.read_csv(C6 / "c6_gp_vs_ml_comparison.csv").set_index("pair")
    c6k = pd.read_csv(C6 / "c6_pti_tti_by_facility.csv").set_index("facility")
    c3 = pd.read_csv(C3 / "nvta_c3_i95_sb_pm_summary.csv")
    c3 = c3[c3["subset"].eq("primary_sensor_high_medium")].set_index("metric")
    primary = c6.loc["I-95 SB PM"]

    def corr(pair: str, column: str) -> float:
        return float(table.loc[table["pair"].eq(pair), column].iloc[0])

    b_models = pd.read_csv(B / "b_sigma_model_comparison.csv")
    b_models = b_models[b_models["selected"]].set_index("scope")
    b_tmc = pd.read_csv(B / "b_tmc_dc_statistics.csv")
    b_check = pd.read_csv(B / "b_planning_sigma_pti95_metrics.csv").set_index("sigma_source")
    rows = [
        ("B", "Share of TMCs passing Shapiro-Wilk on ln(D/C)", float((b_tmc["shapiro_p_ln_dc"] > 0.05).mean()), "share", f"{len(b_tmc)} GP TMCs"),
        ("B", "Share of TMCs where ln(D/C) fits the normal better than D/C", float((b_tmc["qq_r2_ln_dc"] > b_tmc["qq_r2_dc"]).mean()), "share", f"{len(b_tmc)} GP TMCs"),
        ("B", "sigma_ln(D/C), I-95 SB PM (constant model)", float(b_models.loc["I-95 SB PM", "intercept"]), "log units", "16 TMCs; episode-day D/C"),
        ("B", "sigma_ln(D/C), all GP corridor-periods (constant model)", float(b_models.loc["All GP corridor-periods", "intercept"]), "log units", f"{len(b_tmc)} TMCs; episode-day D/C"),
        ("B", "Spearman observed vs QVDF PTI95 with planning sigma (LOTO)", float(b_check.loc["planning sigma, LOTO", "spearman_rho"]), "correlation", "10 TMCs"),
        ("C1", "Spearman D/C vs P", corr("D/C vs P", "spearman_rho"), "correlation", "133 episode-days"),
        ("C1", "Spearman D/C vs TTI", corr("D/C vs TTI", "spearman_rho"), "correlation", "133 episode-days"),
        ("C1", "Spearman P vs TTI", corr("P vs TTI", "spearman_rho"), "correlation", "133 episode-days"),
        ("C2", "Spearman P95 vs PTI95", corr("P95 vs PTI95", "spearman_rho"), "correlation", "10 TMCs"),
        ("C2", "Spearman TTI vs PTI95", corr("TTI vs PTI95", "spearman_rho"), "correlation", "10 TMCs"),
        ("C3", "Spearman observed vs QVDF PTI95", float(c3.loc["PTI95", "spearman_rho"]), "correlation", "10 TMCs"),
        ("C3", "QVDF PTI95 bias (model - observed)", float(c3.loc["PTI95", "bias_model_minus_observed"]), "PTI points", "10 TMCs"),
        ("C4", "Median share of log-delay variance from D/C", float(c4.loc["median_demand_explained_share", "value"]), "share", "10 TMCs"),
        ("C4", "Median residual (non-D/C) share", float(c4.loc["median_unexplained_share", "value"]), "share", "10 TMCs"),
        ("C4", "PTI95 MAE after residual term (LOTO)", float(c4[c4["result_group"].eq("residual_variance_only_loto")].loc["pti95_mae", "value"]), "PTI points", "10 TMCs"),
        ("C5", "Local k in PTI95 = 1 + k ln(TTI)", float(c5.loc["i95_sb_gp_pm_local_k", "value"]), "coefficient", "10 TMCs; SHRP2 k = 3.67"),
        ("C5", "SHRP2 PTI95 MAE", float(c5[c5["result_group"].eq("shrp2_benchmark")].loc["pti95_mae", "value"]), "PTI points", "10 TMCs"),
        ("C5", "Local-k PTI95 MAE (LOTO)", float(c5[c5["result_group"].eq("local_loto")].loc["pti95_mae", "value"]), "PTI points", "10 TMCs"),
        ("C6", "GP local k, all weekdays, 4 open corridor-periods", float(c6k.loc["GP", "local_k"]), "coefficient", f"{int(c6k.loc['GP', 'k_fit_tmcs'])} GP TMCs"),
        ("C6", "I-95 SB PM GP TTI / PTI95", f"{primary['gp_TTI']:.2f} / {primary['gp_PTI95']:.2f}", "index", "23 weekdays"),
        ("C6", "I-95 SB PM express-lane TTI / PTI95", f"{primary['ml_TTI']:.2f} / {primary['ml_PTI95']:.2f}", "index", "23 weekdays"),
        ("C6", "I-95 SB PM planning-time saving, ML vs GP", float(primary["planning_time_saving_min"]), "min/trip", f"{primary['ml_length_mi']:.1f}-mile section"),
        ("C6", "Median express-lane gamma95, open direction", float(c6k.loc["ML", "median_gamma95"]), "ratio", f"{int(c6k.loc['ML', 'tmcs'])} ML TMCs"),
    ]
    frame = pd.DataFrame(rows, columns=["experiment", "quantity", "value", "unit", "sample"])
    frame["value"] = [f"{value:.3f}" if isinstance(value, float) else value for value in frame["value"]]
    return frame


def main() -> None:
    KEY.mkdir(exist_ok=True)
    day, tmc = load_sample()
    table = correlation_table(day, tmc)
    table.round(3).to_csv(KEY / "correlation_table_c1_c2.csv", index=False)
    plot_c1(day, table, KEY / "fig_c1_dc_p_tti.png")
    plot_c3(tmc, KEY / "fig_c3_observed_vs_qvdf.png")
    numbers = key_numbers(table)
    numbers.to_csv(KEY / "key_numbers.csv", index=False)
    print(table.round(3).to_string(index=False))
    print(numbers.to_string(index=False))


if __name__ == "__main__":
    main()
