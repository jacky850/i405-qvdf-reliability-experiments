"""Experiment B distribution figure: what the day-to-day loading x looks like.

(a) All B TMC-days: ln x standardized within each TMC, against N(0, 1).
(b) The 10 C1-C5 TMCs: empirical CDF of x with fitted lognormal and normal CDFs.
"""

from __future__ import annotations

from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import lognorm, norm

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
from paths import NVTA_DIR  # noqa: E402
from run_nvta_b import FIGURES, OUTPUT, load_daily_dc, standardized  # noqa: E402

C3 = NVTA_DIR / "c3-qvdf-reliability" / "output"

BLUE = "#2a78d6"
ORANGE = "#eb6834"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
GRID = "#e4e3df"


def c_sample() -> pd.DataFrame:
    day = pd.read_csv(C3 / "nvta_c3_i95_sb_pm_link_day_audit.csv", dtype={"tmc_code": "string"})
    tmc = pd.read_csv(C3 / "nvta_c3_i95_sb_pm_tmc_validation.csv", dtype={"tmc_code": "string"})
    tmc = tmc[tmc["primary_c3_subset"]]
    day = day[day["analysis_eligible"] & day["tmc_code"].isin(set(tmc["tmc_code"]))]
    day = day.merge(tmc[["tmc_code", "road_order"]], on="tmc_code", suffixes=("_day", ""))
    return day.rename(columns={"demand_capacity_ratio": "x"})[["tmc_code", "road_order", "date_local", "x"]]


def style(axis: plt.Axes) -> None:
    axis.grid(color=GRID, lw=0.7)
    axis.set_axisbelow(True)
    axis.spines[["top", "right"]].set_visible(False)


def main() -> None:
    plt.rcParams.update({"font.size": 9.5, "axes.edgecolor": INK_SECONDARY, "axes.labelcolor": INK,
                         "xtick.color": INK_SECONDARY, "ytick.color": INK_SECONDARY})
    daily = standardized(load_daily_dc())
    sample = c_sample()

    figure = plt.figure(figsize=(13.6, 5.6), constrained_layout=True)
    left, right = figure.subfigures(1, 2, width_ratios=[1.0, 2.05])

    # (a) pooled histogram of standardized ln x
    axis = left.subplots()
    z = daily["z_ln"].to_numpy(float)
    axis.hist(z, bins=np.arange(-3.5, 3.51, 0.25), density=True, color=BLUE, alpha=0.75, edgecolor="white", linewidth=0.8)
    grid = np.linspace(-3.5, 3.5, 300)
    axis.plot(grid, norm.pdf(grid), color=INK, lw=1.8, label="Standard normal")
    axis.set_xlabel(r"Standardized $\ln x$ (within TMC)")
    axis.set_ylabel("Density")
    axis.set_title(f"(a) All B TMC-days: {len(z)} days, {daily.groupby(['group', 'tmc_code']).ngroups} TMC-periods", loc="left", fontsize=10, color=INK)
    axis.legend(frameon=False, fontsize=8.5, loc="upper left")
    style(axis)

    # (b) per-TMC empirical CDF with fitted lognormal and normal CDFs
    axes = right.subplots(2, 5, sharey=True)
    fits = []
    for axis, (tmc, frame) in zip(axes.flat, sample.sort_values("road_order").groupby("tmc_code", sort=False)):
        x = np.sort(frame["x"].to_numpy(float))
        n = len(x)
        mu, sigma = np.log(x).mean(), np.log(x).std(ddof=1)
        mean, sd = x.mean(), x.std(ddof=1)
        span = np.linspace(x.min() * 0.7, x.max() * 1.25, 200)
        axis.step(x, np.arange(1, n + 1) / n, where="post", color=INK, lw=1.4, label="Observed")
        axis.plot(span, lognorm.cdf(span, s=sigma, scale=np.exp(mu)), color=BLUE, lw=1.8, label="Lognormal fit")
        axis.plot(span, norm.cdf(span, mean, sd), color=ORANGE, lw=1.4, ls="--", label="Normal fit")
        axis.set_title(f"{tmc} (n = {n})", fontsize=8.5, color=INK)
        axis.tick_params(labelsize=8)
        style(axis)
        fits.append({"tmc_code": tmc, "days": n, "mu_ln_x": mu, "sigma_ln_x": sigma, "mean_x": mean, "sd_x": sd})
    for axis in axes[1]:
        axis.set_xlabel("Loading $x$", fontsize=8.5)
    for axis in axes[:, 0]:
        axis.set_ylabel("Cumulative share of days", fontsize=8.5)
    axes[0, 0].legend(frameon=False, fontsize=7.5, loc="lower right")
    right.suptitle("(b) The 10 C1–C5 TMCs, I-95 SB PM: distribution of $x$ across congestion days",
                   x=0.01, ha="left", fontsize=10, color=INK)

    figure.savefig(FIGURES / "nvta_b_dc_distribution.png", dpi=200, bbox_inches="tight")
    plt.close(figure)
    pd.DataFrame(fits).to_csv(OUTPUT / "b_c_sample_distribution_fits.csv", index=False)
    print(pd.DataFrame(fits).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
