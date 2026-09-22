from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


PRIMARY_BASIS = "duration_qvdf_capacity_equivalent_hours"
THRESHOLDS = np.array([0.90, 0.95, 1.00, 1.05, 1.10])


def style_axis(ax: plt.Axes) -> None:
    ax.set_xticks(THRESHOLDS)
    ax.set_xticklabels(
        [r"$0.90v_c$", r"$0.95v_c$", r"$1.00v_c$", r"$1.05v_c$", r"$1.10v_c$"]
    )
    ax.set_xlim(0.885, 1.115)
    ax.axvline(1.00, color="0.48", linestyle="--", linewidth=1.1, zorder=0)
    ax.grid(axis="y", color="0.88", linewidth=0.8)
    ax.margins(y=0.22)
    ax.tick_params(axis="both", labelsize=10)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def plot_series(
    ax: plt.Axes,
    x: np.ndarray,
    y: np.ndarray,
    title: str,
    ylabel: str,
    decimals: int,
) -> None:
    ax.plot(x, y, color="#1769aa", marker="o", linewidth=2.2, markersize=6)
    for x_value, y_value in zip(x, y):
        ax.annotate(
            f"{y_value:.{decimals}f}",
            (x_value, y_value),
            xytext=(0, 8),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=9,
            color="0.20",
        )
    ax.set_title(title, fontsize=13)
    ax.set_ylabel(ylabel, fontsize=11)
    style_axis(ax)


def make_sensitivity_figure(root: Path) -> None:
    episodes = pd.read_csv(root / "results" / "step3_threshold_episodes.csv")
    support = pd.read_csv(root / "results" / "step3_common_support.csv")
    common = support.loc[support["common_support"], ["link_id", "date_local"]]
    episodes = episodes.merge(common, on=["link_id", "date_local"], how="inner")

    medians = (
        episodes.groupby("threshold_multiplier")
        .agg(
            median_P_h=("duration_h", "median"),
            median_D_over_C_h=("capacity_equivalent_hours", "median"),
        )
        .reindex(THRESHOLDS)
        .reset_index()
    )
    fit = pd.read_csv(root / "results" / "step4_qvdf_fit_summary.csv")
    fit = fit[
        fit["scope"].eq("pooled") & fit["fit_basis"].eq(PRIMARY_BASIS)
    ].set_index("threshold_multiplier").reindex(THRESHOLDS).reset_index()

    x = THRESHOLDS
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    plot_series(
        axes[0, 0], x, medians["median_P_h"].to_numpy(float),
        r"Median congestion duration $P$", r"$P$ (hours)", 2,
    )
    plot_series(
        axes[0, 1], x, medians["median_D_over_C_h"].to_numpy(float),
        r"Median $D/C$", r"$D/C$ (hours)", 2,
    )
    plot_series(
        axes[1, 0], x, fit["fd"].to_numpy(float),
        r"Fitted parameter $f_d$", r"$f_d$", 3,
    )
    plot_series(
        axes[1, 1], x, fit["n"].to_numpy(float),
        r"Fitted exponent $n$", r"$n$", 3,
    )
    axes[1, 0].set_xlabel(r"Congestion threshold $v_{th}=a v_c$", fontsize=11)
    axes[1, 1].set_xlabel(r"Congestion threshold $v_{th}=a v_c$", fontsize=11)
    fig.suptitle(
        "Experiment A: Sensitivity to the Congestion Speed Threshold",
        fontsize=16,
    )
    fig.savefig(
        root / "figures" / "threshold_parameter_sensitivity.png",
        dpi=220,
        bbox_inches="tight",
    )
    plt.close(fig)


def make_duration_fit_figure(root: Path) -> None:
    predictions = pd.read_csv(root / "results" / "step4_qvdf_predictions.csv")
    predictions = predictions[
        predictions["scope"].eq("pooled")
        & predictions["fit_basis"].eq(PRIMARY_BASIS)
    ]
    fig, axes = plt.subplots(
        1, 5, figsize=(17, 3.5), sharex=True, sharey=True, constrained_layout=True
    )
    for ax, (multiplier, group) in zip(
        axes, predictions.groupby("threshold_multiplier")
    ):
        ax.scatter(group["x_value"], group["observed_duration_h"], s=18, alpha=0.65)
        order = np.argsort(group["x_value"].to_numpy())
        ax.plot(
            group["x_value"].to_numpy()[order],
            group["predicted_duration_h"].to_numpy()[order],
            color="tab:red",
            linewidth=2,
        )
        ax.set_title(f"{multiplier:.2f} × $v_c$")
        ax.set_xlabel("$D/C$ (hours)")
        ax.grid(alpha=0.2)
    axes[0].set_ylabel("Congestion duration $P$ (hours)")
    fig.suptitle("Pooled duration relationship: $P=f_d(D/C)^n$")
    fig.savefig(root / "figures" / "duration_vs_dc.png", dpi=200)
    plt.close(fig)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    (root / "figures").mkdir(parents=True, exist_ok=True)
    make_sensitivity_figure(root)
    make_duration_fit_figure(root)
    print(f"Saved finalized figures to: {root / 'figures'}")


if __name__ == "__main__":
    main()
