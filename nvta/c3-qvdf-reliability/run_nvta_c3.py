"""C3: validate QVDF-implied PM reliability against observed I-95 SB travel times.

The analysis is conditional on accepted PM congestion episodes because the
available link-specific QVDF parameters were calibrated on those episodes.
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


CBI = CBI_ROOT / "I95_SB"
RAW_RITIS = RITIS_RAW
PARAMETERS = CBI / "06-qvdf-calibration/qvdf_selected_parameters.csv"
EPISODES = CBI / "05-episode-filtering/daily_episodes_accepted.csv"

OUTPUT, FIGURES = experiment_dirs("c3-qvdf-reliability")

PM_START_MINUTE = 15 * 60
PM_END_MINUTE = 19 * 60
EXPECTED_BINS = 48
MIN_EPISODE_DAYS = 3
Z95 = float(norm.ppf(0.95))
BOOTSTRAP_REPLICATES = 1000
RANDOM_SEED = 395


def normalize_tmc(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.upper()


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    parameters = pd.read_csv(PARAMETERS, dtype={"tmc_code": "string"})
    parameters["tmc_code"] = normalize_tmc(parameters["tmc_code"])
    parameters = parameters[parameters["period"].eq("PM")].copy()
    if parameters["tmc_code"].duplicated().any():
        raise ValueError("Expected one selected PM parameter row per TMC")

    episodes = pd.read_csv(EPISODES, dtype={"tmc_code": "string"})
    episodes["tmc_code"] = normalize_tmc(episodes["tmc_code"])
    episodes = episodes[episodes["period"].eq("PM")].copy()
    episodes["date_local"] = pd.to_datetime(episodes["date"]).dt.date.astype(str)
    episodes = episodes.sort_values(["tmc_code", "date_local", "episode_demand"])
    episodes = episodes.drop_duplicates(["tmc_code", "date_local"], keep="last")

    keep = [
        "tmc_code",
        "date_local",
        "demand_capacity_ratio",
        "P_hr",
        "length_mi",
        "freeflow_speed_mph",
        "network_link_id",
        "road_order",
    ]
    return parameters, episodes[keep]


def read_pm_travel_times(selected_tmcs: set[str]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for chunk in pd.read_csv(
        RAW_RITIS,
        usecols=["tmc_code", "measurement_tstamp", "travel_time_minutes", "speed"],
        dtype={"tmc_code": "string"},
        chunksize=750_000,
    ):
        chunk["tmc_code"] = normalize_tmc(chunk["tmc_code"])
        chunk = chunk[chunk["tmc_code"].isin(selected_tmcs)].copy()
        if chunk.empty:
            continue
        chunk["timestamp_local"] = pd.to_datetime(
            chunk.pop("measurement_tstamp"), errors="coerce"
        )
        chunk["travel_time_min"] = pd.to_numeric(
            chunk.pop("travel_time_minutes"), errors="coerce"
        )
        chunk["speed_mph"] = pd.to_numeric(chunk.pop("speed"), errors="coerce")
        chunk = chunk.dropna(
            subset=["timestamp_local", "travel_time_min", "speed_mph"]
        )
        minute = chunk["timestamp_local"].dt.hour * 60 + chunk["timestamp_local"].dt.minute
        chunk = chunk[
            (chunk["timestamp_local"].dt.weekday < 5)
            & (minute >= PM_START_MINUTE)
            & (minute < PM_END_MINUTE)
        ].copy()
        if not chunk.empty:
            frames.append(chunk)
    if not frames:
        raise RuntimeError("No weekday PM RITIS records found for selected I-95 SB TMCs")
    data = pd.concat(frames, ignore_index=True)
    data["date_local"] = data["timestamp_local"].dt.date.astype(str)
    daily = (
        data.groupby(["tmc_code", "date_local"], as_index=False)
        .agg(
            source_5min_bins=("timestamp_local", "nunique"),
            mean_pm_travel_time_min=("travel_time_min", "mean"),
            mean_pm_speed_mph=("speed_mph", "mean"),
        )
    )
    daily["complete_pm_window"] = daily["source_5min_bins"].eq(EXPECTED_BINS)
    return daily


def build_tmc_metrics(
    parameters: pd.DataFrame, episodes: pd.DataFrame, daily: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    link_day = episodes.merge(
        daily, on=["tmc_code", "date_local"], how="left", validate="one_to_one"
    )
    link_day = link_day.merge(
        parameters[
            [
                "tmc_code",
                "alpha",
                "beta",
                "f_d",
                "n",
                "reliability",
                "calibration_scope",
                "n_episodes",
                "duration_r2",
                "speed_r2",
            ]
        ],
        on="tmc_code",
        how="inner",
        validate="many_to_one",
    )
    link_day["free_flow_travel_time_min"] = (
        link_day["length_mi"] / link_day["freeflow_speed_mph"] * 60.0
    )
    link_day["observed_daily_pm_tti"] = (
        link_day["mean_pm_travel_time_min"]
        / link_day["free_flow_travel_time_min"]
    )
    link_day["analysis_eligible"] = (
        link_day["complete_pm_window"].fillna(False)
        & link_day["demand_capacity_ratio"].gt(0)
        & link_day["observed_daily_pm_tti"].notna()
    )
    link_day["analysis_scope"] = "accepted PM congestion episodes"
    link_day["demand_capacity_basis"] = (
        "episode vehicle demand divided by four-hour PM capacity"
    )

    eligible = link_day[link_day["analysis_eligible"]].copy()
    rows: list[dict] = []
    for tmc, group in eligible.groupby("tmc_code", sort=True):
        group = group.sort_values("date_local")
        first = group.iloc[0]
        dc = group["demand_capacity_ratio"].to_numpy(float)
        log_dc = np.log(dc)
        mu = float(np.mean(log_dc))
        sigma = float(np.std(log_dc, ddof=1)) if len(log_dc) > 1 else np.nan
        alpha = float(first["alpha"])
        beta = float(first["beta"])
        observed_tti = float(group["observed_daily_pm_tti"].mean())
        observed_pti95 = float(group["observed_daily_pm_tti"].quantile(0.95))
        if np.isfinite(sigma):
            model_tti = 1.0 + alpha * np.exp(
                beta * mu + 0.5 * beta * beta * sigma * sigma
            )
            model_pti95 = 1.0 + alpha * np.exp(beta * mu + Z95 * beta * sigma)
        else:
            model_tti = np.nan
            model_pti95 = np.nan
        rows.append(
            {
                "corridor": "I-95 SB",
                "facility": "GP",
                "period": "PM 15:00-19:00",
                "tmc_code": tmc,
                "network_link_id": int(first["network_link_id"]),
                "road_order": float(first["road_order"]),
                "length_mi": float(first["length_mi"]),
                "free_flow_speed_mph": float(first["freeflow_speed_mph"]),
                "accepted_episode_days": int(group["date_local"].nunique()),
                "mean_dc": float(np.mean(dc)),
                "mu_ln_dc": mu,
                "sigma_ln_dc": sigma,
                "alpha": alpha,
                "beta": beta,
                "f_d": float(first["f_d"]),
                "n": float(first["n"]),
                "parameter_reliability": first["reliability"],
                "parameter_scope": first["calibration_scope"],
                "calibration_n_episodes": int(first["n_episodes"]),
                "calibration_duration_r2": float(first["duration_r2"]),
                "calibration_speed_r2": float(first["speed_r2"]),
                "observed_mean_tti": observed_tti,
                "observed_pti95": observed_pti95,
                "observed_gamma95": observed_pti95 / observed_tti,
                "model_mean_tti": model_tti,
                "model_pti95": model_pti95,
                "model_gamma95": model_pti95 / model_tti,
                "pti95_error_model_minus_observed": model_pti95 - observed_pti95,
                "gamma95_error_model_minus_observed": (
                    model_pti95 / model_tti - observed_pti95 / observed_tti
                ),
                "primary_c3_subset": bool(
                    first["reliability"] in {"high", "medium"}
                    and first["calibration_scope"] == "sensor_period"
                    and group["date_local"].nunique() >= MIN_EPISODE_DAYS
                ),
                "analysis_scope": "conditional on accepted PM congestion episodes",
            }
        )
    return link_day, pd.DataFrame(rows).sort_values(["road_order", "tmc_code"])


def safe_corr(x: pd.Series, y: pd.Series, method: str) -> float:
    pair = pd.DataFrame({"x": x, "y": y}).dropna()
    if len(pair) < 3 or pair["x"].nunique() < 2 or pair["y"].nunique() < 2:
        return np.nan
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConstantInputWarning)
        if method == "pearson":
            return float(pearsonr(pair["x"], pair["y"]).statistic)
        return float(spearmanr(pair["x"], pair["y"]).statistic)


def bootstrap_corr(pair: pd.DataFrame, method: str, seed: int) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    values: list[float] = []
    for _ in range(BOOTSTRAP_REPLICATES):
        sample = pair.iloc[rng.integers(0, len(pair), size=len(pair))]
        value = safe_corr(sample["observed"], sample["model"], method)
        if np.isfinite(value):
            values.append(value)
    if not values:
        return np.nan, np.nan
    return tuple(np.quantile(values, [0.025, 0.975]).astype(float))


def summarize(tmc: pd.DataFrame) -> pd.DataFrame:
    subsets = {
        "primary_sensor_high_medium": tmc[tmc["primary_c3_subset"]],
        "all_high_medium": tmc[tmc["parameter_reliability"].isin(["high", "medium"])],
        "all_parameterized": tmc,
    }
    rows: list[dict] = []
    seed = RANDOM_SEED
    for subset_name, subset in subsets.items():
        for metric, observed, model in [
            ("PTI95", "observed_pti95", "model_pti95"),
            ("gamma95", "observed_gamma95", "model_gamma95"),
            ("mean_TTI", "observed_mean_tti", "model_mean_tti"),
        ]:
            pair = subset[[observed, model]].dropna().rename(
                columns={observed: "observed", model: "model"}
            )
            pearson = safe_corr(pair["observed"], pair["model"], "pearson")
            spearman = safe_corr(pair["observed"], pair["model"], "spearman")
            pearson_low, pearson_high = bootstrap_corr(pair, "pearson", seed)
            spearman_low, spearman_high = bootstrap_corr(pair, "spearman", seed + 1)
            error = pair["model"] - pair["observed"]
            rows.append(
                {
                    "subset": subset_name,
                    "metric": metric,
                    "tmcs": int(len(pair)),
                    "accepted_episode_days": int(
                        subset.loc[pair.index, "accepted_episode_days"].sum()
                    ),
                    "pearson_r": pearson,
                    "pearson_bootstrap_95_low": pearson_low,
                    "pearson_bootstrap_95_high": pearson_high,
                    "spearman_rho": spearman,
                    "spearman_bootstrap_95_low": spearman_low,
                    "spearman_bootstrap_95_high": spearman_high,
                    "mae": float(error.abs().mean()),
                    "rmse": float(np.sqrt(np.mean(error**2))),
                    "bias_model_minus_observed": float(error.mean()),
                    "analysis_scope": "conditional on accepted PM congestion episodes",
                }
            )
            seed += 2
    return pd.DataFrame(rows)


def plot_pti95(tmc: pd.DataFrame, output: Path) -> None:
    # Keep the figure link-specific. Corridor fallback parameters remain in the
    # CSV sensitivity results but would visually dominate this comparison.
    tmc = tmc[tmc["parameter_scope"].eq("sensor_period")].copy()
    figure, axis = plt.subplots(figsize=(7.0, 5.6), constrained_layout=True)
    styles = {
        "high": {"color": "#1f77b4", "marker": "o"},
        "medium": {"color": "#f28e2b", "marker": "s"},
        "low": {"color": "#9e9e9e", "marker": "o"},
    }
    for reliability, group in tmc.groupby("parameter_reliability", sort=True):
        style = styles.get(reliability, styles["low"])
        axis.scatter(
            group["observed_pti95"],
            group["model_pti95"],
            s=52,
            alpha=0.82 if reliability != "low" else 0.55,
            color=style["color"],
            marker=style["marker"],
            edgecolors="white",
            linewidths=0.6,
            label=f"{reliability} parameter fit (n={len(group)})",
        )
    values = np.concatenate(
        [tmc["observed_pti95"].to_numpy(float), tmc["model_pti95"].to_numpy(float)]
    )
    lower = max(1.0, float(np.nanmin(values) - 0.05))
    upper = float(np.nanmax(values) + 0.08)
    axis.plot([lower, upper], [lower, upper], color="#222222", ls="--", lw=1.1, label="1:1")
    labels = tmc.assign(abs_error=tmc["pti95_error_model_minus_observed"].abs()).nlargest(2, "abs_error")
    for index, row in enumerate(labels.itertuples(index=False)):
        axis.annotate(
            row.tmc_code,
            (row.observed_pti95, row.model_pti95),
            xytext=(8, 10 + index * 6),
            textcoords="offset points",
            fontsize=8,
            arrowprops={"arrowstyle": "-", "color": "#666666", "lw": 0.6},
        )
    axis.set_xlim(lower, upper)
    axis.set_ylim(lower, upper)
    axis.set_aspect("equal", adjustable="box")
    axis.set_xlabel("Observed PTI95")
    axis.set_ylabel("QVDF-implied PTI95")
    axis.set_title(
        "I-95 South GP PM: observed and QVDF-implied reliability\n"
        "Accepted PM congestion episodes; link-specific parameter fits",
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
    parameters, episodes = load_inputs()
    daily = read_pm_travel_times(set(parameters["tmc_code"]))
    link_day, tmc = build_tmc_metrics(parameters, episodes, daily)
    summary = summarize(tmc)

    tmc.to_csv(OUTPUT / "nvta_c3_i95_sb_pm_tmc_validation.csv", index=False)
    summary.to_csv(OUTPUT / "nvta_c3_i95_sb_pm_summary.csv", index=False)
    link_day.to_csv(OUTPUT / "nvta_c3_i95_sb_pm_link_day_audit.csv", index=False)
    plot_pti95(tmc, FIGURES / "nvta_c3_i95_sb_pm_observed_vs_model_pti95.png")

    print("PM selected parameter rows:", len(parameters))
    print("PM accepted episode-day rows:", len(episodes))
    print("C3 TMC rows:", len(tmc))
    print("Primary C3 TMC rows:", int(tmc["primary_c3_subset"].sum()))
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
