from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiment_a.core import _qualifying_runs, fit_power_curve


def test_qualifying_runs():
    mask = np.array([False, True, True, False, True, True, True, False])
    assert _qualifying_runs(mask, minimum_bins=3) == [(4, 6)]


def test_power_curve_recovery():
    config = {"fit_n_min": 1.0, "fit_n_max": 4.0, "fit_n_step": 0.001}
    x = np.linspace(0.5, 1.2, 50)
    y = 2.5 * x ** 2.2
    fit = fit_power_curve(x, y, config)
    assert abs(fit["fd_h"] - 2.5) < 0.005
    assert abs(fit["n"] - 2.2) < 0.005
    assert fit["rmse_h"] < 1e-6
