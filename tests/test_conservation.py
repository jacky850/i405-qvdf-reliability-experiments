from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiment_a.conservation import (
    build_section_timeseries,
    maximum_rolling_hour,
)


def test_maximum_rolling_hour_uses_twelve_five_minute_bins():
    values = pd.Series([1.0] * 12 + [13.0])
    assert maximum_rolling_hour(values) == 2.0


def test_section_conservation_and_missing_off_ramp():
    rows = []
    for time, upstream, on_ramp, off_ramp, downstream in [
        ("06:00", 100.0, 20.0, 10.0, 110.0),
        ("06:05", 120.0, 25.0, np.nan, 130.0),
    ]:
        for station_id, flow in zip(
            [1, 2, 3, 4], [upstream, on_ramp, off_ramp, downstream]
        ):
            rows.append({
                "date_local": "2025-09-05",
                "time_local": time,
                "station_id": station_id,
                "pct_observed": 100.0 if np.isfinite(flow) else 0.0,
                "flow_vph": flow,
            })
    data = pd.DataFrame(rows)
    sections = [{
        "link_id": "L1",
        "upstream_station_id": 1,
        "on_ramp_station_id": 2,
        "off_ramp_station_id": 3,
        "downstream_station_id": 4,
    }]
    result = build_section_timeseries(data, sections)
    assert result.loc[0, "conservation_arrival_vph"] == 110.0
    assert np.isnan(result.loc[1, "conservation_arrival_vph"])
