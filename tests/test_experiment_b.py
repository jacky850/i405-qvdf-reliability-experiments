import numpy as np
import pandas as pd

from experiment_b.core import (
    detector_day_peaks,
    fit_delay_power_curve,
    fit_sigma_models,
    normal_qq_r2,
    reliability_envelope,
    select_weekdays,
)


def test_select_weekdays_excludes_holiday():
    dates = select_weekdays("2025-06-16", "2025-06-23", 5, ["2025-06-19"])
    assert dates == [
        "2025-06-16", "2025-06-17", "2025-06-18", "2025-06-20", "2025-06-23"
    ]


def test_detector_day_peak_uses_maximum_rolling_hour():
    timestamp = pd.date_range("2025-06-02 06:00", periods=24, freq="5min")
    flow = np.r_[np.full(12, 1000.0), np.full(12, 2000.0)]
    frame = pd.DataFrame(
        {
            "station_id": 1,
            "date_local": "2025-06-02",
            "timestamp_local": timestamp.astype(str),
            "flow_vph_link": flow,
            "speed_mph": 50.0,
            "lanes": 2,
        }
    )
    peak = detector_day_peaks(frame, capacity_per_lane_vph=2000.0, resolution_minutes=5)
    assert peak.iloc[0]["D_vph_link"] == 2000.0
    assert peak.iloc[0]["C_vph_link"] == 4000.0
    assert peak.iloc[0]["dc_ratio"] == 0.5
    assert peak.iloc[0]["peak_window_harmonic_speed_mph"] == 50.0


def test_normal_qq_r2_is_high_for_normal_quantiles():
    values = np.array([-1.64, -1.04, -0.67, -0.39, -0.13, 0.13, 0.39, 0.67, 1.04, 1.64])
    assert normal_qq_r2(values) > 0.99


def test_sigma_model_comparison_returns_constant_and_linear():
    mean_dc = np.array([0.5, 0.7, 0.9, 1.1])
    sigma = np.array([0.04, 0.04, 0.04, 0.04])
    result = fit_sigma_models(mean_dc, sigma)
    assert set(result["model"]) == {"constant", "linear"}
    assert np.isclose(
        result.loc[result["model"].eq("constant"), "intercept"].iloc[0], 0.04
    )


def test_delay_power_curve_recovers_exact_parameters():
    dc = np.linspace(0.4, 1.3, 60)
    tti = 1.0 + 0.24 * dc**3.2
    fit = fit_delay_power_curve(dc, tti)
    assert np.isclose(fit["alpha"], 0.24, rtol=1e-5)
    assert np.isclose(fit["beta"], 3.2, rtol=1e-5)
    assert fit["rmse_tti"] < 1e-8


def test_reliability_envelope_is_ordered_and_mean_preserving():
    result = reliability_envelope(
        np.array([0.8]), alpha=0.15, beta=4.0,
        sigma_ln_dc=0.04, percentiles=[0.5, 0.8, 0.9, 0.95],
    )
    row = result.iloc[0]
    assert row["tti_50"] < row["tti_80"] < row["tti_90"] < row["tti_95"]
    mu = np.log(0.8) - 0.5 * 0.04**2
    expected = 1.0 + 0.15 * np.exp(4.0 * mu + 0.5 * 4.0**2 * 0.04**2)
    assert np.isclose(row["expected_tti"], expected)
