"""Run NVTA Experiment A on day-level I-95 NB GP and managed-lane speeds.

The workflow retains the structure of the PeMS threshold experiment while
adding the one transformation required by the RITIS source:

    observed speed -> inverse S3 flow -> episode D -> D/C.

The S3 parameters are fixed before the threshold sweep.  For each tested
threshold, the code re-detects congestion, recomputes P and D/C, and then fits
a separate duration relation P = f_d (D/C)^n on common link-day support.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "nvta_experiment_a_i95_nb_am.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    return parser.parse_args()


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def normalized_tmc(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.upper()


def project_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def build_parameter_table(mapping: pd.DataFrame, config: dict) -> pd.DataFrame:
    """Build either the legacy facility priors or audited TMC-level inputs."""
    mode = config.get("parameter_mode", "facility_priors")
    free_flow_by_tmc: dict[str, float] = {}
    capacity_by_tmc: dict[str, tuple[float, float, int]] = {}

    if mode == "tmc_offpeak_p85_cube_am_capacity":
        sources = config["per_tmc_parameter_sources"]
        free_flow = pd.read_csv(project_path(sources["free_flow_audit_csv"]))
        capacity = pd.read_csv(project_path(sources["capacity_audit_csv"]))
        free_flow["tmc_code"] = normalized_tmc(free_flow["tmc_code"])
        capacity["tmc"] = normalized_tmc(capacity["tmc"])
        if free_flow["tmc_code"].duplicated().any() or capacity["tmc"].duplicated().any():
            raise ValueError("TMC-level parameter audit contains duplicate TMC rows")
        free_flow_by_tmc = free_flow.set_index("tmc_code")[
            "recommended_calibration_vf_mph"
        ].astype(float).to_dict()
        capacity_by_tmc = {
            row.tmc: (
                float(row.recommended_capacity_vphpl),
                float(row.recommended_capacity_vph_link),
                int(row.lanes),
            )
            for row in capacity.itertuples(index=False)
        }
        selected = set(mapping["tmc"])
        missing_vf = sorted(selected - set(free_flow_by_tmc))
        missing_capacity = sorted(selected - set(capacity_by_tmc))
        if missing_vf or missing_capacity:
            raise ValueError(
                f"Missing audited parameters: vf={missing_vf}, capacity={missing_capacity}"
            )
    elif mode != "facility_priors":
        raise ValueError(f"Unsupported parameter_mode: {mode}")

    parameter_rows = []
    for row in mapping.itertuples(index=False):
        prior = config["facility_fd_priors"][row.facility]
        if mode == "tmc_offpeak_p85_cube_am_capacity":
            free_flow = free_flow_by_tmc[row.tmc]
            capacity_lane, capacity_link, lanes = capacity_by_tmc[row.tmc]
            if lanes != int(row.net_lanes):
                raise ValueError(f"Lane mismatch for {row.tmc}: {lanes} vs {row.net_lanes}")
            if not np.isclose(capacity_link, capacity_lane * lanes):
                raise ValueError(f"Capacity identity failed for {row.tmc}")
            parameter_source = (
                "TMC weekday off-peak observed-speed P85; Cube AM IAMHRLNCAP/IAMHRLKCAP"
            )
        else:
            free_flow = float(prior["free_flow_speed_mph"])
            capacity_lane = float(prior["capacity_vphpl"])
            lanes = int(row.net_lanes)
            capacity_link = capacity_lane * lanes
            parameter_source = prior["source"]
        m = float(prior["s3_m"])
        parameter_rows.append(
            {
                "corridor": row.corridor,
                "facility": row.facility,
                "tmc_code": row.tmc,
                "road_order": float(row.road_order),
                "network_link_id": int(row.net_link_id),
                "length_mi": float(row.miles),
                "lanes": lanes,
                "free_flow_speed_mph": free_flow,
                "capacity_speed_mph": free_flow * 2.0 ** (-2.0 / m),
                "capacity_vphpl": capacity_lane,
                "capacity_vph_link": capacity_link,
                "s3_m": m,
                "parameter_source": parameter_source,
            }
        )
    return pd.DataFrame(parameter_rows)


def inverse_s3_flow(
    speed_mph: np.ndarray,
    free_flow_speed_mph: float,
    capacity_vphpl: float,
    m: float,
) -> np.ndarray:
    """Congested-branch S3 inversion, returning veh/h/lane."""
    speed_at_capacity = free_flow_speed_mph * 2.0 ** (-2.0 / m)
    critical_density = capacity_vphpl / speed_at_capacity
    speed = np.clip(np.asarray(speed_mph, dtype=float), 1.0, 0.99 * free_flow_speed_mph)
    ratio = np.maximum((free_flow_speed_mph / speed) ** (m / 2.0) - 1.0, 1e-8)
    density = critical_density * ratio ** (1.0 / m)
    return np.minimum(density * speed, capacity_vphpl)


def read_selected_speeds(config: dict, selected_tmcs: set[str]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    usecols = ["tmc_code", "measurement_tstamp", "speed"]
    for chunk in pd.read_csv(
        config["raw_speed_csv"],
        usecols=usecols,
        dtype={"tmc_code": "string"},
        chunksize=750_000,
    ):
        chunk["tmc_code"] = normalized_tmc(chunk["tmc_code"])
        chunk = chunk[chunk["tmc_code"].isin(selected_tmcs)].copy()
        if chunk.empty:
            continue
        chunk["timestamp_local"] = pd.to_datetime(
            chunk.pop("measurement_tstamp"), errors="coerce"
        )
        chunk["speed_mph"] = pd.to_numeric(chunk.pop("speed"), errors="coerce")
        chunk = chunk.dropna(subset=["timestamp_local", "speed_mph"])
        chunk = chunk[chunk["timestamp_local"].dt.weekday < 5]
        frames.append(chunk)
    if not frames:
        raise RuntimeError("No selected weekday speed records were found")
    raw = pd.concat(frames, ignore_index=True)
    raw["date_local"] = raw["timestamp_local"].dt.date.astype(str)
    raw["timestamp_15min"] = raw["timestamp_local"].dt.floor(
        f"{int(config['analysis_interval_minutes'])}min"
    )
    aggregated = (
        raw.groupby(["tmc_code", "date_local", "timestamp_15min"], as_index=False)
        .agg(speed_mph=("speed_mph", "mean"), source_observations=("speed_mph", "size"))
    )
    aggregated = aggregated[
        aggregated["source_observations"]
        >= int(config["minimum_source_observations_per_interval"])
    ].copy()
    aggregated["minute_of_day"] = (
        aggregated["timestamp_15min"].dt.hour * 60
        + aggregated["timestamp_15min"].dt.minute
    )
    return aggregated.sort_values(
        ["tmc_code", "date_local", "timestamp_15min"]
    ).reset_index(drop=True)


def prepare_inputs(config: dict) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    mapping = pd.read_csv(config["corridor_mapping_csv"])
    mapping["tmc"] = normalized_tmc(mapping["tmc"])
    mapping = mapping[mapping["corridor"].isin(config["corridors"])].copy()
    excluded_tmcs = {value.strip().upper() for value in config.get("excluded_tmcs", [])}
    mapping = mapping[~mapping["tmc"].isin(excluded_tmcs)].copy()
    mapping = mapping.sort_values(["corridor", "road_order", "tmc"]).drop_duplicates(
        ["corridor", "tmc"]
    )
    if mapping.empty:
        raise RuntimeError("No TMCs matched the requested corridors")

    parameters = build_parameter_table(mapping, config)
    speeds = read_selected_speeds(config, set(parameters["tmc_code"]))
    data = speeds.merge(parameters, on="tmc_code", how="inner", validate="many_to_one")
    data["flow_vphpl_s3"] = np.nan
    for tmc, group in data.groupby("tmc_code"):
        idx = group.index
        parameter = group.iloc[0]
        data.loc[idx, "flow_vphpl_s3"] = inverse_s3_flow(
            group["speed_mph"].to_numpy(float),
            float(parameter["free_flow_speed_mph"]),
            float(parameter["capacity_vphpl"]),
            float(parameter["s3_m"]),
        )
    data["flow_vph_link_s3"] = data["flow_vphpl_s3"] * data["lanes"]

    expected_bins = 24 * 60 // int(config["analysis_interval_minutes"])
    coverage = (
        data.groupby(
            ["corridor", "facility", "tmc_code", "date_local"], as_index=False
        )
        .agg(
            observed_15min_bins=("timestamp_15min", "nunique"),
            minimum_speed_mph=("speed_mph", "min"),
            mean_speed_mph=("speed_mph", "mean"),
            mean_s3_flow_vph_link=("flow_vph_link_s3", "mean"),
        )
    )
    coverage["expected_15min_bins"] = expected_bins
    coverage["complete_day"] = coverage["observed_15min_bins"] == expected_bins
    return parameters, data, coverage


def interpolate_crossing(
    minute: np.ndarray, speed: np.ndarray, left: int, right: int, cutoff: float
) -> float:
    if speed[right] == speed[left]:
        return float(minute[right])
    fraction = np.clip(
        (cutoff - speed[left]) / (speed[right] - speed[left]), 0.0, 1.0
    )
    return float(minute[left] + fraction * (minute[right] - minute[left]))


def find_episodes(
    minute: np.ndarray, smoothed_speed: np.ndarray, cutoff: float, hysteresis_bins: int
) -> list[dict]:
    episodes: list[dict] = []
    i = 0
    n = len(smoothed_speed)
    while i < n:
        if smoothed_speed[i] >= cutoff:
            i += 1
            continue
        start = i
        end = i
        while end < n - 1:
            next_index = end + 1
            if smoothed_speed[next_index] >= cutoff:
                stop = min(next_index + hysteresis_bins, n)
                if np.all(smoothed_speed[next_index:stop] >= cutoff):
                    break
            end += 1
        t0 = (
            interpolate_crossing(minute, smoothed_speed, start - 1, start, cutoff)
            if start > 0
            else float(minute[0])
        )
        t3 = (
            interpolate_crossing(minute, smoothed_speed, end, end + 1, cutoff)
            if end < n - 1
            else float(minute[-1] + 15)
        )
        minimum_index = start + int(np.argmin(smoothed_speed[start : end + 1]))
        episodes.append(
            {
                "start_index": start,
                "end_index": end,
                "minimum_index": minimum_index,
                "t0_minute": t0,
                "t3_minute": t3,
                "duration_h": (t3 - t0) / 60.0,
                "touches_data_start": start == 0,
                "touches_data_end": end == n - 1,
            }
        )
        i = end + 1
    return episodes


def detect_threshold_episodes(data: pd.DataFrame, config: dict) -> pd.DataFrame:
    interval_h = float(config["analysis_interval_minutes"]) / 60.0
    smooth_bins = int(config["smoothing_bins"])
    hysteresis_bins = max(
        1,
        int(round(config["hysteresis_minutes"] / config["analysis_interval_minutes"])),
    )
    period_start = int(config["analysis_start_minute"])
    period_end = int(config["analysis_end_minute"])
    threshold_basis = config.get("threshold_speed_basis", "capacity_speed")
    if threshold_basis not in {"capacity_speed", "free_flow_speed"}:
        raise ValueError(f"Unsupported threshold_speed_basis: {threshold_basis}")
    rows: list[dict] = []

    for (corridor, facility, tmc, date), group in data.groupby(
        ["corridor", "facility", "tmc_code", "date_local"], sort=True
    ):
        group = group.sort_values("minute_of_day").reset_index(drop=True)
        minute = group["minute_of_day"].to_numpy(float)
        speed = group["speed_mph"].to_numpy(float)
        smoothed = (
            pd.Series(speed)
            .rolling(smooth_bins, center=True, min_periods=1)
            .mean()
            .to_numpy()
        )
        vc = float(group["capacity_speed_mph"].iloc[0])
        vf = float(group["free_flow_speed_mph"].iloc[0])
        capacity_link = float(group["capacity_vph_link"].iloc[0])
        threshold_reference_speed = vc if threshold_basis == "capacity_speed" else vf
        base = {
            "corridor": corridor,
            "facility": facility,
            "tmc_code": tmc,
            "date_local": date,
            "road_order": float(group["road_order"].iloc[0]),
            "length_mi": float(group["length_mi"].iloc[0]),
            "lanes": int(group["lanes"].iloc[0]),
            "free_flow_speed_mph": vf,
            "capacity_speed_mph": vc,
            "capacity_vph_link": capacity_link,
            "observed_15min_bins": int(len(group)),
        }
        for multiplier in map(float, config["speed_threshold_multipliers"]):
            cutoff = multiplier * threshold_reference_speed
            candidates = []
            for episode in find_episodes(minute, smoothed, cutoff, hysteresis_bins):
                trough_minute = minute[episode["minimum_index"]]
                if not period_start <= trough_minute < period_end:
                    continue
                if episode["duration_h"] < float(config["minimum_episode_hours"]):
                    continue
                candidates.append(episode)

            threshold_base = {
                **base,
                "threshold_multiplier": multiplier,
                "threshold_basis": threshold_basis,
                "threshold_speed_mph": cutoff,
                "threshold_speed_ratio_to_vf": cutoff / vf,
                "threshold_speed_ratio_to_vc": cutoff / vc,
            }
            if not candidates:
                rows.append(
                    {
                        **threshold_base,
                        "episode_identified": False,
                        "duration_h": 0.0,
                        "demand_veh_link": 0.0,
                        "d_over_c_h": 0.0,
                        "episode_start_minute": np.nan,
                        "episode_end_minute": np.nan,
                        "minimum_speed_mph": np.nan,
                        "minimum_speed_minute": np.nan,
                        "touches_data_start": False,
                        "touches_data_end": False,
                    }
                )
                continue

            episode = max(
                candidates,
                key=lambda item: (
                    item["duration_h"],
                    -smoothed[item["minimum_index"]],
                    -item["t0_minute"],
                ),
            )
            within = (minute >= episode["t0_minute"]) & (minute <= episode["t3_minute"])
            demand = float(group.loc[within, "flow_vph_link_s3"].sum() * interval_h)
            rows.append(
                {
                    **threshold_base,
                    "episode_identified": True,
                    "duration_h": float(episode["duration_h"]),
                    "demand_veh_link": demand,
                    "d_over_c_h": demand / capacity_link,
                    "episode_start_minute": float(episode["t0_minute"]),
                    "episode_end_minute": float(episode["t3_minute"]),
                    "minimum_speed_mph": float(smoothed[episode["minimum_index"]]),
                    "minimum_speed_minute": float(minute[episode["minimum_index"]]),
                    "touches_data_start": bool(episode["touches_data_start"]),
                    "touches_data_end": bool(episode["touches_data_end"]),
                }
            )
    return pd.DataFrame(rows).sort_values(
        ["corridor", "threshold_multiplier", "road_order", "date_local"]
    ).reset_index(drop=True)


def build_common_support(episodes: pd.DataFrame, config: dict) -> pd.DataFrame:
    eligible = (
        episodes["episode_identified"]
        & ~episodes["touches_data_start"]
        & ~episodes["touches_data_end"]
        & (episodes["d_over_c_h"] > 0)
    )
    frame = episodes.assign(eligible=eligible)
    keys = ["corridor", "facility", "tmc_code", "date_local"]
    pivot = frame.pivot_table(
        index=keys,
        columns="threshold_multiplier",
        values="eligible",
        aggfunc="first",
        fill_value=False,
    )
    multipliers = list(map(float, config["speed_threshold_multipliers"]))
    for multiplier in multipliers:
        if multiplier not in pivot.columns:
            pivot[multiplier] = False
    pivot = pivot[multipliers]
    pivot["common_support"] = pivot.all(axis=1)
    pivot = pivot.reset_index()
    pivot.columns = keys + [f"eligible_at_{value:.2f}" for value in multipliers] + [
        "common_support"
    ]
    return pivot


def fit_power_curve(x: np.ndarray, y: np.ndarray, config: dict) -> dict:
    grid = np.arange(
        float(config["fit_n_min"]),
        float(config["fit_n_max"]) + float(config["fit_n_step"]) / 2.0,
        float(config["fit_n_step"]),
    )
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    powered = x[:, None] ** grid[None, :]
    fd = np.sum(powered * y[:, None], axis=0) / np.sum(powered * powered, axis=0)
    predictions = powered * fd[None, :]
    sse = np.sum((y[:, None] - predictions) ** 2, axis=0)
    best = int(np.argmin(sse))
    yhat = predictions[:, best]
    sst = float(np.sum((y - y.mean()) ** 2))
    return {
        "fd": float(fd[best]),
        "n": float(grid[best]),
        "r_squared": float(1.0 - sse[best] / sst) if sst > 0 else np.nan,
        "rmse_h": float(np.sqrt(np.mean((y - yhat) ** 2))),
        "n_at_boundary": best in {0, len(grid) - 1},
        "predicted": yhat,
    }


def fit_thresholds(
    episodes: pd.DataFrame, support: pd.DataFrame, config: dict
) -> tuple[pd.DataFrame, pd.DataFrame]:
    support_keys = support.loc[
        support["common_support"],
        ["corridor", "facility", "tmc_code", "date_local"],
    ]
    fit_data = episodes.merge(
        support_keys,
        on=["corridor", "facility", "tmc_code", "date_local"],
        how="inner",
    )
    summary_rows: list[dict] = []
    prediction_rows: list[dict] = []
    minimum = int(config["minimum_fit_observations"])

    for (corridor, facility), corridor_data in episodes.groupby(
        ["corridor", "facility"], sort=True
    ):
        common = fit_data[
            (fit_data["corridor"] == corridor) & (fit_data["facility"] == facility)
        ]
        for multiplier in map(float, config["speed_threshold_multipliers"]):
            group = common[np.isclose(common["threshold_multiplier"], multiplier)].copy()
            base = {
                "corridor": corridor,
                "facility": facility,
                "threshold_multiplier": multiplier,
                "common_support_observations": int(len(group)),
                "common_support_tmcs": int(group["tmc_code"].nunique()),
                "median_duration_h": float(group["duration_h"].median()) if len(group) else np.nan,
                "median_d_over_c_h": float(group["d_over_c_h"].median()) if len(group) else np.nan,
            }
            if len(group) < minimum:
                summary_rows.append(
                    {
                        **base,
                        "fit_status": "insufficient_common_support",
                        "fd": np.nan,
                        "n": np.nan,
                        "r_squared": np.nan,
                        "rmse_h": np.nan,
                        "n_at_boundary": False,
                    }
                )
                continue
            fit = fit_power_curve(
                group["d_over_c_h"].to_numpy(float),
                group["duration_h"].to_numpy(float),
                config,
            )
            summary_rows.append(
                {
                    **base,
                    "fit_status": "fitted",
                    "fd": fit["fd"],
                    "n": fit["n"],
                    "r_squared": fit["r_squared"],
                    "rmse_h": fit["rmse_h"],
                    "n_at_boundary": fit["n_at_boundary"],
                }
            )
            for (_, row), prediction in zip(group.iterrows(), fit["predicted"]):
                prediction_rows.append(
                    {
                        "corridor": corridor,
                        "facility": facility,
                        "tmc_code": row["tmc_code"],
                        "date_local": row["date_local"],
                        "threshold_multiplier": multiplier,
                        "d_over_c_h": row["d_over_c_h"],
                        "observed_duration_h": row["duration_h"],
                        "predicted_duration_h": float(prediction),
                        "residual_h": float(row["duration_h"] - prediction),
                    }
                )

    summary = pd.DataFrame(summary_rows)
    for (corridor, facility), group in summary.groupby(["corridor", "facility"]):
        fitted = group[group["fit_status"] == "fitted"]
        baseline = fitted[np.isclose(fitted["threshold_multiplier"], 1.0)]
        if baseline.empty:
            continue
        baseline = baseline.iloc[0]
        mask = (summary["corridor"] == corridor) & (summary["facility"] == facility)
        summary.loc[mask, "fd_change_vs_1pct"] = (
            summary.loc[mask, "fd"] / baseline["fd"] - 1.0
        ) * 100.0
        summary.loc[mask, "n_change_vs_1pct"] = (
            summary.loc[mask, "n"] / baseline["n"] - 1.0
        ) * 100.0
    return summary, pd.DataFrame(prediction_rows)


def make_figure(summary: pd.DataFrame, output: Path, title: str) -> None:
    fitted = summary[summary["fit_status"] == "fitted"].copy()
    if fitted.empty:
        return
    preferred = fitted[fitted["corridor"] == "I-95 NB"]
    data = preferred if not preferred.empty else fitted
    data = data.sort_values("threshold_multiplier")
    color = "#1f77b4"
    labels = [f"{value:.2f}" for value in data["threshold_multiplier"]]
    panels = [
        ("median_duration_h", "Median P (h)"),
        ("median_d_over_c_h", "Median $X_E$ (h)"),
        ("fd", "$f_d$ (h$^{1-n}$)"),
        ("n", "$n$"),
    ]
    figure, axes = plt.subplots(2, 2, figsize=(9, 6.4), constrained_layout=True)
    for axis, (column, ylabel) in zip(axes.flat, panels):
        axis.plot(labels, data[column], color=color, marker="o", linewidth=2)
        axis.set_xlabel("Speed threshold multiplier on S3 capacity speed")
        axis.set_ylabel(ylabel)
        axis.grid(axis="y", color="#d9d9d9", linewidth=0.8)
        axis.spines[["top", "right"]].set_visible(False)
    figure.suptitle(title, fontsize=14)
    figure.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    args = parse_args()
    config = load_config(args.config)
    results_dir = ROOT / "results"
    figures_dir = ROOT / "figures"
    results_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)
    output_prefix = config.get("output_prefix", "nvta_a")

    parameters, data, coverage = prepare_inputs(config)
    episodes = detect_threshold_episodes(data, config)
    support = build_common_support(episodes, config)
    fit_summary, predictions = fit_thresholds(episodes, support, config)

    parameters.to_csv(results_dir / f"{output_prefix}_step1_fd_parameters.csv", index=False)
    coverage.to_csv(results_dir / f"{output_prefix}_step2_day_coverage.csv", index=False)
    episodes.to_csv(results_dir / f"{output_prefix}_step3_threshold_episodes.csv", index=False)
    support.to_csv(results_dir / f"{output_prefix}_step3_common_support.csv", index=False)
    fit_summary.to_csv(results_dir / f"{output_prefix}_step4_qvdf_fit_summary.csv", index=False)
    predictions.to_csv(results_dir / f"{output_prefix}_step4_qvdf_predictions.csv", index=False)
    make_figure(
        fit_summary,
        figures_dir / f"{output_prefix}_threshold_parameter_sensitivity.png",
        config.get("figure_title", "I-95 Northbound AM QVDF threshold sensitivity"),
    )

    fitted = fit_summary[fit_summary["fit_status"] == "fitted"]
    summary = {
        "scope": {
            "corridors": config["corridors"],
            "period": config["analysis_period"],
            "weekday_dates": int(data["date_local"].nunique()),
            "tmcs": int(data["tmc_code"].nunique()),
            "source_resolution_minutes": 5,
            "analysis_resolution_minutes": int(config["analysis_interval_minutes"]),
        },
        "parameter_mode": config.get("parameter_mode", "facility_priors"),
        "method": (
            "fixed S3 parameters within each run; recompute P and D/C at each threshold; "
            "fit f_d and n separately on common link-day support"
        ),
        "common_support_by_corridor": {
            corridor: int(group["common_support"].sum())
            for corridor, group in support.groupby("corridor")
        },
        "fitted_corridors": sorted(fitted["corridor"].unique().tolist()),
        "unfitted_corridors": sorted(
            set(config["corridors"]) - set(fitted["corridor"].unique())
        ),
    }
    with (results_dir / f"{output_prefix}_summary.json").open("w", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2)

    print(fit_summary.to_string(index=False))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
