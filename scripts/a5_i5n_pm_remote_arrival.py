#!/usr/bin/env python3
"""Test remote free-flow upstream arrivals plus all intervening ramps."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from experiment_a.core import _qualifying_runs, fit_power_curve
from experiment_a.i5n_conservation import maximum_rolling_mean, split_link_ids


DEFAULT_SOURCE = Path(
    "/Users/jinxiwu/Library/CloudStorage/Dropbox-ASU/Jinxi Wu/IEEE Big Data/"
    "I210E_corridor_data_package/multicorridor_2026_pilot/"
    "trafficflowbench_five_corridors/data_public/kaggle_release/"
    "corridors/D12_I5_N"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE)
    return parser.parse_args()


def daily_path(source: Path, kind: str, date: str) -> Path:
    token = date.replace("-", "_")
    return (
        source / "train" / kind / f"year_month={date[:7]}"
        / f"d12_text_station_5min_{token}.parquet"
    )


def control_volumes(source: Path, config: dict) -> list[dict]:
    topology = pd.read_csv(
        source / "network" / "lwr_sensor_topology.csv"
    ).sort_values("segment_index")
    ramps = pd.read_csv(
        source / "network" / "ramp_control_map.csv", dtype={"station_id": str}
    )
    fd = pd.read_csv(
        source / "network" / "fd_parameters.csv", dtype={"station_id": str}
    ).set_index("station_id")
    start = int(config["upstream_segment_index"])
    definitions = []
    for end in config["bottleneck_segment_indices"]:
        path = topology[topology["segment_index"].between(start, int(end))]
        links = {
            link for value in path["mainline_path_links"]
            for link in split_link_ids(value)
        }
        attached = ramps[ramps["nearest_mainline_link_id"].isin(links)]
        upstream = str(int(path.iloc[0]["upstream_detector"]))
        downstream = str(int(path.iloc[-1]["downstream_detector"]))
        definitions.append({
            "control_volume_id": f"I5N-CV{start:02d}-{int(end):02d}",
            "upstream_segment_index": start,
            "bottleneck_segment_index": int(end),
            "upstream_station_id": upstream,
            "downstream_station_id": downstream,
            "on_ramp_station_ids": attached.loc[
                attached["ramp_type"].eq("OR"), "station_id"
            ].tolist(),
            "off_ramp_station_ids": attached.loc[
                attached["ramp_type"].eq("FR"), "station_id"
            ].tolist(),
            "segment_count": int(len(path)),
            "length_km": float(path["length_km"].sum()),
            "capacity_vph_link": float(fd.loc[downstream, "capacity_vph"]),
            "capacity_speed_kmh": float(fd.loc[downstream, "v_cut"]),
            "upstream_capacity_speed_kmh": float(fd.loc[upstream, "v_cut"]),
        })
    return definitions


def has_episode(speed: pd.Series, threshold: float, minimum_bins: int) -> bool:
    return bool(_qualifying_runs(speed.le(threshold).to_numpy(), minimum_bins))


def run(source: Path, config: dict, volumes: list[dict]):
    dates = pd.date_range(
        config["sample_start_date"], config["sample_end_date"], freq="B"
    ).strftime("%Y-%m-%d")
    threshold = float(config["minimum_pct_observed"])
    window = int(config["demand_window_bins"])
    smooth = int(config["smoothing_bins"])
    minimum_bins = int(config["minimum_episode_bins"])
    link_days, durations = [], []
    cell_data: dict[str, list[pd.DataFrame]] = {
        item["control_volume_id"]: [] for item in volumes
    }

    for date in dates:
        mainline = pd.read_parquet(
            daily_path(source, "mainline_states", date),
            columns=["timestamp", "station_id", "speed_kmh", "flow_vph", "pct_observed"],
        )
        ramps = pd.read_parquet(
            daily_path(source, "ramp_states", date),
            columns=["timestamp", "station_id", "flow_vph", "pct_observed"],
        )
        for frame in (mainline, ramps):
            frame["station_id"] = frame["station_id"].astype(str)
            frame["time_local"] = frame["timestamp"].str.slice(11, 16)
            frame.drop(
                frame.index[
                    ~frame["time_local"].ge(config["period_start"])
                    | ~frame["time_local"].lt(config["period_end"])
                ], inplace=True,
            )
        mf = mainline.pivot(index="time_local", columns="station_id", values="flow_vph")
        ms = mainline.pivot(index="time_local", columns="station_id", values="speed_kmh")
        mp = mainline.pivot(index="time_local", columns="station_id", values="pct_observed")
        rf = ramps.pivot(index="time_local", columns="station_id", values="flow_vph")
        rp = ramps.pivot(index="time_local", columns="station_id", values="pct_observed")

        for volume in volumes:
            up, down = volume["upstream_station_id"], volume["downstream_station_id"]
            valid = mp[up].ge(threshold) & mp[down].ge(threshold)
            valid &= mf[[up, down]].notna().all(axis=1) & ms[[up, down]].notna().all(axis=1)
            arrivals = mf[up].copy()
            for station in volume["on_ramp_station_ids"]:
                valid &= rp[station].ge(threshold) & rf[station].notna()
                arrivals += rf[station]
            for station in volume["off_ramp_station_ids"]:
                valid &= rp[station].ge(threshold) & rf[station].notna()
                arrivals -= rf[station]
            arrivals = arrivals.where(valid)
            downstream = mf[down].where(valid)
            speed = ms[down].where(valid).rolling(
                smooth, center=True, min_periods=1
            ).median()
            upstream_speed = ms[up].where(valid).rolling(
                smooth, center=True, min_periods=1
            ).median()
            capacity = volume["capacity_vph_link"]
            link_days.append({
                "control_volume_id": volume["control_volume_id"],
                "date_local": date,
                "valid_cells": int(valid.sum()),
                "coverage": float(valid.mean()),
                "upstream_episode": has_episode(
                    upstream_speed, volume["upstream_capacity_speed_kmh"], minimum_bins
                ),
                "downstream_D60_vph": maximum_rolling_mean(downstream, window),
                "downstream_dc": maximum_rolling_mean(downstream, window) / capacity,
                "remote_arrival_D60_vph": maximum_rolling_mean(arrivals, window),
                "remote_arrival_dc": maximum_rolling_mean(arrivals, window) / capacity,
            })
            cell_data[volume["control_volume_id"]].append(pd.DataFrame({
                "remote_arrival_vph": arrivals,
                "downstream_flow_vph": downstream,
            }))
            for multiplier in config["speed_threshold_multipliers"]:
                runs = _qualifying_runs(
                    speed.le(float(multiplier) * volume["capacity_speed_kmh"]).to_numpy(),
                    minimum_bins,
                )
                bins = max((end - start + 1 for start, end in runs), default=0)
                durations.append({
                    "control_volume_id": volume["control_volume_id"],
                    "date_local": date,
                    "threshold_multiplier": float(multiplier),
                    "episode_identified": bool(runs),
                    "duration_bins": int(bins),
                    "duration_h": bins / 12.0,
                })

    link_days = pd.DataFrame(link_days)
    durations = pd.DataFrame(durations)
    merged = durations.merge(link_days, on=["control_volume_id", "date_local"])
    common = merged.groupby(["control_volume_id", "date_local"])[
        "episode_identified"
    ].all()
    keys = common[common].reset_index()[["control_volume_id", "date_local"]]
    fit_data = merged.merge(keys, on=["control_volume_id", "date_local"])
    summaries, predictions = [], []
    for multiplier, group in fit_data.groupby("threshold_multiplier"):
        for label, column in {
            "downstream_throughput": "downstream_dc",
            "remote_upstream_plus_on_minus_off": "remote_arrival_dc",
        }.items():
            fit = fit_power_curve(
                group[column].to_numpy(float), group["duration_h"].to_numpy(float), config
            )
            summaries.append({
                "demand_basis": label,
                "threshold_multiplier": multiplier,
                "observations": len(group),
                "fd_h": fit["fd_h"], "n": fit["n"],
                "r_squared": fit["r_squared"], "rmse_h": fit["rmse_h"],
                "spearman_rho": group[column].corr(group["duration_h"], method="spearman"),
                "n_at_boundary": fit["n_at_boundary"],
            })
            for (_, row), prediction in zip(group.iterrows(), fit["predicted"]):
                predictions.append({
                    "demand_basis": label,
                    "threshold_multiplier": multiplier,
                    "control_volume_id": row["control_volume_id"],
                    "date_local": row["date_local"],
                    "dc_ratio": row[column], "duration_h": row["duration_h"],
                    "predicted_duration_h": prediction,
                })
    closure = []
    for volume_id, pieces in cell_data.items():
        cells = pd.concat(pieces).dropna()
        residual = cells["remote_arrival_vph"] - cells["downstream_flow_vph"]
        closure.append({
            "control_volume_id": volume_id, "valid_cells": len(cells),
            "correlation": cells.corr().iloc[0, 1], "bias_vph": residual.mean(),
            "mae_vph": residual.abs().mean(),
            "rmse_vph": np.sqrt(np.mean(residual**2)),
            "note": "raw balance before storage term; not expected to equal zero",
        })
    return link_days, durations, pd.DataFrame(summaries), pd.DataFrame(predictions), pd.DataFrame(closure)


def make_figure(summary, predictions, output):
    chosen = predictions[np.isclose(predictions["threshold_multiplier"], 1.0)]
    metrics = summary[np.isclose(summary["threshold_multiplier"], 1.0)].set_index("demand_basis")
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
    for ax, (basis, title) in zip(axes, [
        ("downstream_throughput", "Downstream throughput"),
        ("remote_upstream_plus_on_minus_off", "Remote upstream + on - off"),
    ]):
        group = chosen[chosen["demand_basis"].eq(basis)]
        ax.scatter(group["dc_ratio"], group["duration_h"], alpha=.75)
        order = np.argsort(group["dc_ratio"])
        ax.plot(group["dc_ratio"].to_numpy()[order], group["predicted_duration_h"].to_numpy()[order], color="#c62828")
        row = metrics.loc[basis]
        ax.set_title(f"{title}\n$R^2$={row.r_squared:.3f}, Spearman={row.spearman_rho:.3f}")
        ax.set_xlabel("Dimensionless peak-hour D/C")
        ax.grid(alpha=.2)
    axes[0].set_ylabel("Congestion duration P (hours)")
    fig.suptitle("I-5 North PM remote-arrival conservation diagnostic")
    fig.tight_layout()
    fig.savefig(output, dpi=220, bbox_inches="tight")
    plt.close(fig)


def main():
    args = parse_args()
    with (ROOT / "config" / "experiment_a_i5n_pm_remote.json").open() as source:
        config = json.load(source)
    volumes = control_volumes(args.source_root, config)
    link_days, durations, fits, predictions, closure = run(args.source_root, config, volumes)
    results, figures = ROOT / "results", ROOT / "figures"
    map_rows = [{
        **{key: value for key, value in volume.items() if not key.endswith("_station_ids")},
        "on_ramp_station_ids": ";".join(volume["on_ramp_station_ids"]),
        "off_ramp_station_ids": ";".join(volume["off_ramp_station_ids"]),
    } for volume in volumes]
    for name, frame in {
        "control_volume_map": pd.DataFrame(map_rows), "link_day": link_days,
        "durations": durations, "fit_summary": fits,
        "fit_predictions": predictions, "closure_summary": closure,
    }.items():
        frame.to_csv(results / f"a5_i5n_pm_remote_{name}.csv", index=False)
    make_figure(fits, predictions, figures / "a5_i5n_pm_remote_arrival.png")
    one = fits[np.isclose(fits["threshold_multiplier"], 1.0)]
    summary = {
        "sample": "I-5 North, PM, 2025-07-07 through 2025-07-25",
        "control_volumes": [volume["control_volume_id"] for volume in volumes],
        "minimum_daily_coverage": float(link_days["coverage"].min()),
        "overall_coverage": float(link_days["valid_cells"].sum() / (len(link_days) * 48)),
        "upstream_congested_days": int(link_days.groupby("date_local")["upstream_episode"].max().sum()),
        "common_support_observations": int(one["observations"].iloc[0]),
        "threshold_1_fit": one.set_index("demand_basis")[["fd_h", "n", "r_squared", "rmse_h", "spearman_rho", "n_at_boundary"]].to_dict(orient="index"),
        "interpretation": "Remote ramp-adjusted arrivals reduce the inverse association but do not establish a positive duration-QVDF relationship.",
    }
    with (results / "a5_i5n_pm_remote_summary.json").open("w") as output:
        json.dump(summary, output, indent=2)
    print(pd.DataFrame(map_rows).to_string(index=False))
    print("\nThreshold 1.00 results:")
    print(one.to_string(index=False))
    print("\nSummary:")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
