"""Core calculations for Experiment B.

The functions here contain no project-specific file paths so the numerical
contract can be tested independently of the large PeMS source files.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd
from statistics import NormalDist


KMH_TO_MPH = 0.621371192237334


def select_weekdays(
    start: str,
    end: str,
    count: int,
    excluded_dates: Iterable[str],
) -> list[str]:
    """Return the first ``count`` Monday-Friday dates after exclusions."""

    excluded = set(excluded_dates)
    dates = [
        value.strftime("%Y-%m-%d")
        for value in pd.date_range(start, end, freq="B")
        if value.strftime("%Y-%m-%d") not in excluded
    ]
    if len(dates) < count:
        raise ValueError(f"Only {len(dates)} eligible weekdays, need {count}.")
    return dates[:count]


def add_peak_hour_statistics(
    frame: pd.DataFrame,
    group_columns: list[str],
    bins_per_hour: int,
) -> pd.DataFrame:
    """Add trailing-hour flow and harmonic-speed statistics.

    ``flow_vph_link`` must be a whole-detector rate and ``speed_mph`` must be
    positive. Input rows must already be sorted at regular 5-minute spacing.
    """

    result = frame.copy()
    grouped = result.groupby(group_columns, sort=False)
    result["rolling_60min_flow_vph_link"] = grouped["flow_vph_link"].transform(
        lambda values: values.rolling(bins_per_hour, min_periods=bins_per_hour).mean()
    )
    inverse_speed = 1.0 / result["speed_mph"].clip(lower=1e-9)
    result["rolling_60min_mean_inverse_speed"] = inverse_speed.groupby(
        [result[column] for column in group_columns], sort=False
    ).transform(
        lambda values: values.rolling(bins_per_hour, min_periods=bins_per_hour).mean()
    )
    return result


def detector_day_peaks(
    frame: pd.DataFrame,
    capacity_per_lane_vph: float,
    resolution_minutes: int,
) -> pd.DataFrame:
    """Return one deterministic-capacity D/C record per detector-day."""

    group_columns = ["station_id", "date_local"]
    ordered = frame.sort_values(group_columns + ["timestamp_local"]).copy()
    expected_bins = int(60 / resolution_minutes)
    rolled = add_peak_hour_statistics(ordered, group_columns, expected_bins)
    index = rolled.groupby(group_columns)["rolling_60min_flow_vph_link"].idxmax()
    peak = rolled.loc[index].copy()

    peak_end = pd.to_datetime(peak["timestamp_local"]) + pd.Timedelta(
        minutes=resolution_minutes
    )
    peak_start = peak_end - pd.Timedelta(minutes=60)
    peak["peak_window_start_local"] = peak_start.dt.strftime("%Y-%m-%dT%H:%M:%S")
    peak["peak_window_end_local"] = peak_end.dt.strftime("%Y-%m-%dT%H:%M:%S")
    peak["D_vph_link"] = peak["rolling_60min_flow_vph_link"]
    peak["C_vph_link"] = capacity_per_lane_vph * peak["lanes"]
    peak["dc_ratio"] = peak["D_vph_link"] / peak["C_vph_link"]
    peak["ln_dc"] = np.log(peak["dc_ratio"])
    peak["peak_window_harmonic_speed_mph"] = 1.0 / peak[
        "rolling_60min_mean_inverse_speed"
    ]
    return peak


def normal_qq_r2(values: np.ndarray) -> float:
    """Squared correlation of ordered observations and normal quantiles."""

    ordered = np.sort(np.asarray(values, dtype=float))
    count = len(ordered)
    if count < 3 or np.allclose(ordered, ordered[0]):
        return float("nan")
    distribution = NormalDist()
    theoretical = np.array(
        [distribution.inv_cdf((rank - 0.375) / (count + 0.25)) for rank in range(1, count + 1)]
    )
    correlation = np.corrcoef(theoretical, ordered)[0, 1]
    return float(correlation * correlation)


def fit_sigma_models(mean_dc: np.ndarray, sigma_ln_dc: np.ndarray) -> pd.DataFrame:
    """Compare constant and linear sigma models with AICc and LOOCV."""

    x = np.asarray(mean_dc, dtype=float)
    y = np.asarray(sigma_ln_dc, dtype=float)
    designs = {
        "constant": np.ones((len(x), 1)),
        "linear": np.column_stack([np.ones(len(x)), x]),
    }
    rows: list[dict[str, float | str]] = []
    for name, design in designs.items():
        coefficients = np.linalg.lstsq(design, y, rcond=None)[0]
        fitted = design @ coefficients
        residuals = y - fitted
        rss = float(np.sum(residuals**2))
        count = len(y)
        parameters = design.shape[1]
        aic = float(count * np.log(rss / count) + 2 * parameters)
        aicc = float(aic + 2 * parameters * (parameters + 1) / (count - parameters - 1))
        total = float(np.sum((y - y.mean()) ** 2))
        r_squared = float(1.0 - rss / total) if total > 0 else float("nan")

        loo_predictions = []
        for held_out in range(count):
            keep = np.arange(count) != held_out
            loo_coefficients = np.linalg.lstsq(design[keep], y[keep], rcond=None)[0]
            loo_predictions.append(float(design[held_out] @ loo_coefficients))
        loocv_rmse = float(np.sqrt(np.mean((y - np.array(loo_predictions)) ** 2)))
        rows.append(
            {
                "model": name,
                "intercept": float(coefficients[0]),
                "slope": float(coefficients[1]) if len(coefficients) > 1 else 0.0,
                "parameter_count": parameters,
                "rss": rss,
                "rmse": float(np.sqrt(rss / count)),
                "r_squared": r_squared,
                "aic": aic,
                "aicc": aicc,
                "loocv_rmse": loocv_rmse,
            }
        )
    return pd.DataFrame(rows)


def fit_delay_power_curve(
    dc_ratio: np.ndarray,
    tti: np.ndarray,
    beta_min: float = 0.05,
    beta_max: float = 10.0,
) -> dict[str, float | int]:
    """Fit ``TTI = 1 + alpha * (D/C)**beta`` in TTI space.

    For a fixed beta, the non-negative least-squares estimate of alpha has a
    closed form. A bounded one-dimensional search then selects beta. This
    avoids adding a SciPy dependency to the reproducible experiment.
    """

    x_all = np.asarray(dc_ratio, dtype=float)
    tti_all = np.asarray(tti, dtype=float)
    valid = np.isfinite(x_all) & np.isfinite(tti_all) & (x_all > 0) & (tti_all > 0)
    x = x_all[valid]
    observed_delay = tti_all[valid] - 1.0
    if len(x) < 3:
        raise ValueError("At least three valid D/C and TTI observations are required.")
    if not 0 < beta_min < beta_max:
        raise ValueError("Require 0 < beta_min < beta_max.")

    def evaluate(beta: float) -> tuple[float, float]:
        basis = np.power(x, beta)
        alpha = max(float(np.dot(basis, observed_delay) / np.dot(basis, basis)), 0.0)
        residual = observed_delay - alpha * basis
        return float(np.dot(residual, residual)), alpha

    # Locate the best basin first, then refine it with a golden-section search.
    grid = np.linspace(beta_min, beta_max, 2001)
    grid_rss = np.array([evaluate(value)[0] for value in grid])
    best_index = int(np.argmin(grid_rss))
    lower = float(grid[max(0, best_index - 1)])
    upper = float(grid[min(len(grid) - 1, best_index + 1)])
    if best_index == 0:
        lower, upper = beta_min, float(grid[1])
    elif best_index == len(grid) - 1:
        lower, upper = float(grid[-2]), beta_max

    golden = (np.sqrt(5.0) - 1.0) / 2.0
    left = upper - golden * (upper - lower)
    right = lower + golden * (upper - lower)
    left_rss = evaluate(left)[0]
    right_rss = evaluate(right)[0]
    for _ in range(80):
        if left_rss <= right_rss:
            upper, right, right_rss = right, left, left_rss
            left = upper - golden * (upper - lower)
            left_rss = evaluate(left)[0]
        else:
            lower, left, left_rss = left, right, right_rss
            right = lower + golden * (upper - lower)
            right_rss = evaluate(right)[0]

    beta = float((lower + upper) / 2.0)
    rss, alpha = evaluate(beta)
    fitted_tti = 1.0 + alpha * np.power(x, beta)
    residual_tti = tti_all[valid] - fitted_tti
    total = float(np.sum((tti_all[valid] - np.mean(tti_all[valid])) ** 2))
    return {
        "alpha": alpha,
        "beta": beta,
        "observations": int(len(x)),
        "excluded_observations": int(len(x_all) - len(x)),
        "rss_tti": rss,
        "rmse_tti": float(np.sqrt(np.mean(residual_tti**2))),
        "mae_tti": float(np.mean(np.abs(residual_tti))),
        "r_squared_tti": float(1.0 - rss / total) if total > 0 else float("nan"),
        "beta_at_boundary": bool(
            np.isclose(beta, beta_min, atol=1e-5)
            or np.isclose(beta, beta_max, atol=1e-5)
        ),
    }


def reliability_envelope(
    mean_dc: np.ndarray,
    alpha: float,
    beta: float,
    sigma_ln_dc: float | np.ndarray,
    percentiles: Iterable[float],
) -> pd.DataFrame:
    """Return QVDF travel-time percentiles for lognormal daily D/C.

    ``mean_dc`` is the arithmetic mean of D/C. Therefore
    ``mu_ln_dc = ln(mean_dc) - sigma**2 / 2`` preserves that mean under the
    lognormal model.
    """

    x = np.asarray(mean_dc, dtype=float)
    sigma = np.broadcast_to(np.asarray(sigma_ln_dc, dtype=float), x.shape)
    if np.any(x <= 0) or np.any(sigma < 0):
        raise ValueError("mean D/C must be positive and sigma must be non-negative.")
    if alpha < 0 or beta <= 0:
        raise ValueError("alpha must be non-negative and beta must be positive.")

    mu = np.log(x) - 0.5 * sigma**2
    output = pd.DataFrame(
        {
            "mean_dc": x,
            "mu_ln_dc": mu,
            "sigma_ln_dc": sigma,
        }
    )
    expected_delay_ratio = alpha * np.exp(beta * mu + 0.5 * beta**2 * sigma**2)
    output["expected_tti"] = 1.0 + expected_delay_ratio
    output["shrp2_tti95"] = 1.0 + 3.67 * np.log(output["expected_tti"])

    normal = NormalDist()
    for percentile in percentiles:
        if not 0 < percentile < 1:
            raise ValueError("Percentiles must be strictly between zero and one.")
        label = f"{int(round(percentile * 100)):02d}"
        z_value = normal.inv_cdf(float(percentile))
        tti = 1.0 + alpha * np.exp(beta * mu + z_value * beta * sigma)
        output[f"tti_{label}"] = tti
        output[f"gamma_{label}"] = tti / output["expected_tti"]
        output[f"delay_dominant_gamma_{label}"] = np.exp(
            z_value * beta * sigma - 0.5 * beta**2 * sigma**2
        )
    return output
