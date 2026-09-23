import numpy as np
import pandas as pd

from experiment_a.i5n_conservation import (
    add_conservation_terms,
    maximum_rolling_mean,
)


def test_storage_term_closes_known_conservation_balance():
    frame = pd.DataFrame({
        "segment_id": ["S1", "S1"],
        "date_local": ["2025-07-07", "2025-07-07"],
        "upstream_flow_vph": [100.0, 100.0],
        "downstream_flow_vph": [100.0, 100.0],
        "on_ramp_flow_vph": [12.0, 12.0],
        "off_ramp_flow_vph": [0.0, 0.0],
        "upstream_density_vehpkm": [10.0, 12.0],
        "downstream_density_vehpkm": [10.0, 12.0],
        "length_km": [0.5, 0.5],
    })
    result = add_conservation_terms(frame, bin_hours=1 / 12)
    assert result.loc[0, "storage_change_vph"] == 12.0
    assert result.loc[0, "residual_with_storage_vph"] == 0.0
    assert np.isnan(result.loc[1, "storage_change_vph"])


def test_maximum_rolling_mean_uses_full_window():
    values = pd.Series([1.0] * 12 + [13.0])
    assert maximum_rolling_mean(values, 12) == 2.0
