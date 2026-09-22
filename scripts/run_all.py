from pathlib import Path
import subprocess
import sys


def main() -> None:
    scripts = Path(__file__).resolve().parent
    steps = [
        "step1_estimate_link_parameters.py",
        "step2_compute_daily_demand.py",
        "step3_detect_threshold_episodes.py",
        "step4_fit_qvdf.py",
        "step5_make_figures.py",
    ]
    for step in steps:
        print(f"\n=== Running {step} ===")
        subprocess.run([sys.executable, str(scripts / step)], check=True)


if __name__ == "__main__":
    main()
