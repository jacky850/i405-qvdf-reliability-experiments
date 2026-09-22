from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiment_a.core import bootstrap_fit, fit_power_curve, load_config


PRIMARY_BASIS = "duration_qvdf_capacity_equivalent_hours"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    config = load_config(root)
    episodes = pd.read_csv(root / "results" / "step3_threshold_episodes.csv")
    support = pd.read_csv(root / "results" / "step3_common_support.csv")
    keys = support.loc[support["common_support"], ["link_id", "date_local"]]
    data = episodes.merge(keys, on=["link_id", "date_local"], how="inner")

    summary_rows = []
    prediction_rows = []
    fit_bases = [(PRIMARY_BASIS, "capacity_equivalent_hours")]
    scopes = [("pooled", "ALL", data)]
    scopes += [("link", link, group) for link, group in data.groupby("link_id")]

    for fit_basis, x_column in fit_bases:
        for scope, link_id, scope_data in scopes:
            for multiplier, group in scope_data.groupby("threshold_multiplier"):
                x = group[x_column].to_numpy(float)
                y = group["duration_h"].to_numpy(float)
                fit = fit_power_curve(x, y, config)
                ci = bootstrap_fit(x, y, config) if (
                    scope == "pooled" and fit_basis == PRIMARY_BASIS
                ) else {
                    "fd_ci_low": np.nan,
                    "fd_ci_high": np.nan,
                    "n_ci_low": np.nan,
                    "n_ci_high": np.nan,
                }
                if "fd_ci_low_h" in ci:
                    ci["fd_ci_low"] = ci.pop("fd_ci_low_h")
                    ci["fd_ci_high"] = ci.pop("fd_ci_high_h")
                summary_rows.append({
                    "fit_basis": fit_basis,
                    "x_column": x_column,
                    "scope": scope,
                    "link_id": link_id,
                    "threshold_multiplier": multiplier,
                    "observations": len(group),
                    "fd": fit["fd_h"],
                    "n": fit["n"],
                    "r_squared": fit["r_squared"],
                    "rmse_h": fit["rmse_h"],
                    "n_at_boundary": fit["n_at_boundary"],
                    **ci,
                })
                for (_, row), predicted in zip(group.iterrows(), fit["predicted"]):
                    prediction_rows.append({
                        "fit_basis": fit_basis,
                        "x_column": x_column,
                        "scope": scope,
                        "fit_link_id": link_id,
                        "link_id": row["link_id"],
                        "date_local": row["date_local"],
                        "threshold_multiplier": multiplier,
                        "x_value": row[x_column],
                        "observed_duration_h": row["duration_h"],
                        "predicted_duration_h": predicted,
                        "residual_h": row["duration_h"] - predicted,
                    })

    summary = pd.DataFrame(summary_rows)
    pooled_mask = summary["scope"].eq("pooled")
    for fit_basis in summary["fit_basis"].unique():
        basis_mask = pooled_mask & summary["fit_basis"].eq(fit_basis)
        baseline = summary[
            basis_mask & np.isclose(summary["threshold_multiplier"], 1.0)
        ].iloc[0]
        summary.loc[basis_mask, "fd_change_vs_1pct"] = (
            (summary.loc[basis_mask, "fd"] / baseline["fd"] - 1.0) * 100.0
        )
        summary.loc[basis_mask, "n_change_vs_1pct"] = (
            (summary.loc[basis_mask, "n"] / baseline["n"] - 1.0) * 100.0
        )

    summary.to_csv(
        root / "results" / "step4_qvdf_fit_summary.csv",
        index=False, float_format="%.6f"
    )
    pd.DataFrame(prediction_rows).to_csv(
        root / "results" / "step4_qvdf_predictions.csv",
        index=False, float_format="%.6f"
    )

    primary = summary[pooled_mask & summary["fit_basis"].eq(PRIMARY_BASIS)].copy()
    verdict = {
        "common_support_link_days": int(len(keys)),
        "thresholds": config["speed_threshold_multipliers"],
        "primary_fit_basis": PRIMARY_BASIS,
        "basis_note": (
            "congested passed volume divided by hourly capacity; units are hours, "
            "not dimensionless rate-based D/C"
        ),
        "pooled_fd_range": [float(primary["fd"].min()), float(primary["fd"].max())],
        "pooled_n_range": [float(primary["n"].min()), float(primary["n"].max())],
        "pooled_r_squared_range": [
            float(primary["r_squared"].min()), float(primary["r_squared"].max())
        ],
        "pooled_rmse_range_h": [
            float(primary["rmse_h"].min()), float(primary["rmse_h"].max())
        ],
        "any_primary_n_at_boundary": bool(primary["n_at_boundary"].any()),
    }
    with (root / "results" / "experiment_a_summary.json").open("w", encoding="utf-8") as f:
        json.dump(verdict, f, indent=2)

    print("Duration-QVDF capacity-equivalent-hours basis:")
    print(primary[[
        "threshold_multiplier", "observations", "fd", "n", "r_squared",
        "rmse_h", "fd_change_vs_1pct", "n_change_vs_1pct", "n_at_boundary"
    ]].to_string(index=False))

if __name__ == "__main__":
    main()
