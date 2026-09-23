"""Shared locations for the NVTA C-series scripts.

The RITIS speed file, the CBI calibration package, and the Cube network are
licensed project inputs and are not redistributed in this repository. Point
``NVTA_EXTERNAL_ROOT`` at the folder that contains them to rerun the scripts.
"""

from __future__ import annotations

import os
from pathlib import Path


NVTA_DIR = Path(__file__).resolve().parent
REPO_ROOT = NVTA_DIR.parent

EXTERNAL_ROOT = Path(
    os.environ.get(
        "NVTA_EXTERNAL_ROOT",
        "/Users/jinxiwu/Library/CloudStorage/Dropbox-ASU/Jinxi Wu",
    )
)
RITIS_RAW = EXTERNAL_ROOT / "1_map_matching2026/data/raw/ritis/NOVA-Oct1-31-2025--Avg-at-5min-.csv"
RITIS_TMC_IDENTIFICATION = EXTERNAL_ROOT / "1_map_matching2026/data/raw/ritis/TMC_Identification.csv"
CUBE_AM_NETWORK = EXTERNAL_ROOT / "1_map_matching2026/data/raw/base_2025/am/link.csv"
CBI = EXTERNAL_ROOT / "link-queue-simulation/link-queue-simulation/cbi"


def experiment_dirs(name: str) -> tuple[Path, Path]:
    """Return (output, figures) folders for one experiment, creating them."""
    base = NVTA_DIR / name
    output = base / "output"
    figures = base / "figures"
    output.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    return output, figures
