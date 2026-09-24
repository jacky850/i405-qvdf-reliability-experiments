"""Shared RITIS helpers for the NVTA scripts: corridor TMCs and cached 5-minute records."""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from paths import CBI, CUBE_AM_NETWORK, NVTA_DIR, RITIS_RAW

# Licensed data: the cache lives inside the repo but is gitignored.
CACHE = NVTA_DIR / ".cache"


def normalize_tmc(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.upper()


def gp_corridor(corridor: str) -> pd.DataFrame:
    """Unrestricted mainline GP TMCs of a CBI corridor, in road order."""
    reference = pd.read_csv(CBI / corridor / "01-input-and-qc/link_reference.csv", dtype={"tmc_code": "string"})
    reference["tmc_code"] = normalize_tmc(reference["tmc_code"])
    network = pd.read_csv(
        CUBE_AM_NETWORK, usecols=["link_id", "AMLIMIT", "PMLIMIT", "STREETNAME"], low_memory=False
    )
    reference = reference.merge(network, left_on="network_link_id", right_on="link_id", how="left")
    keep = reference["AMLIMIT"].eq(0) & reference["PMLIMIT"].eq(0) & reference["STREETNAME"].ne("ramp")
    return reference.loc[keep, ["tmc_code", "road_order", "length_mi"]].sort_values("road_order").reset_index(drop=True)


def read_ritis(tmcs: set[str]) -> pd.DataFrame:
    """Weekday 5-minute RITIS records for the given TMCs, cached by TMC set."""
    CACHE.mkdir(exist_ok=True)
    key = hashlib.md5(",".join(sorted(tmcs)).encode()).hexdigest()[:12]
    cached = CACHE / f"ritis_{key}.csv.gz"
    if cached.exists():
        data = pd.read_csv(cached, dtype={"tmc_code": "string"}, parse_dates=["timestamp"])
    else:
        frames = []
        for chunk in pd.read_csv(
            RITIS_RAW,
            usecols=["tmc_code", "measurement_tstamp", "speed", "reference_speed", "travel_time_minutes"],
            dtype={"tmc_code": "string"},
            chunksize=1_000_000,
        ):
            chunk["tmc_code"] = normalize_tmc(chunk["tmc_code"])
            frames.append(chunk[chunk["tmc_code"].isin(tmcs)])
        data = pd.concat(frames, ignore_index=True).rename(columns={"measurement_tstamp": "timestamp"})
        data["timestamp"] = pd.to_datetime(data["timestamp"])
        data.to_csv(cached, index=False)
    data = data[data["timestamp"].dt.weekday < 5].copy()
    data["date_local"] = data["timestamp"].dt.date.astype(str)
    data["minute"] = data["timestamp"].dt.hour * 60 + data["timestamp"].dt.minute
    return data


def free_flow_speed(data: pd.DataFrame) -> pd.Series:
    """Per-TMC free-flow speed: weekday off-peak (21:00-05:00) speed P85, as in A1/A2."""
    off_peak = data[(data["minute"] >= 21 * 60) | (data["minute"] < 5 * 60)]
    return off_peak.groupby("tmc_code")["speed"].quantile(0.85).rename("vf_mph")


def ritis_length(data: pd.DataFrame) -> pd.Series:
    """Length implied by RITIS travel time and speed, so T and T0 share one length."""
    return (data["travel_time_minutes"] * data["speed"] / 60.0).groupby(data["tmc_code"]).median().rename("length_mi")


def smoothed_speed(data: pd.DataFrame, bins: int = 3) -> pd.Series:
    """Centered rolling median of speed within each TMC-day."""
    ordered = data.sort_values(["tmc_code", "date_local", "minute"])
    smooth = ordered.groupby(["tmc_code", "date_local"])["speed"].transform(
        lambda s: s.rolling(bins, center=True, min_periods=1).median()
    )
    return smooth.reindex(data.index)


def quantile_or_nan(values: np.ndarray, q: float) -> float:
    values = values[np.isfinite(values)]
    return float(np.quantile(values, q)) if len(values) else float("nan")
