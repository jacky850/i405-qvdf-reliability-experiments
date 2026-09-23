from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_nvta_b1_speed_cutoff import add_b1_fields, aggregate_daily, summarize


def test_b1_link_mile_hours_and_daily_reduction():
    episodes = pd.DataFrame(
        {
            "corridor": ["I-95 NB"] * 4,
            "facility": ["GP"] * 4,
            "tmc_code": ["A", "B", "A", "B"],
            "date_local": ["2025-10-01"] * 4,
            "threshold_multiplier": [0.25, 0.25, 0.50, 0.50],
            "threshold_speed_ratio_to_vf": [0.25, 0.25, 0.50, 0.50],
            "threshold_speed_mph": [17.5, 17.5, 35.0, 35.0],
            "length_mi": [1.0, 2.0, 1.0, 2.0],
            "duration_h": [1.0, 0.0, 1.0, 2.0],
            "episode_identified": [True, False, True, True],
            "touches_data_start": [False] * 4,
            "touches_data_end": [False] * 4,
        }
    )
    enriched = add_b1_fields(episodes)
    daily = aggregate_daily(enriched)
    summary = summarize(enriched, daily)
    gp = summary[summary["facility"] == "GP"].set_index(
        "threshold_speed_ratio_to_vf"
    )

    assert gp.loc[0.25, "mean_daily_congested_link_mile_hours"] == 1.0
    assert gp.loc[0.50, "mean_daily_congested_link_mile_hours"] == 5.0
    assert gp.loc[0.25, "mean_daily_reduction_vs_050_percent"] == 80.0
    assert gp.loc[0.25, "qualifying_tmc_days"] == 1
    assert gp.loc[0.50, "qualifying_tmc_days"] == 2
