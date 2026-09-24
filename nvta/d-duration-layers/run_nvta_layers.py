"""D: congestion duration at nested speed cutoffs (0.75, 0.50, 0.25 of v_f).

P_r is the total time on a TMC-day with smoothed speed below r * v_f inside
the analysis window. Unlike the A2 longest-episode rule, total time is nested:
P_0.25 <= P_0.50 <= P_0.75 on every TMC-day. Each TMC-day also gets its daily
TTI over the same window, so the layers can be compared against travel time.

Questions:
1. How much variation does each layer carry (share of zero days, spread)?
2. Do the layers carry the same information (correlation between layers)?
3. Which layer tracks daily travel time most closely?
"""

from __future__ import annotations

from pathlib import Path
import sys
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import ConstantInputWarning, spearmanr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import experiment_dirs  # noqa: E402
from ritis_io import free_flow_speed, gp_corridor, read_ritis, ritis_length, smoothed_speed  # noqa: E402


OUTPUT, FIGURES = experiment_dirs("d-duration-layers")

CORRIDORS = [
    {"label": "I-95 NB AM", "corridor": "I95_NB", "start": 5 * 60, "end": 10 * 60, "file": "i95_nb_am"},
    {"label": "I-95 SB PM", "corridor": "I95_SB", "start": 12 * 60, "end": 21 * 60, "file": "i95_sb_pm"},
]
RATIOS = [0.75, 0.50, 0.25]
BIN_H = 5 / 60

# Ordered severity -> one hue, light to dark.
RATIO_COLORS = {0.75: "#8fbcee", 0.50: "#2a78d6", 0.25: "#0b3d7a"}
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
GRID = "#e4e3df"


def spearman(x: pd.Series, y: pd.Series) -> float:
    pair = pd.DataFrame({"x": x, "y": y}).dropna()
    if pair["x"].nunique() < 2 or pair["y"].nunique() < 2:
        return float("nan")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConstantInputWarning)
        return float(spearmanr(pair["x"], pair["y"]).statistic)


def within_tmc(frame: pd.DataFrame, column: str) -> pd.Series:
    return frame[column] - frame.groupby("tmc_code")[column].transform("mean")


def tmc_day_layers(spec: dict) -> pd.DataFrame:
    tmcs = gp_corridor(spec["corridor"])
    data = read_ritis(set(tmcs["tmc_code"]))
    vf = free_flow_speed(data)
    length = ritis_length(data)
    window = data[(data["minute"] >= spec["start"]) & (data["minute"] < spec["end"])].copy()
    window["speed_smooth"] = smoothed_speed(window)
    window = window.join(vf, on="tmc_code").join(length, on="tmc_code")
    window["t0_min"] = window["length_mi"] / window["vf_mph"] * 60.0
    expected_bins = (spec["end"] - spec["start"]) // 5

    agg = {"bins": ("minute", "nunique"), "tti": ("travel_time_minutes", "mean"), "t0": ("t0_min", "first")}
    for ratio in RATIOS:
        window[f"below_{ratio}"] = window["speed_smooth"] < ratio * window["vf_mph"]
        agg[f"P_{ratio:.2f}"] = (f"below_{ratio}", "sum")
    day = window.groupby(["tmc_code", "date_local"]).agg(**agg).reset_index()
    day = day[day["bins"].eq(expected_bins)].copy()
    for ratio in RATIOS:
        day[f"P_{ratio:.2f}"] = day[f"P_{ratio:.2f}"] * BIN_H
    day["tti"] = day["tti"] / day["t0"]
    day = day.merge(tmcs[["tmc_code", "road_order"]], on="tmc_code").merge(vf.reset_index(), on="tmc_code")
    day.insert(0, "corridor_period", spec["label"])
    return day.drop(columns=["bins", "t0"])


def summarize(day: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    layer_rows, pair_rows = [], []
    for label, frame in day.groupby("corridor_period", sort=False):
        for ratio in RATIOS:
            column = f"P_{ratio:.2f}"
            values = frame[column]
            layer_rows.append(
                {
                    "corridor_period": label,
                    "cutoff": f"{ratio:.2f} vf",
                    "tmc_days": int(len(frame)),
                    "share_tmc_days_P_gt_0": float((values > 0).mean()),
                    "mean_P_h": float(values.mean()),
                    "sd_P_h": float(values.std(ddof=1)),
                    "cv_P": float(values.std(ddof=1) / values.mean()) if values.mean() > 0 else float("nan"),
                    "spearman_P_vs_daily_TTI": spearman(values, frame["tti"]),
                    "spearman_within_TMC_P_vs_TTI": spearman(within_tmc(frame, column), within_tmc(frame, "tti")),
                }
            )
        for low, high in [(0.25, 0.50), (0.50, 0.75), (0.25, 0.75)]:
            a, b = frame[f"P_{low:.2f}"], frame[f"P_{high:.2f}"]
            active = b > 0
            pair_rows.append(
                {
                    "corridor_period": label,
                    "pair": f"P_{low:.2f} vs P_{high:.2f}",
                    "spearman_all_tmc_days": spearman(a, b),
                    "spearman_where_broader_P_gt_0": spearman(a[active], b[active]),
                    "share_narrower_P_gt_0_where_broader_P_gt_0": float((a[active] > 0).mean()),
                    "median_share_severe_where_broader_P_gt_0": float((a[active] / b[active]).median()),
                    "nested_everywhere": bool((a <= b + 1e-9).all()),
                }
            )
    return pd.DataFrame(layer_rows), pd.DataFrame(pair_rows)


def style(axis: plt.Axes) -> None:
    axis.grid(color=GRID, lw=0.8)
    axis.set_axisbelow(True)
    axis.spines[["top", "right"]].set_visible(False)


def plot(frame: pd.DataFrame, layers: pd.DataFrame, pairs: pd.DataFrame, label: str, output: Path) -> None:
    plt.rcParams.update({"font.size": 9.5, "axes.edgecolor": INK_SECONDARY, "axes.labelcolor": INK,
                         "xtick.color": INK_SECONDARY, "ytick.color": INK_SECONDARY})
    figure, axes = plt.subplots(1, 3, figsize=(14.4, 4.9), constrained_layout=True)
    stats = layers[layers["corridor_period"].eq(label)].set_index("cutoff")
    pair = pairs[pairs["corridor_period"].eq(label)].set_index("pair")
    n = len(frame)

    # (a) distribution of each layer, zeros included
    axis = axes[0]
    for ratio in RATIOS:
        values = np.sort(frame[f"P_{ratio:.2f}"].to_numpy(float))
        share = stats.loc[f"{ratio:.2f} vf", "share_tmc_days_P_gt_0"]
        axis.step(values, np.arange(1, n + 1) / n, where="post", color=RATIO_COLORS[ratio], lw=2,
                  label=f"$P_{{{ratio:.2f}}}$: {share:.0%} of TMC-days > 0")
    axis.set_xlabel("Congestion duration P (h)")
    axis.set_ylabel("Share of TMC-days at or below P")
    axis.set_title(f"(a) Distribution of P at each cutoff ({n} TMC-days)", loc="left", fontsize=10, color=INK)
    axis.legend(frameon=False, fontsize=8.5, loc="lower right")

    # (b), (c) layer against layer
    for axis, (low, high, tag) in zip([axes[1], axes[2]], [(0.25, 0.50, "b"), (0.50, 0.75, "c")]):
        x, y = frame[f"P_{high:.2f}"], frame[f"P_{low:.2f}"]
        axis.scatter(x, y, s=16, color=RATIO_COLORS[low], alpha=0.55, edgecolors="none")
        top = float(max(x.max(), 0.5)) * 1.03
        axis.plot([0, top], [0, top], color=INK_SECONDARY, ls="--", lw=1)
        axis.text(top, top, "equal ", ha="right", va="bottom", fontsize=8.5, color=INK_SECONDARY)
        row = pair.loc[f"P_{low:.2f} vs P_{high:.2f}"]
        axis.set_xlim(-0.05 * top, top * 1.02)
        axis.set_ylim(-0.05 * top, top * 1.02)
        axis.set_xlabel(f"$P_{{{high:.2f}}}$ (h)")
        axis.set_ylabel(f"$P_{{{low:.2f}}}$ (h)")
        axis.set_title(
            f"({tag}) $P_{{{low:.2f}}}$ vs $P_{{{high:.2f}}}$: Spearman {row['spearman_all_tmc_days']:.2f}\n"
            f"$P_{{{low:.2f}}}$ > 0 on {row['share_narrower_P_gt_0_where_broader_P_gt_0']:.0%} of the TMC-days with $P_{{{high:.2f}}}$ > 0",
            loc="left", fontsize=10, color=INK,
        )

    for axis in axes.flat:
        style(axis)
    figure.suptitle(f"{label}, GP lanes, 23 weekdays: congestion duration below 0.75, 0.50 and 0.25 $v_f$",
                    x=0.01, ha="left", fontsize=11, color=INK)
    figure.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    day = pd.concat([tmc_day_layers(spec) for spec in CORRIDORS], ignore_index=True)
    layers, pairs = summarize(day)
    day.to_csv(OUTPUT / "d_tmc_day_layers.csv", index=False)
    layers.to_csv(OUTPUT / "d_layer_summary.csv", index=False)
    pairs.to_csv(OUTPUT / "d_layer_pairs.csv", index=False)
    for spec in CORRIDORS:
        frame = day[day["corridor_period"].eq(spec["label"])]
        plot(frame, layers, pairs, spec["label"], FIGURES / f"nvta_d_layers_{spec['file']}.png")

    pd.set_option("display.width", 220)
    print(layers.round(3).to_string(index=False))
    print(pairs.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
