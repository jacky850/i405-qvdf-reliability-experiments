"""C6: minimal GP-versus-managed-lane reliability comparison.

The I-95 and I-395 express lanes in Northern Virginia are reversible. A
managed-lane TMC keeps reporting a RITIS speed while its direction is closed,
so a comparison is valid only for the direction that is open in the period:

* northbound managed lanes are open in AM and closed in PM;
* southbound managed lanes are open in PM and closed in AM.

Open status comes from the Cube network period-restriction codes
(``AMLIMIT``/``PMLIMIT`` = 9 means closed). For each open corridor-period
pair, the script compares observed travel-time reliability on the managed lane
and on the GP TMCs covering the same section. No QVDF parameters are used for
the managed lane: the CBI package has almost no link-specific fits for an open
managed lane (see ``c6_managed_lane_parameter_audit.csv``).

Definitions follow the memo. For facility f, day d, and peak window W,
T_{f,d} is the mean over W of the summed 5-minute TMC travel times on the
matched section, T0 is the section free-flow time from the RITIS reference
speed and the RITIS-implied TMC length, TTI = E_d[T]/T0, PTI95 = Q95_d[T]/T0, and gamma95 = PTI95/TTI.
"""

from __future__ import annotations

from pathlib import Path
import sys
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import ConstantInputWarning, pearsonr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from paths import (  # noqa: E402
    CBI,
    CUBE_AM_NETWORK,
    RITIS_RAW,
    RITIS_TMC_IDENTIFICATION,
    experiment_dirs,
)


OUTPUT, FIGURES = experiment_dirs("c6-managed-lane-comparison")

# Peak windows follow the CBI/NVTA model periods (AM 06-09, PM 15-19).
PERIOD_WINDOWS = {"AM": (6 * 60, 9 * 60), "MD": (9 * 60, 15 * 60), "PM": (15 * 60, 19 * 60)}
LIMIT_COLUMN = {"AM": "AMLIMIT", "PM": "PMLIMIT", "MD": "MDLIMIT"}
CLOSED_CODE = 9

PAIRS = [
    {"pair": "I-95 SB PM", "gp": "I95_SB", "ml": "I95HOV_SB", "period": "PM", "primary": True},
    {"pair": "I-95 NB AM", "gp": "I95_NB", "ml": "I95HOV_NB", "period": "AM", "primary": False},
    {"pair": "I-395 SB PM", "gp": "I395_SB", "ml": "I395HOV_SB", "period": "PM", "primary": False},
    {"pair": "I-395 NB AM", "gp": "I395_NB", "ml": "I395HOV_NB", "period": "AM", "primary": False},
]
MANAGED_CORRIDORS = ["I95HOV_NB", "I95HOV_SB", "I395HOV_NB", "I395HOV_SB"]

SHRP2_K = 3.67
MIN_TTI_FOR_K = 1.05
BOOTSTRAP_REPLICATES = 2000
RANDOM_SEED = 606

# Validated categorical slots 1-2 (dataviz reference palette) plus ink.
GP_COLOR = "#2a78d6"
ML_COLOR = "#eb6834"
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
GRID = "#e4e3df"


def normalize_tmc(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.upper()


def load_network() -> pd.DataFrame:
    return pd.read_csv(
        CUBE_AM_NETWORK,
        usecols=["link_id", "AMLIMIT", "PMLIMIT", "MDLIMIT", "STREETNAME"],
        low_memory=False,
    )


def load_reference(corridor: str, network: pd.DataFrame) -> pd.DataFrame:
    reference = pd.read_csv(
        CBI / corridor / "01-input-and-qc/link_reference.csv", dtype={"tmc_code": "string"}
    )
    reference["tmc_code"] = normalize_tmc(reference["tmc_code"])
    reference = reference[["tmc_code", "network_link_id"]].merge(
        network, left_on="network_link_id", right_on="link_id", how="left", validate="many_to_one"
    )
    reference["corridor"] = corridor
    return reference


def load_identification() -> pd.DataFrame:
    ident = pd.read_csv(RITIS_TMC_IDENTIFICATION, encoding="utf-8-sig", dtype={"tmc": "string"})
    ident["tmc_code"] = normalize_tmc(ident["tmc"])
    return ident[
        ["tmc_code", "miles", "start_latitude", "start_longitude", "end_latitude", "end_longitude"]
    ]


def read_ritis(tmcs: set[str]) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for chunk in pd.read_csv(
        RITIS_RAW,
        usecols=["tmc_code", "measurement_tstamp", "speed", "reference_speed", "travel_time_minutes"],
        dtype={"tmc_code": "string"},
        chunksize=1_000_000,
    ):
        chunk["tmc_code"] = normalize_tmc(chunk["tmc_code"])
        chunk = chunk[chunk["tmc_code"].isin(tmcs)]
        if not chunk.empty:
            frames.append(chunk)
    data = pd.concat(frames, ignore_index=True)
    data["timestamp"] = pd.to_datetime(data.pop("measurement_tstamp"))
    data = data[data["timestamp"].dt.weekday < 5].copy()
    data["date_local"] = data["timestamp"].dt.date.astype(str)
    data["minute"] = data["timestamp"].dt.hour * 60 + data["timestamp"].dt.minute
    return data


def attach_ritis_length(section: pd.DataFrame, data: pd.DataFrame) -> pd.DataFrame:
    """Use the length RITIS used for travel time, so T and T0 share one length.

    A few short TMCs have identification-file lengths up to 2.7 times the
    length implied by RITIS travel time and speed, which would push TTI below 1.
    """
    implied = (data["travel_time_minutes"] * data["speed"] / 60.0).groupby(data["tmc_code"]).median()
    section = section.rename(columns={"miles": "identification_miles"})
    section["miles"] = section["tmc_code"].map(implied).fillna(section["identification_miles"])
    return section


def in_window(data: pd.DataFrame, period: str) -> pd.DataFrame:
    start, end = PERIOD_WINDOWS[period]
    return data[(data["minute"] >= start) & (data["minute"] < end)]


def axis_positions(frame: pd.DataFrame) -> pd.DataFrame:
    """Project TMC endpoints onto the section's principal axis, in miles."""
    scale = np.array([69.0, 69.0 * np.cos(np.radians(38.8))])
    start = frame[["start_latitude", "start_longitude"]].to_numpy(float) * scale
    end = frame[["end_latitude", "end_longitude"]].to_numpy(float) * scale
    points = np.vstack([start, end])
    center = points.mean(axis=0)
    direction = np.linalg.svd(points - center)[2][0]
    frame = frame.copy()
    frame["s_start"] = (start - center) @ direction
    frame["s_end"] = (end - center) @ direction
    frame["s_mid"] = 0.5 * (frame["s_start"] + frame["s_end"])
    return frame


def select_section(pair: dict, network: pd.DataFrame, ident: pd.DataFrame) -> pd.DataFrame:
    """Open managed-lane TMCs plus the GP TMCs whose midpoints lie on that section."""
    limit = LIMIT_COLUMN[pair["period"]]
    gp = load_reference(pair["gp"], network).assign(facility="GP")
    ml = load_reference(pair["ml"], network).assign(facility="ML")
    both = axis_positions(pd.concat([gp, ml]).merge(ident, on="tmc_code", how="inner"))

    ml_open = both[both["facility"].eq("ML") & both[limit].ne(CLOSED_CODE)]
    low = float(np.minimum(ml_open["s_start"], ml_open["s_end"]).min())
    high = float(np.maximum(ml_open["s_start"], ml_open["s_end"]).max())
    # GP rows must be unrestricted GP links; a reversible code would mean the
    # TMC is really on the managed facility.
    gp_rows = both[
        both["facility"].eq("GP")
        & both["AMLIMIT"].eq(0)
        & both["PMLIMIT"].eq(0)
        & both["s_mid"].between(low, high)
    ]
    section = pd.concat([ml_open, gp_rows], ignore_index=True)
    section["pair"] = pair["pair"]
    section["period"] = pair["period"]
    return section


def route_daily(section: pd.DataFrame, data: pd.DataFrame, period: str) -> pd.DataFrame:
    """Daily peak-window mean section travel time for each facility."""
    rows: list[pd.DataFrame] = []
    window = in_window(data, period)
    for facility, group in section.groupby("facility"):
        tmcs = set(group["tmc_code"])
        sub = window[window["tmc_code"].isin(tmcs)]
        per_bin = sub.groupby(["date_local", "minute"]).agg(
            travel_time_min=("travel_time_minutes", "sum"), tmcs=("tmc_code", "nunique")
        )
        # Only bins where every TMC on the section reports a travel time.
        per_bin = per_bin[per_bin["tmcs"].eq(len(tmcs))]
        daily = per_bin.groupby("date_local")["travel_time_min"].mean().rename("T_min").reset_index()
        daily["facility"] = facility
        rows.append(daily)
    return pd.concat(rows, ignore_index=True)


def free_flow_minutes(group: pd.DataFrame, data: pd.DataFrame) -> float:
    reference = data[data["tmc_code"].isin(group["tmc_code"])].groupby("tmc_code")["reference_speed"].median()
    miles = group.set_index("tmc_code")["miles"]
    return float((miles / reference.reindex(miles.index) * 60.0).sum())


def reliability(values: np.ndarray, t0: float) -> dict[str, float]:
    mean = float(np.mean(values))
    t95 = float(np.quantile(values, 0.95))
    return {
        "mean_T_min": mean,
        "T95_min": t95,
        "TTI": mean / t0,
        "PTI95": t95 / t0,
        "gamma95": t95 / mean,
        "buffer_index": t95 / mean - 1.0,
    }


def summarize_pair(pair: dict, section: pd.DataFrame, daily: pd.DataFrame, data: pd.DataFrame) -> tuple[list[dict], dict]:
    wide = daily.pivot(index="date_local", columns="facility", values="T_min").dropna()
    facility_rows: list[dict] = []
    stats: dict[str, dict] = {}
    for facility in ["GP", "ML"]:
        group = section[section["facility"].eq(facility)]
        t0 = free_flow_minutes(group, data)
        length = float(group["miles"].sum())
        metrics = reliability(wide[facility].to_numpy(float), t0)
        stats[facility] = {"t0": t0, "length": length, **metrics}
        facility_rows.append(
            {
                "pair": pair["pair"],
                "facility": facility,
                "window": f"{pair['period']} {PERIOD_WINDOWS[pair['period']][0] // 60:02d}:00-{PERIOD_WINDOWS[pair['period']][1] // 60:02d}:00",
                "tmcs": int(len(group)),
                "length_mi": length,
                "weekdays": int(len(wide)),
                "T0_min": t0,
                **metrics,
            }
        )

    # Compare per-mile rates, scaled to the managed-lane section length, so a
    # small difference in covered GP length does not show up as time savings.
    length_ml = stats["ML"]["length"]
    gp_rate = wide["GP"] / stats["GP"]["length"]
    ml_rate = wide["ML"] / length_ml

    def savings(gp_values: pd.Series, ml_values: pd.Series) -> tuple[float, float]:
        mean_saving = (gp_values.mean() - ml_values.mean()) * length_ml
        t95_saving = (gp_values.quantile(0.95) - ml_values.quantile(0.95)) * length_ml
        return float(mean_saving), float(t95_saving)

    mean_saving, t95_saving = savings(gp_rate, ml_rate)
    rng = np.random.default_rng(RANDOM_SEED)
    boot = []
    for _ in range(BOOTSTRAP_REPLICATES):
        index = rng.integers(0, len(wide), size=len(wide))
        boot.append(savings(gp_rate.iloc[index], ml_rate.iloc[index]))
    boot = np.array(boot)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConstantInputWarning)
        day_corr = float(pearsonr(wide["GP"], wide["ML"]).statistic)

    comparison = {
        "pair": pair["pair"],
        "primary": pair["primary"],
        "weekdays": int(len(wide)),
        "ml_length_mi": length_ml,
        "gp_length_mi": stats["GP"]["length"],
        "gp_TTI": stats["GP"]["TTI"],
        "ml_TTI": stats["ML"]["TTI"],
        "gp_PTI95": stats["GP"]["PTI95"],
        "ml_PTI95": stats["ML"]["PTI95"],
        "gp_gamma95": stats["GP"]["gamma95"],
        "ml_gamma95": stats["ML"]["gamma95"],
        "mean_time_saving_min": mean_saving,
        "mean_time_saving_95_low": float(np.quantile(boot[:, 0], 0.025)),
        "mean_time_saving_95_high": float(np.quantile(boot[:, 0], 0.975)),
        "planning_time_saving_min": t95_saving,
        "planning_time_saving_95_low": float(np.quantile(boot[:, 1], 0.025)),
        "planning_time_saving_95_high": float(np.quantile(boot[:, 1], 0.975)),
        "gp_ml_daily_T_pearson_r": day_corr,
        "saving_basis": "GP minus ML per-mile time, scaled to the managed-lane section length; min per trip",
    }
    return facility_rows, comparison


def tmc_reliability(section: pd.DataFrame, data: pd.DataFrame, period: str) -> pd.DataFrame:
    window = in_window(data, period)
    window = window[window["tmc_code"].isin(set(section["tmc_code"]))]
    daily = window.groupby(["tmc_code", "date_local"]).agg(
        T_min=("travel_time_minutes", "mean"), reference_speed=("reference_speed", "median")
    ).reset_index()
    rows: list[dict] = []
    lookup = section.set_index("tmc_code")
    for tmc, group in daily.groupby("tmc_code"):
        info = lookup.loc[tmc]
        t0 = float(info["miles"]) / float(group["reference_speed"].median()) * 60.0
        rows.append(
            {
                "pair": info["pair"],
                "facility": info["facility"],
                "tmc_code": tmc,
                "length_mi": float(info["miles"]),
                "weekdays": int(len(group)),
                **reliability(group["T_min"].to_numpy(float), t0),
            }
        )
    return pd.DataFrame(rows)


def fit_k(tmc: pd.DataFrame) -> float:
    x = np.log(tmc["TTI"].to_numpy(float))
    y = tmc["PTI95"].to_numpy(float) - 1.0
    return float(np.dot(x, y) / np.dot(x, x))


def facility_relationship(tmc: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    rng = np.random.default_rng(RANDOM_SEED + 1)
    for facility, group in tmc.groupby("facility"):
        congested = group[group["TTI"].ge(MIN_TTI_FOR_K)]
        k = fit_k(congested) if len(congested) >= 3 else np.nan
        low = high = np.nan
        if len(congested) >= 3:
            draws = [
                fit_k(congested.iloc[rng.integers(0, len(congested), size=len(congested))])
                for _ in range(BOOTSTRAP_REPLICATES)
            ]
            low, high = np.quantile(draws, [0.025, 0.975])
        rows.append(
            {
                "facility": facility,
                "tmcs": int(len(group)),
                "median_TTI": float(group["TTI"].median()),
                "median_PTI95": float(group["PTI95"].median()),
                "median_gamma95": float(group["gamma95"].median()),
                "share_tmcs_TTI_ge_1p05": float(group["TTI"].ge(MIN_TTI_FOR_K).mean()),
                "k_fit_tmcs": int(len(congested)),
                "local_k": k,
                "local_k_95_low": float(low),
                "local_k_95_high": float(high),
                "shrp2_k": SHRP2_K,
                "k_basis": f"PTI95 = 1 + k ln(TTI), fitted on TMCs with TTI >= {MIN_TTI_FOR_K}",
            }
        )
    return pd.DataFrame(rows)


def parameter_audit(network: pd.DataFrame, data: pd.DataFrame) -> pd.DataFrame:
    """Where do the CBI managed-lane QVDF parameters come from: open or closed lanes?"""
    rows: list[dict] = []
    for corridor in MANAGED_CORRIDORS:
        params = pd.read_csv(
            CBI / corridor / "06-qvdf-calibration/qvdf_selected_parameters.csv",
            dtype={"tmc_code": "string"},
        )
        params["tmc_code"] = normalize_tmc(params["tmc_code"])
        params = params.merge(network, left_on="network_link_id", right_on="link_id", how="left")
        reference = load_reference(corridor, network)
        for period in ["AM", "MD", "PM"]:
            group = params[params["period"].eq(period)]
            tmcs = set(reference["tmc_code"])
            speed = in_window(data[data["tmc_code"].isin(tmcs)], period)
            ratio = float((speed["speed"] / speed["reference_speed"]).median()) if len(speed) else np.nan
            linked = group[group["calibration_scope"].eq("sensor_period")]
            high_medium = linked[linked["reliability"].isin(["high", "medium"])]
            open_mask = high_medium[LIMIT_COLUMN[period]].ne(CLOSED_CODE)
            rows.append(
                {
                    "corridor": corridor,
                    "period": period,
                    "network_open_tmcs": int(reference[LIMIT_COLUMN[period]].ne(CLOSED_CODE).sum()),
                    "network_closed_tmcs": int(reference[LIMIT_COLUMN[period]].eq(CLOSED_CODE).sum()),
                    "median_speed_over_reference": ratio,
                    "parameter_rows": int(len(group)),
                    "link_specific_high_medium": int(len(high_medium)),
                    "link_specific_high_medium_on_open_links": int(open_mask.sum()),
                }
            )
    audit = pd.DataFrame(rows)
    # MD straddles the late-morning reversal; the network codes MD as open in
    # both directions, so the observed speed ratio is the better guide there.
    audit["usable_for_open_lane_reliability"] = (
        audit["link_specific_high_medium_on_open_links"].ge(3)
        & audit["median_speed_over_reference"].ge(0.95)
    )
    return audit


def plot(daily: pd.DataFrame, comparisons: pd.DataFrame, tmc: pd.DataFrame, relationship: pd.DataFrame, output: Path) -> None:
    plt.rcParams.update({"font.size": 9.5, "axes.edgecolor": INK_SECONDARY, "axes.labelcolor": INK, "xtick.color": INK_SECONDARY, "ytick.color": INK_SECONDARY})
    figure, (left, right) = plt.subplots(1, 2, figsize=(11.2, 4.7), constrained_layout=True, gridspec_kw={"width_ratios": [1.0, 1.25]})

    # (a) Primary pair: daily section travel time, GP versus ML.
    primary = comparisons[comparisons["primary"]].iloc[0]
    pair_daily = daily[daily["pair"].eq(primary["pair"])]
    rng = np.random.default_rng(1)
    for position, (facility, color) in enumerate([("GP", GP_COLOR), ("ML", ML_COLOR)]):
        values = pair_daily.loc[pair_daily["facility"].eq(facility), "T_per_ml_section_min"].to_numpy(float)
        jitter = rng.uniform(-0.12, 0.12, size=len(values))
        left.scatter(position + jitter, values, s=34, color=color, edgecolors="white", linewidths=1.0, zorder=3)
        mean, t95 = values.mean(), np.quantile(values, 0.95)
        left.hlines(mean, position - 0.28, position + 0.28, color=INK, lw=2.0, zorder=4)
        left.hlines(t95, position - 0.28, position + 0.28, color=INK, lw=1.2, ls=(0, (3, 2)), zorder=4)
        if t95 - mean > 2.0:
            left.text(position + 0.32, mean, f"mean {mean:.1f}", va="center", fontsize=8.5, color=INK)
            left.text(position + 0.32, t95, f"95th pct {t95:.1f}", va="center", fontsize=8.5, color=INK)
        else:
            left.text(position + 0.32, t95 + 1.2, f"mean {mean:.1f}\n95th pct {t95:.1f}", va="bottom", fontsize=8.5, color=INK)
    left.set_xticks([0, 1], ["General purpose", "Express lanes"])
    left.plot([], [], color=INK, lw=2.0, label="mean")
    left.plot([], [], color=INK, lw=1.2, ls=(0, (3, 2)), label="95th percentile")
    left.legend(frameon=False, fontsize=8.3, loc="lower left")
    left.set_xlim(-0.5, 1.9)
    left.set_ylim(bottom=0)
    left.set_ylabel(f"Daily PM mean travel time (min)\n{primary['ml_length_mi']:.1f}-mile matched section")
    left.set_title(
        f"(a) {primary['pair']}: {int(primary['weekdays'])} weekdays\n"
        f"planning-time saving {primary['planning_time_saving_min']:.1f} min/trip "
        f"(95% CI {primary['planning_time_saving_95_low']:.1f}–{primary['planning_time_saving_95_high']:.1f})",
        loc="left", fontsize=10, color=INK,
    )

    # (b) TMC-level PTI95 versus TTI for GP and ML across all open pairs.
    for facility, color, label in [("GP", GP_COLOR, "General purpose"), ("ML", ML_COLOR, "Express lanes (open direction)")]:
        group = tmc[tmc["facility"].eq(facility)]
        right.scatter(group["TTI"], group["PTI95"], s=30, color=color, edgecolors="white", linewidths=0.8, alpha=0.9, zorder=3, label=f"{label} (n={len(group)} TMCs)")
    grid = np.linspace(1.0, max(2.6, float(tmc["TTI"].max()) + 0.05), 200)
    right.plot(grid, 1 + SHRP2_K * np.log(grid), color=INK_SECONDARY, ls="--", lw=1.4, label=f"SHRP2 L03: k = {SHRP2_K}")
    gp_k = float(relationship.loc[relationship["facility"].eq("GP"), "local_k"].iloc[0])
    right.plot(grid, 1 + gp_k * np.log(grid), color=GP_COLOR, lw=2.0, label=f"GP local fit: k = {gp_k:.2f}")
    ml = tmc[tmc["facility"].eq("ML")]
    near = int((ml["TTI"].lt(1.1) & ml["PTI95"].lt(1.2)).sum())
    right.annotate(
        f"{near} of {len(ml)} express-lane TMCs\nsit at TTI < 1.1, PTI95 < 1.2",
        xy=(1.03, 1.05), xytext=(2.3, 1.25), fontsize=8.5, color=INK,
        arrowprops={"arrowstyle": "-", "color": INK_SECONDARY, "lw": 0.8},
    )
    right.set_xlabel("Observed TTI (mean over weekdays / free-flow)")
    right.set_ylabel("Observed PTI95")
    right.set_title("(b) Four open corridor-periods, TMC level\nI-95 SB PM, I-95 NB AM, I-395 SB PM, I-395 NB AM", loc="left", fontsize=10, color=INK)
    right.legend(frameon=False, fontsize=8.3, loc="upper left")

    for axis in (left, right):
        axis.grid(color=GRID, lw=0.8)
        axis.set_axisbelow(True)
        axis.spines[["top", "right"]].set_visible(False)
    left.grid(axis="x", visible=False)
    figure.savefig(output, dpi=200, bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    network = load_network()
    ident = load_identification()
    sections = [select_section(pair, network, ident) for pair in PAIRS]
    all_tmcs = set(pd.concat(sections)["tmc_code"])
    for corridor in MANAGED_CORRIDORS:
        all_tmcs |= set(load_reference(corridor, network)["tmc_code"])
    data = read_ritis(all_tmcs)
    sections = [attach_ritis_length(section, data) for section in sections]

    facility_rows: list[dict] = []
    comparisons: list[dict] = []
    daily_frames: list[pd.DataFrame] = []
    tmc_frames: list[pd.DataFrame] = []
    for pair, section in zip(PAIRS, sections):
        daily = route_daily(section, data, pair["period"])
        rows, comparison = summarize_pair(pair, section, daily, data)
        facility_rows.extend(rows)
        comparisons.append(comparison)
        lengths = section.groupby("facility")["miles"].sum()
        daily["pair"] = pair["pair"]
        daily["section_length_mi"] = daily["facility"].map(lengths)
        daily["T_per_ml_section_min"] = daily["T_min"] / daily["section_length_mi"] * lengths["ML"]
        daily_frames.append(daily)
        tmc_frames.append(tmc_reliability(section, data, pair["period"]))

    facility = pd.DataFrame(facility_rows)
    comparison = pd.DataFrame(comparisons)
    daily = pd.concat(daily_frames, ignore_index=True)
    tmc = pd.concat(tmc_frames, ignore_index=True)
    relationship = facility_relationship(tmc)
    audit = parameter_audit(network, data)
    section_map = pd.concat(sections, ignore_index=True)[
        ["pair", "period", "facility", "corridor", "tmc_code", "network_link_id", "AMLIMIT", "PMLIMIT", "identification_miles", "miles", "s_mid"]
    ].sort_values(["pair", "facility", "s_mid"])

    facility.to_csv(OUTPUT / "c6_section_reliability.csv", index=False)
    comparison.to_csv(OUTPUT / "c6_gp_vs_ml_comparison.csv", index=False)
    tmc.to_csv(OUTPUT / "c6_tmc_reliability.csv", index=False)
    relationship.to_csv(OUTPUT / "c6_pti_tti_by_facility.csv", index=False)
    audit.to_csv(OUTPUT / "c6_managed_lane_parameter_audit.csv", index=False)
    section_map.to_csv(OUTPUT / "c6_section_map.csv", index=False)
    plot(daily, comparison, tmc, relationship, FIGURES / "nvta_c6_gp_vs_managed_lane.png")

    pd.set_option("display.width", 200)
    print(facility.round(3).to_string(index=False))
    print(comparison.drop(columns=["saving_basis"]).round(3).to_string(index=False))
    print(relationship.drop(columns=["k_basis"]).round(3).to_string(index=False))
    print(audit.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
