from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


BIN_HOURS = 5.0 / 60.0


def load_config(repo_root: Path) -> dict:
    with (repo_root / "config" / "experiment_a.json").open(encoding="utf-8") as f:
        return json.load(f)


def load_link_data(repo_root: Path, config: dict) -> pd.DataFrame:
    path = repo_root / config["input_csv"]
    df = pd.read_csv(path)
    df["timestamp_local"] = pd.to_datetime(df["timestamp_local"])
    df["date_local"] = pd.to_datetime(df["date_local"]).dt.date.astype(str)
    required = {
        "link_id", "road_order", "timestamp_local", "date_local",
        "minute_of_day", "is_am_analysis_bin", "speed_mph", "flow_vph"
    }
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    if df[list(required)].isna().any().any():
        raise ValueError("Required input columns contain missing values")
    dup = df.duplicated(["link_id", "timestamp_local"])
    if dup.any():
        raise ValueError(f"Input contains {int(dup.sum())} duplicate link/time rows")
    return df.sort_values(["road_order", "link_id", "timestamp_local"]).reset_index(drop=True)


def estimate_link_parameters(df: pd.DataFrame, config: dict) -> pd.DataFrame:
    analysis = df[
        (df["minute_of_day"] >= config["analysis_start_minute"])
        & (df["minute_of_day"] < config["analysis_end_minute"])
    ]
    rows = []
    for link_id, g in analysis.groupby("link_id", sort=False):
        vf = float(g["speed_mph"].quantile(config["free_flow_speed_quantile"]))
        capacity = float(g["flow_vph"].quantile(config["capacity_flow_quantile"]))
        vc = vf / np.sqrt(2.0)
        first = g.iloc[0]
        rows.append({
            "corridor": first.get("corridor", "I405_S"),
            "road_order": int(first["road_order"]),
            "link_id": link_id,
            "direction": first.get("direction", "S"),
            "milepost": float(first["milepost"]),
            "station_count": int(first["station_count"]),
            "observations_5min": int(len(g)),
            "days": int(g["date_local"].nunique()),
            "vf_mph": vf,
            "capacity_vph_link": capacity,
            "vc_mph": vc,
            "vf_quantile": float(config["free_flow_speed_quantile"]),
            "capacity_quantile": float(config["capacity_flow_quantile"]),
            "capacity_speed_method": config["capacity_speed_method"],
        })
    return pd.DataFrame(rows).sort_values("road_order").reset_index(drop=True)


def compute_daily_demand(
    df: pd.DataFrame, link_parameters: pd.DataFrame, config: dict
) -> pd.DataFrame:
    capacity = link_parameters.set_index("link_id")["capacity_vph_link"]
    analysis = df[
        (df["minute_of_day"] >= config["analysis_start_minute"])
        & (df["minute_of_day"] < config["analysis_end_minute"])
    ].copy()
    window = int(config["demand_window_bins"])
    rows = []
    for (link_id, date), g in analysis.groupby(["link_id", "date_local"], sort=False):
        g = g.sort_values("timestamp_local").reset_index(drop=True)
        rolling = g["flow_vph"].rolling(window=window, min_periods=window).mean()
        if rolling.notna().sum() == 0:
            raise ValueError(f"Not enough observations for {link_id} on {date}")
        end_idx = int(rolling.idxmax())
        start_idx = end_idx - window + 1
        demand = float(rolling.iloc[end_idx])
        cap = float(capacity.loc[link_id])
        rows.append({
            "link_id": link_id,
            "date_local": date,
            "demand_vph_link": demand,
            "capacity_vph_link": cap,
            "demand_capacity_ratio": demand / cap,
            "peak_hour_start_local": g.iloc[start_idx]["timestamp_local"].isoformat(),
            "peak_hour_end_local": (
                g.iloc[end_idx]["timestamp_local"] + pd.Timedelta(minutes=5)
            ).isoformat(),
            "demand_definition": "maximum_rolling_60min_mean_flow",
        })
    return pd.DataFrame(rows).sort_values(["link_id", "date_local"]).reset_index(drop=True)


def _qualifying_runs(mask: np.ndarray, minimum_bins: int) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start = None
    for i, value in enumerate(mask):
        if value and start is None:
            start = i
        if start is not None and ((not value) or i == len(mask) - 1):
            end = i if value and i == len(mask) - 1 else i - 1
            if end - start + 1 >= minimum_bins:
                runs.append((start, end))
            start = None
    return runs


def detect_threshold_episodes(
    df: pd.DataFrame, link_parameters: pd.DataFrame, daily_demand: pd.DataFrame,
    config: dict
) -> pd.DataFrame:
    params = link_parameters.set_index("link_id")
    demand = daily_demand.set_index(["link_id", "date_local"])
    multipliers = [float(v) for v in config["speed_threshold_multipliers"]]
    smooth_bins = int(config["smoothing_bins"])
    min_bins = int(config["minimum_episode_bins"])
    rows = []
    for (link_id, date), g in df.groupby(["link_id", "date_local"], sort=False):
        g = g.sort_values("timestamp_local").reset_index(drop=True).copy()
        g["smoothed_speed_mph"] = g["speed_mph"].rolling(
            window=smooth_bins, center=True, min_periods=1
        ).median()
        vc = float(params.loc[link_id, "vc_mph"])
        capacity = float(params.loc[link_id, "capacity_vph_link"])
        dc = float(demand.loc[(link_id, date), "demand_capacity_ratio"])
        for multiplier in multipliers:
            threshold = multiplier * vc
            runs = _qualifying_runs(
                (g["smoothed_speed_mph"] <= threshold).to_numpy(), min_bins
            )
            base = {
                "link_id": link_id,
                "date_local": date,
                "threshold_multiplier": multiplier,
                "vc_mph": vc,
                "threshold_speed_mph": threshold,
                "demand_capacity_ratio": dc,
                "capacity_vph_link": capacity,
                "episode_identified": bool(runs),
            }
            if not runs:
                rows.append({
                    **base, "duration_bins": 0, "duration_h": 0.0,
                    "congested_passed_volume_veh": 0.0,
                    "capacity_equivalent_hours": 0.0,
                    "episode_start_local": "", "episode_end_local": "",
                    "minimum_speed_mph": np.nan, "minimum_speed_time_local": "",
                    "touches_data_start": False, "touches_data_end": False,
                })
                continue
            # Longest episode; ties use the lower minimum speed, then earlier start.
            start, end = max(
                runs,
                key=lambda run: (
                    run[1] - run[0] + 1,
                    -float(g.iloc[run[0]:run[1] + 1]["smoothed_speed_mph"].min()),
                    -run[0],
                ),
            )
            episode = g.iloc[start:end + 1]
            min_idx = int(episode["smoothed_speed_mph"].idxmin())
            passed_volume = float(episode["flow_vph"].sum() * BIN_HOURS)
            rows.append({
                **base,
                "duration_bins": int(end - start + 1),
                "duration_h": float((end - start + 1) * BIN_HOURS),
                "congested_passed_volume_veh": passed_volume,
                # Congested passing volume divided by hourly link capacity.
                # The resulting capacity-equivalent duration has units of hours.
                "capacity_equivalent_hours": passed_volume / capacity,
                "episode_start_local": g.iloc[start]["timestamp_local"].isoformat(),
                "episode_end_local": (
                    g.iloc[end]["timestamp_local"] + pd.Timedelta(minutes=5)
                ).isoformat(),
                "minimum_speed_mph": float(g.loc[min_idx, "smoothed_speed_mph"]),
                "minimum_speed_time_local": g.loc[min_idx, "timestamp_local"].isoformat(),
                "touches_data_start": bool(start == 0),
                "touches_data_end": bool(end == len(g) - 1),
            })
    return pd.DataFrame(rows).sort_values(
        ["threshold_multiplier", "link_id", "date_local"]
    ).reset_index(drop=True)


def common_support(episodes: pd.DataFrame, multipliers: list[float]) -> pd.DataFrame:
    availability = episodes.pivot_table(
        index=["link_id", "date_local"], columns="threshold_multiplier",
        values="episode_identified", aggfunc="first"
    ).fillna(False)
    expected = [float(v) for v in multipliers]
    for multiplier in expected:
        if multiplier not in availability.columns:
            availability[multiplier] = False
    availability = availability[expected]
    availability["common_support"] = availability.all(axis=1)
    result = availability.reset_index()
    result.columns = [
        "link_id", "date_local",
        *[f"episode_at_{v:.2f}" for v in expected], "common_support"
    ]
    return result


def fit_power_curve(x: np.ndarray, y: np.ndarray, config: dict) -> dict:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    grid = np.arange(
        config["fit_n_min"],
        config["fit_n_max"] + config["fit_n_step"] / 2.0,
        config["fit_n_step"],
    )
    z = x[:, None] ** grid[None, :]
    fd = np.sum(z * y[:, None], axis=0) / np.sum(z * z, axis=0)
    pred = z * fd[None, :]
    sse = np.sum((y[:, None] - pred) ** 2, axis=0)
    best = int(np.argmin(sse))
    yhat = pred[:, best]
    sst = float(np.sum((y - y.mean()) ** 2))
    return {
        "fd_h": float(fd[best]),
        "n": float(grid[best]),
        "rmse_h": float(np.sqrt(np.mean((y - yhat) ** 2))),
        "r_squared": float(1.0 - sse[best] / sst) if sst > 0 else np.nan,
        "n_at_boundary": bool(best == 0 or best == len(grid) - 1),
        "predicted": yhat,
    }


def bootstrap_fit(x: np.ndarray, y: np.ndarray, config: dict) -> dict:
    rng = np.random.default_rng(int(config["random_seed"]))
    reps = int(config["bootstrap_replicates"])
    estimates = []
    for _ in range(reps):
        sample = rng.integers(0, len(x), len(x))
        fit = fit_power_curve(x[sample], y[sample], config)
        estimates.append((fit["fd_h"], fit["n"]))
    arr = np.asarray(estimates)
    return {
        "fd_ci_low_h": float(np.quantile(arr[:, 0], 0.025)),
        "fd_ci_high_h": float(np.quantile(arr[:, 0], 0.975)),
        "n_ci_low": float(np.quantile(arr[:, 1], 0.025)),
        "n_ci_high": float(np.quantile(arr[:, 1], 0.975)),
    }
