from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from experiment_a.core import estimate_link_parameters, load_config, load_link_data


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    config = load_config(root)
    data = load_link_data(root, config)
    result = estimate_link_parameters(data, config)
    output = root / "results" / "step1_link_parameters.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False, float_format="%.6f")
    print(result.to_string(index=False))
    print(f"\nSaved: {output}")


if __name__ == "__main__":
    main()
