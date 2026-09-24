"""E: time-space view of mean and 95th-percentile travel time on I-95 GP.

For every TMC and 5-minute time of day, the 23 weekday travel times give
TTI = mean / T0, PTI95 = P95 / T0 and gamma95 = P95 / mean, with T0 from the
TMC's off-peak free-flow speed. Distance runs in the direction of travel.
"""

from __future__ import annotations

from pathlib import Path
import sys

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import RITIS_TMC_IDENTIFICATION, experiment_dirs  # noqa: E402
from ritis_io import free_flow_speed, gp_corridor, normalize_tmc, read_ritis, ritis_length  # noqa: E402


OUTPUT, FIGURES = experiment_dirs("e-time-space")

CORRIDORS = [
    {"label": "I-95 NB AM", "corridor": "I95_NB", "start": 5 * 60, "end": 11 * 60, "northbound": True, "file": "i95_nb_am"},
    {"label": "I-95 SB PM", "corridor": "I95_SB", "start": 12 * 60, "end": 21 * 60, "northbound": False, "file": "i95_sb_pm"},
]
TTI_CAP = 5.0
GAMMA_CAP = 2.0

INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
SEQUENTIAL = LinearSegmentedColormap.from_list("blue_seq", ["#f7f9fc", "#bcd6f5", "#5b9be3", "#2a78d6", "#0b3d7a"])
SEQUENTIAL.set_over("#061f40")


def travel_order(tmcs: pd.DataFrame, northbound: bool) -> pd.DataFrame:
    """Order TMCs in the direction of travel, using start latitude."""
    ident = pd.read_csv(RITIS_TMC_IDENTIFICATION, encoding="utf-8-sig", dtype={"tmc": "string"})
    ident["tmc_code"] = normalize_tmc(ident["tmc"])
    tmcs = tmcs.merge(ident[["tmc_code", "start_latitude"]], on="tmc_code", how="left")
    return tmcs.sort_values("start_latitude", ascending=northbound).reset_index(drop=True)


def cell_table(spec: dict) -> pd.DataFrame:
    tmcs = gp_corridor(spec["corridor"])
    data = read_ritis(set(tmcs["tmc_code"]))
    data = data[(data["minute"] >= spec["start"]) & (data["minute"] < spec["end"])]
    vf = free_flow_speed(read_ritis(set(tmcs["tmc_code"])))
    length = ritis_length(data)

    ordered = travel_order(tmcs[["tmc_code"]], spec["northbound"])
    ordered["length_mi"] = ordered["tmc_code"].map(length)
    ordered["distance_end_mi"] = ordered["length_mi"].cumsum()
    ordered["distance_start_mi"] = ordered["distance_end_mi"] - ordered["length_mi"]
    ordered["t0_min"] = ordered["length_mi"] / ordered["tmc_code"].map(vf) * 60.0

    cells = data.groupby(["tmc_code", "minute"])["travel_time_minutes"].agg(
        mean_tt="mean", p95_tt=lambda s: s.quantile(0.95), days="count"
    ).reset_index()
    cells = cells.merge(ordered, on="tmc_code")
    cells["tti"] = cells["mean_tt"] / cells["t0_min"]
    cells["pti95"] = cells["p95_tt"] / cells["t0_min"]
    cells["gamma95"] = cells["p95_tt"] / cells["mean_tt"]
    cells.insert(0, "corridor_period", spec["label"])
    return cells


def plot(cells: pd.DataFrame, spec: dict, output: Path) -> None:
    plt.rcParams.update({"font.size": 9.5, "axes.edgecolor": INK_SECONDARY, "axes.labelcolor": INK,
                         "xtick.color": INK_SECONDARY, "ytick.color": INK_SECONDARY})
    segments = cells.drop_duplicates("tmc_code").sort_values("distance_start_mi")
    edges = np.r_[segments["distance_start_mi"].to_numpy(), segments["distance_end_mi"].iloc[-1]]
    minutes = np.arange(spec["start"], spec["end"] + 5, 5)

    figure, axes = plt.subplots(1, 3, figsize=(13.2, 5.0), constrained_layout=True, sharey=True)
    panels = [
        ("tti", "(a) Mean TTI", 1.0, TTI_CAP),
        ("pti95", "(b) PTI$_{95}$ (95th-percentile day)", 1.0, TTI_CAP),
        ("gamma95", r"(c) $\gamma_{95}$ = PTI$_{95}$ / TTI", 1.0, GAMMA_CAP),
    ]
    for axis, (column, title, low, high) in zip(axes, panels):
        grid = (
            cells.pivot(index="minute", columns="tmc_code", values=column)
            .reindex(index=minutes[:-1], columns=segments["tmc_code"])
            .to_numpy(float)
        )
        mesh = axis.pcolormesh(edges, minutes / 60.0, grid, cmap=SEQUENTIAL, vmin=low, vmax=high, shading="flat")
        axis.set_title(title, loc="left", fontsize=10, color=INK)
        axis.set_xlabel("Distance in direction of travel (mi)")
        axis.set_xlim(edges[0], edges[-1])
        bar = figure.colorbar(mesh, ax=axis, extend="max", fraction=0.05, pad=0.02)
        bar.outline.set_visible(False)
    axes[0].set_ylabel("Time of day (h)")
    axes[0].invert_yaxis()
    figure.suptitle(
        f"{spec['label']}, GP lanes, {len(segments)} TMCs, 23 weekdays. Each cell: one TMC × one 5-minute time of day",
        x=0.01, ha="left", fontsize=11, color=INK,
    )
    figure.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    tables = []
    for spec in CORRIDORS:
        cells = cell_table(spec)
        plot(cells, spec, FIGURES / f"nvta_e_time_space_{spec['file']}.png")
        tables.append(cells)
        segments = cells.drop_duplicates("tmc_code")
        print(spec["label"], "TMCs", len(segments), "length %.1f mi" % segments["length_mi"].sum(),
              "| max TTI %.2f, max PTI95 %.2f, max gamma %.2f" % (cells.tti.max(), cells.pti95.max(), cells.gamma95.max()))
    pd.concat(tables, ignore_index=True).to_csv(OUTPUT / "e_time_space_cells.csv", index=False)


if __name__ == "__main__":
    main()
