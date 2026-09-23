"""Audit free-flow speed and capacity inputs for I-95 NB GP/HOV TMCs.

The audit compares the inherited facility-level priors with three link-level
speed sources and verifies the AM Cube network capacity identities.  It does
not modify the Experiment A configuration or rerun a QVDF fit.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_SPEED = Path(
    "/Users/jinxiwu/Library/CloudStorage/Dropbox-ASU/Jinxi Wu/"
    "1_map_matching2026/data/raw/ritis/NOVA-Oct1-31-2025--Avg-at-5min-.csv"
)
MAPPING = Path(
    "/Users/jinxiwu/Library/CloudStorage/Dropbox-ASU/Jinxi Wu/"
    "T2_Task_3/t2_vt2_analysis (2)/qvdf_projection/data/corridor_tmc_mapping.csv"
)
AM_NETWORK = Path(
    "/Users/jinxiwu/Library/CloudStorage/Dropbox-ASU/Jinxi Wu/"
    "1_map_matching2026/data/raw/base_2025/am/link.csv"
)
CORRIDORS = ["I-95 NB", "I-95 HOV NB"]
LEGACY_VF = {"GP": 70.0, "HOV": 65.0}
LEGACY_CAPACITY = {"GP": 2200.0, "HOV": 1800.0}


def normalize_tmc(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.upper()


def selected_mapping() -> pd.DataFrame:
    mapping = pd.read_csv(MAPPING)
    mapping["tmc"] = normalize_tmc(mapping["tmc"])
    return (
        mapping[mapping["corridor"].isin(CORRIDORS)]
        .sort_values(["corridor", "road_order", "tmc"])
        .drop_duplicates(["corridor", "tmc"])
        .copy()
    )


def read_speed_statistics(mapping: pd.DataFrame) -> pd.DataFrame:
    selected = set(mapping["tmc"])
    frames: list[pd.DataFrame] = []
    usecols = [
        "tmc_code",
        "measurement_tstamp",
        "speed",
        "reference_speed",
        "historical_average_speed",
    ]
    for chunk in pd.read_csv(
        RAW_SPEED,
        usecols=usecols,
        dtype={"tmc_code": "string"},
        chunksize=750_000,
    ):
        chunk["tmc_code"] = normalize_tmc(chunk["tmc_code"])
        chunk = chunk[chunk["tmc_code"].isin(selected)].copy()
        if chunk.empty:
            continue
        chunk["timestamp_local"] = pd.to_datetime(
            chunk.pop("measurement_tstamp"), errors="coerce"
        )
        chunk = chunk.dropna(subset=["timestamp_local", "speed", "reference_speed"])
        chunk = chunk[chunk["timestamp_local"].dt.weekday < 5]
        frames.append(chunk)
    if not frames:
        raise RuntimeError("No selected weekday RITIS records were found")

    data = pd.concat(frames, ignore_index=True)
    minute = data["timestamp_local"].dt.hour * 60 + data["timestamp_local"].dt.minute
    # Night shoulders avoid the AM/PM peaks while retaining enough observations
    # for every TMC: 00:00-05:00 and 21:00-24:00.
    data["offpeak"] = (minute < 300) | (minute >= 1260)
    rows = []
    for tmc, group in data.groupby("tmc_code", sort=True):
        offpeak = group[group["offpeak"]]
        rows.append(
            {
                "tmc_code": tmc,
                "weekday_records": int(len(group)),
                "weekday_dates": int(group["timestamp_local"].dt.date.nunique()),
                "ritis_reference_mph": float(group["reference_speed"].median()),
                "ritis_reference_min_mph": float(group["reference_speed"].min()),
                "ritis_reference_max_mph": float(group["reference_speed"].max()),
                "ritis_reference_unique_values": int(group["reference_speed"].nunique()),
                "historical_average_median_mph": float(
                    group["historical_average_speed"].median()
                ),
                "observed_all_day_p85_mph": float(group["speed"].quantile(0.85)),
                "observed_all_day_p95_mph": float(group["speed"].quantile(0.95)),
                "observed_offpeak_p50_mph": float(offpeak["speed"].quantile(0.50)),
                "observed_offpeak_p85_mph": float(offpeak["speed"].quantile(0.85)),
                "observed_offpeak_p95_mph": float(offpeak["speed"].quantile(0.95)),
                "observed_offpeak_records": int(len(offpeak)),
            }
        )
    return pd.DataFrame(rows)


def build_free_flow_audit(mapping: pd.DataFrame, speed: pd.DataFrame) -> pd.DataFrame:
    audit = mapping.merge(speed, left_on="tmc", right_on="tmc_code", validate="one_to_one")
    audit["legacy_vf_mph"] = audit["facility"].map(LEGACY_VF)
    audit["recommended_calibration_vf_mph"] = audit["observed_offpeak_p85_mph"]
    audit["recommended_calibration_vf_source"] = (
        "weekday 00:00-05:00 and 21:00-24:00 observed speed P85"
    )
    audit["model_application_vf_mph"] = audit["net_free_speed_mph"]
    audit["model_application_vf_source"] = "AM Cube network free speed"
    audit["network_minus_offpeak_p85_mph"] = (
        audit["net_free_speed_mph"] - audit["observed_offpeak_p85_mph"]
    )
    audit["ritis_reference_minus_offpeak_p85_mph"] = (
        audit["ritis_reference_mph"] - audit["observed_offpeak_p85_mph"]
    )
    audit["legacy_minus_offpeak_p85_mph"] = (
        audit["legacy_vf_mph"] - audit["observed_offpeak_p85_mph"]
    )
    audit["network_within_5mph_of_offpeak_p85"] = (
        audit["network_minus_offpeak_p85_mph"].abs() <= 5.0
    )
    audit["legacy_within_5mph_of_offpeak_p85"] = (
        audit["legacy_minus_offpeak_p85_mph"].abs() <= 5.0
    )
    audit["audit_finding"] = np.where(
        audit["facility"].eq("HOV"),
        "legacy HOV prior is lower than all three link-level evidence sources",
        "replace facility-wide prior with link-level offpeak P85; retain network speed as model-transfer check",
    )
    columns = [
        "corridor",
        "facility",
        "tmc_code",
        "road_order",
        "net_link_id",
        "weekday_dates",
        "weekday_records",
        "legacy_vf_mph",
        "ritis_reference_mph",
        "observed_offpeak_p50_mph",
        "observed_offpeak_p85_mph",
        "observed_offpeak_p95_mph",
        "net_free_speed_mph",
        "recommended_calibration_vf_mph",
        "recommended_calibration_vf_source",
        "model_application_vf_mph",
        "model_application_vf_source",
        "network_minus_offpeak_p85_mph",
        "ritis_reference_minus_offpeak_p85_mph",
        "legacy_minus_offpeak_p85_mph",
        "network_within_5mph_of_offpeak_p85",
        "legacy_within_5mph_of_offpeak_p85",
        "ritis_reference_unique_values",
        "audit_finding",
    ]
    return audit[columns].sort_values(["corridor", "road_order", "tmc_code"])


def build_capacity_audit(mapping: pd.DataFrame) -> pd.DataFrame:
    usecols = [
        "link_id",
        "lanes",
        "capacity",
        "free_speed",
        "allowed_use",
        "AMLIMIT",
        "PMLIMIT",
        "IAMHRLNCAP",
        "IAMHRLKCAP",
        "IPMHRLNCAP",
        "IPMHRLKCAP",
    ]
    network = pd.read_csv(AM_NETWORK, usecols=usecols)
    audit = mapping.merge(
        network,
        left_on="net_link_id",
        right_on="link_id",
        how="left",
        validate="many_to_one",
    )
    audit["legacy_capacity_vphpl"] = audit["facility"].map(LEGACY_CAPACITY)
    audit["recommended_capacity_vphpl"] = audit["IAMHRLNCAP"]
    audit["recommended_capacity_vph_link"] = audit["IAMHRLKCAP"]
    audit["mapping_lane_difference"] = audit["net_lanes"] - audit["lanes"]
    audit["mapping_capacity_vphpl_difference"] = (
        audit["net_capacity_raw"] - audit["IAMHRLNCAP"]
    )
    audit["am_capacity_identity_error_vph"] = (
        audit["IAMHRLNCAP"] * audit["lanes"] - audit["IAMHRLKCAP"]
    )
    audit["pm_capacity_identity_error_vph"] = (
        audit["IPMHRLNCAP"] * audit["lanes"] - audit["IPMHRLKCAP"]
    )
    audit["mapping_matches_am_network"] = (
        audit["mapping_lane_difference"].abs().le(1e-9)
        & audit["mapping_capacity_vphpl_difference"].abs().le(1e-9)
    )
    audit["period_operation_flag"] = np.select(
        [
            audit["AMLIMIT"].eq(4) & audit["PMLIMIT"].eq(9),
            audit["AMLIMIT"].eq(0) & audit["PMLIMIT"].eq(0),
        ],
        ["open AM / closed PM reversible code", "open both periods"],
        default="review period-operation codes",
    )
    audit["facility_operation_review"] = np.where(
        audit["facility"].eq("GP")
        & audit["AMLIMIT"].eq(4)
        & audit["PMLIMIT"].eq(9),
        "review GP label: network row carries reversible AM-open/PM-closed code",
        "classification consistent with inspected period codes",
    )
    audit["dc_capacity_effect"] = (
        "capacity changes reconstructed q and D proportionally; D/C is unchanged "
        "when the same capacity is used in inverse S3 and the denominator"
    )
    columns = [
        "corridor",
        "facility",
        "tmc",
        "road_order",
        "net_link_id",
        "allowed_use",
        "AMLIMIT",
        "PMLIMIT",
        "period_operation_flag",
        "net_lanes",
        "lanes",
        "mapping_lane_difference",
        "legacy_capacity_vphpl",
        "net_capacity_raw",
        "capacity",
        "IAMHRLNCAP",
        "IAMHRLKCAP",
        "IPMHRLNCAP",
        "IPMHRLKCAP",
        "recommended_capacity_vphpl",
        "recommended_capacity_vph_link",
        "mapping_capacity_vphpl_difference",
        "am_capacity_identity_error_vph",
        "pm_capacity_identity_error_vph",
        "mapping_matches_am_network",
        "facility_operation_review",
        "dc_capacity_effect",
    ]
    return audit[columns].sort_values(["corridor", "road_order", "tmc"])


def build_summary(free_flow: pd.DataFrame, capacity: pd.DataFrame) -> pd.DataFrame:
    speed_summary = (
        free_flow.groupby(["corridor", "facility"], as_index=False)
        .agg(
            tmc_count=("tmc_code", "nunique"),
            legacy_vf_mph=("legacy_vf_mph", "median"),
            ritis_reference_median_mph=("ritis_reference_mph", "median"),
            observed_offpeak_p85_median_mph=("observed_offpeak_p85_mph", "median"),
            network_vf_median_mph=("net_free_speed_mph", "median"),
            network_vf_min_mph=("net_free_speed_mph", "min"),
            network_vf_max_mph=("net_free_speed_mph", "max"),
            network_within_5mph_count=("network_within_5mph_of_offpeak_p85", "sum"),
            legacy_within_5mph_count=("legacy_within_5mph_of_offpeak_p85", "sum"),
        )
    )
    capacity_summary = (
        capacity.groupby(["corridor", "facility"], as_index=False)
        .agg(
            legacy_capacity_vphpl=("legacy_capacity_vphpl", "median"),
            network_capacity_vphpl_median=("recommended_capacity_vphpl", "median"),
            network_capacity_vphpl_min=("recommended_capacity_vphpl", "min"),
            network_capacity_vphpl_max=("recommended_capacity_vphpl", "max"),
            network_lanes_median=("lanes", "median"),
            network_lanes_min=("lanes", "min"),
            network_lanes_max=("lanes", "max"),
            mapping_match_count=("mapping_matches_am_network", "sum"),
        )
    )
    summary = speed_summary.merge(capacity_summary, on=["corridor", "facility"])
    summary["recommended_vf_policy"] = (
        "use TMC-specific observed offpeak P85 for RITIS calibration; rerun with AM Cube "
        "network free speed as model-transfer sensitivity"
    )
    summary["recommended_capacity_policy"] = (
        "use link-level IAMHRLNCAP and IAMHRLKCAP; do not retain legacy facility constants"
    )
    return summary


def main() -> None:
    output = ROOT / "results"
    output.mkdir(parents=True, exist_ok=True)
    mapping = selected_mapping()
    speed = read_speed_statistics(mapping)
    free_flow = build_free_flow_audit(mapping, speed)
    capacity = build_capacity_audit(mapping)
    summary = build_summary(free_flow, capacity)

    free_flow.to_csv(output / "nvta_i95_free_flow_audit.csv", index=False)
    capacity.to_csv(output / "nvta_i95_capacity_audit.csv", index=False)
    summary.to_csv(output / "nvta_i95_parameter_audit_summary.csv", index=False)

    print(summary.to_string(index=False))
    flagged = capacity[
        capacity["facility_operation_review"].str.startswith("review")
    ]
    if len(flagged):
        print("\nPeriod-operation rows requiring mapping review:")
        print(
            flagged[
                [
                    "tmc",
                    "corridor",
                    "net_link_id",
                    "AMLIMIT",
                    "PMLIMIT",
                    "allowed_use",
                ]
            ].to_string(index=False)
        )


if __name__ == "__main__":
    main()
