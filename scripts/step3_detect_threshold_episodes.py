from pathlib import Path
import sys
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiment_a.core import (
    common_support, detect_threshold_episodes, load_config, load_link_data
)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    config = load_config(root)
    data = load_link_data(root, config)
    params = pd.read_csv(root / "results" / "step1_link_parameters.csv")
    demand = pd.read_csv(root / "results" / "step2_daily_demand.csv")
    episodes = detect_threshold_episodes(data, params, demand, config)
    support = common_support(episodes, config["speed_threshold_multipliers"])
    episodes.to_csv(
        root / "results" / "step3_threshold_episodes.csv",
        index=False, float_format="%.6f"
    )
    support.to_csv(root / "results" / "step3_common_support.csv", index=False)
    summary = episodes.groupby("threshold_multiplier").agg(
        link_days=("episode_identified", "size"),
        identified=("episode_identified", "sum"),
        median_duration_h=("duration_h", "median"),
        min_duration_h=("duration_h", "min"),
        max_duration_h=("duration_h", "max"),
    )
    print(summary.to_string())
    print(f"\nCommon support: {int(support['common_support'].sum())}/{len(support)} link-days")


if __name__ == "__main__":
    main()
