from pathlib import Path
import sys
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiment_a.core import compute_daily_demand, load_config, load_link_data


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    config = load_config(root)
    data = load_link_data(root, config)
    params = pd.read_csv(root / "results" / "step1_link_parameters.csv")
    result = compute_daily_demand(data, params, config)
    output = root / "results" / "step2_daily_demand.csv"
    result.to_csv(output, index=False, float_format="%.6f")
    summary = result.groupby("link_id")["demand_capacity_ratio"].agg(
        ["count", "min", "median", "max"]
    )
    print(summary.to_string())
    print(f"\nSaved: {output}")


if __name__ == "__main__":
    main()
