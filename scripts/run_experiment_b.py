#!/usr/bin/env python3
"""Run Experiment B from detector-day preparation through the envelope."""

from pathlib import Path
import subprocess
import sys


def main() -> None:
    scripts = Path(__file__).resolve().parent
    for step in [
        "b1_prepare_detector_days.py",
        "b2_calibrate_sigma.py",
        "b3_reliability_envelope.py",
    ]:
        print(f"\n=== Running {step} ===")
        subprocess.run([sys.executable, str(scripts / step)], check=True)


if __name__ == "__main__":
    main()
