"""Experiment B on NVTA data: day-to-day D/C distribution and sigma model.

Mirrors the PeMS Experiment B steps on I-95/I-395 GP TMCs:

B1  Is ln(D/C) approximately normal across a TMC's weekdays?
B2  Is sigma_ln(D/C) constant, or does it change with mean D/C?
B3  Does a planning-level sigma (from B2, leave-one-TMC-out) reproduce the
    C3 PTI95 comparison as well as each TMC's own sigma?

Daily D/C comes from the CBI accepted congestion episodes (episode demand
over period capacity). Days without an accepted episode have no D/C, so every
statistic here is conditional on congested days; the low tail is missing and
sigma is a lower bound for the full weekday distribution.
"""

from __future__ import annotations

from pathlib import Path
import sys
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import ConstantInputWarning, norm, shapiro, skew, spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from paths import CBI, NVTA_DIR, experiment_dirs  # noqa: E402
from experiment_b.core import fit_sigma_models, normal_qq_r2  # noqa: E402


OUTPUT, FIGURES = experiment_dirs("b-dc-variability")
C3_TMC = NVTA_DIR / "c3-qvdf-reliability" / "output" / "nvta_c3_i95_sb_pm_tmc_validation.csv"

GROUPS = [
    ("I-95 SB PM", "I95_SB", "PM"),
    ("I-95 NB AM", "I95_NB", "AM"),
    ("I-95 NB PM", "I95_NB", "PM"),
    ("I-395 NB AM", "I395_NB", "AM"),
    ("I-395 NB PM", "I395_NB", "PM"),
    ("I-395 SB PM", "I395_SB", "PM"),
]
PRIMARY = "I-95 SB PM"
MIN_DAYS = 8
AICC_SIMPLICITY_THRESHOLD = 2.0
Z95 = float(norm.ppf(0.95))

BLUE = "#2a78d6"
ORANGE = "#eb6834"
GRAY = "#a3a29c"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
GRID = "#e4e3df"


def load_daily_dc() -> pd.DataFrame:
    frames = []
    for label, corridor, period in GROUPS:
        episodes = pd.read_csv(
            CBI / corridor / "05-episode-filtering/daily_episodes_accepted.csv",
            dtype={"tmc_code": "string"},
        )
        episodes["tmc_code"] = episodes["tmc_code"].str.strip().str.upper()
        episodes = episodes[episodes["period"].eq(period) & episodes["demand_capacity_ratio"].gt(0)]
        # One value per TMC-day, as in C3: keep the largest-demand episode.
        episodes = episodes.sort_values("episode_demand").drop_duplicates(["tmc_code", "date"], keep="last")
        episodes["group"] = label
        frames.append(episodes[["group", "tmc_code", "date", "demand_capacity_ratio"]])
    daily = pd.concat(frames, ignore_index=True).rename(columns={"demand_capacity_ratio": "dc"})
    daily["ln_dc"] = np.log(daily["dc"])
    days = daily.groupby(["group", "tmc_code"])["date"].transform("nunique")
    return daily[days.ge(MIN_DAYS)].copy()


def tmc_statistics(daily: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (group, tmc), frame in daily.groupby(["group", "tmc_code"], sort=True):
        ln_dc = frame["ln_dc"].to_numpy(float)
        dc = frame["dc"].to_numpy(float)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            shapiro_p = float(shapiro(ln_dc).pvalue)
        rows.append(
            {
                "group": group,
                "tmc_code": tmc,
                "days": int(len(frame)),
                "mean_dc": float(dc.mean()),
                "mu_ln_dc": float(ln_dc.mean()),
                "sigma_ln_dc": float(ln_dc.std(ddof=1)),
                "skew_ln_dc": float(skew(ln_dc, bias=False)),
                "qq_r2_ln_dc": normal_qq_r2(ln_dc),
                "qq_r2_dc": normal_qq_r2(dc),
                "shapiro_p_ln_dc": shapiro_p,
            }
        )
    return pd.DataFrame(rows)


def standardized(daily: pd.DataFrame) -> pd.DataFrame:
    grouped = daily.groupby(["group", "tmc_code"])
    out = daily.copy()
    out["z_ln"] = (out["ln_dc"] - grouped["ln_dc"].transform("mean")) / grouped["ln_dc"].transform("std")
    out["z_raw"] = (out["dc"] - grouped["dc"].transform("mean")) / grouped["dc"].transform("std")
    return out


def select_model(models: pd.DataFrame) -> str:
    constant = models.loc[models["model"].eq("constant"), "aicc"].iloc[0]
    linear = models.loc[models["model"].eq("linear"), "aicc"].iloc[0]
    return "linear" if constant - linear > AICC_SIMPLICITY_THRESHOLD else "constant"


def sigma_models(tmc: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for scope, frame in [(PRIMARY, tmc[tmc["group"].eq(PRIMARY)]), ("All GP corridor-periods", tmc)]:
        models = fit_sigma_models(frame["mean_dc"].to_numpy(), frame["sigma_ln_dc"].to_numpy())
        models["scope"] = scope
        models["tmcs"] = len(frame)
        models["selected"] = models["model"].eq(select_model(models))
        rows.append(models)
    return pd.concat(rows, ignore_index=True)


def group_summary(tmc: pd.DataFrame) -> pd.DataFrame:
    summary = tmc.groupby("group", sort=False).agg(
        tmcs=("tmc_code", "size"),
        tmc_days=("days", "sum"),
        mean_dc_min=("mean_dc", "min"),
        mean_dc_max=("mean_dc", "max"),
        median_sigma_ln_dc=("sigma_ln_dc", "median"),
        median_qq_r2_ln_dc=("qq_r2_ln_dc", "median"),
        median_qq_r2_dc=("qq_r2_dc", "median"),
        share_shapiro_p_gt_005=("shapiro_p_ln_dc", lambda p: float((p > 0.05).mean())),
    )
    order = [label for label, _, _ in GROUPS]
    return summary.reindex([label for label in order if label in summary.index]).reset_index()


def planning_sigma_check(tmc: pd.DataFrame, form: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """B3: C3 PTI95 with each TMC's own sigma vs a leave-one-TMC-out sigma model."""
    c3 = pd.read_csv(C3_TMC, dtype={"tmc_code": "string"})
    c3 = c3[c3["primary_c3_subset"]].copy()
    primary = tmc[tmc["group"].eq(PRIMARY)]
    rows = []
    for row in c3.itertuples(index=False):
        train = primary[primary["tmc_code"].ne(row.tmc_code)]
        design = np.ones((len(train), 1)) if form == "constant" else np.column_stack([np.ones(len(train)), train["mean_dc"]])
        coefficients = np.linalg.lstsq(design, train["sigma_ln_dc"].to_numpy(float), rcond=None)[0]
        sigma_model = float(coefficients[0] + (coefficients[1] * row.mean_dc if form == "linear" else 0.0))
        # A planning model supplies E[D/C]; the lognormal location follows from it.
        mu_model = float(np.log(row.mean_dc) - 0.5 * sigma_model**2)
        pti_model = 1.0 + row.alpha * np.exp(row.beta * mu_model + Z95 * row.beta * sigma_model)
        rows.append(
            {
                "tmc_code": row.tmc_code,
                "mean_dc": row.mean_dc,
                "own_sigma_ln_dc": row.sigma_ln_dc,
                "planning_sigma_ln_dc_loto": sigma_model,
                "observed_pti95": row.observed_pti95,
                "pti95_own_sigma": row.model_pti95,
                "pti95_planning_sigma": pti_model,
            }
        )
    check = pd.DataFrame(rows)
    metrics = []
    for label, column in [("own TMC sigma (C3)", "pti95_own_sigma"), ("planning sigma, LOTO", "pti95_planning_sigma")]:
        error = check[column] - check["observed_pti95"]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ConstantInputWarning)
            rho = float(spearmanr(check["observed_pti95"], check[column]).statistic)
        metrics.append(
            {"sigma_source": label, "tmcs": len(check), "spearman_rho": rho,
             "mae": float(error.abs().mean()), "bias_model_minus_observed": float(error.mean())}
        )
    return check, pd.DataFrame(metrics)


def plot(daily: pd.DataFrame, tmc: pd.DataFrame, models: pd.DataFrame, output: Path) -> None:
    plt.rcParams.update({"font.size": 9.5, "axes.edgecolor": INK_SECONDARY, "axes.labelcolor": INK,
                         "xtick.color": INK_SECONDARY, "ytick.color": INK_SECONDARY})
    figure, (left, right) = plt.subplots(1, 2, figsize=(10.4, 4.5), constrained_layout=True)

    z = standardized(daily)
    count = len(z)
    theoretical = norm.ppf((np.arange(1, count + 1) - 0.375) / (count + 0.25))
    for column, color, label in [("z_raw", ORANGE, "$x$"), ("z_ln", BLUE, r"$\ln x$")]:
        ordered = np.sort(z[column].to_numpy(float))
        r2 = np.corrcoef(theoretical, ordered)[0, 1] ** 2
        left.scatter(theoretical, ordered, s=9, color=color, alpha=0.75, linewidths=0, label=f"{label}: Q-Q $R^2$ = {r2:.3f}")
    left.plot([-3.2, 3.2], [-3.2, 3.2], color=INK_SECONDARY, ls="--", lw=1.0)
    left.set_xlabel("Standard normal quantile")
    left.set_ylabel("Within-TMC standardized value")
    left.set_title(f"(a) Pooled Q-Q, {tmc['tmc_code'].size} TMCs, {count:,} TMC-days", loc="left", fontsize=10, color=INK)
    left.legend(frameon=False, fontsize=8.5, loc="upper left")

    others = tmc[tmc["group"].ne(PRIMARY)]
    primary = tmc[tmc["group"].eq(PRIMARY)]
    right.scatter(others["mean_dc"], others["sigma_ln_dc"], s=28, color=GRAY, edgecolors="white", linewidths=0.6, label=f"Other GP corridor-periods ({len(others)} TMCs)")
    right.scatter(primary["mean_dc"], primary["sigma_ln_dc"], s=36, color=BLUE, edgecolors="white", linewidths=0.8, zorder=3, label=f"I-95 SB PM ({len(primary)} TMCs)")
    selected = models[models["selected"] & models["scope"].eq("All GP corridor-periods")].iloc[0]
    grid = np.linspace(tmc["mean_dc"].min(), tmc["mean_dc"].max(), 50)
    right.plot(grid, selected["intercept"] + selected["slope"] * grid, color=INK, lw=1.6,
               label=f"All-GP {selected['model']} model")
    right.set_xlabel(r"Mean loading $x = X_E/4\,$h over episode-days")
    right.set_ylabel(r"$\sigma_{\ln x}$ across days")
    right.set_ylim(bottom=0)
    right.set_title("(b) Day-to-day variability vs mean loading", loc="left", fontsize=10, color=INK)
    right.legend(frameon=False, fontsize=8.5, loc="upper right")

    for axis in (left, right):
        axis.grid(color=GRID, lw=0.8)
        axis.set_axisbelow(True)
        axis.spines[["top", "right"]].set_visible(False)
    figure.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    daily = load_daily_dc()
    tmc = tmc_statistics(daily)
    groups = group_summary(tmc)
    models = sigma_models(tmc)
    primary_form = models.loc[models["scope"].eq(PRIMARY) & models["selected"], "model"].iloc[0]
    check, check_metrics = planning_sigma_check(tmc, primary_form)

    tmc.to_csv(OUTPUT / "b_tmc_dc_statistics.csv", index=False)
    groups.to_csv(OUTPUT / "b_group_summary.csv", index=False)
    models.to_csv(OUTPUT / "b_sigma_model_comparison.csv", index=False)
    check.to_csv(OUTPUT / "b_planning_sigma_pti95_check.csv", index=False)
    check_metrics.to_csv(OUTPUT / "b_planning_sigma_pti95_metrics.csv", index=False)
    plot(daily, tmc, models, FIGURES / "nvta_b_dc_lognormal_sigma.png")

    pd.set_option("display.width", 200)
    print(groups.round(3).to_string(index=False))
    print(models.round(4).to_string(index=False))
    print(check_metrics.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
