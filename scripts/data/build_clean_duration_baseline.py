
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

SOURCE = ROOT / "datasets" / "prepared" / "clean_duration_dataset.csv"
OUTPUT = (
    ROOT / "datasets" / "prepared"
    / "clean_duration_baseline_by_category.csv"
)

MIN_CATEGORY_SAMPLES = 5


def normalize_category_id(value):
    if pd.isna(value):
        return ""
    value = str(value).strip()
    return value[:-2] if value.endswith(".0") else value


def main():
    if not SOURCE.exists():
        raise FileNotFoundError(f"Clean dataset not found: {SOURCE}")

    df = pd.read_csv(SOURCE)

    required = {
        "session_id",
        "category_id",
        "detected_category",
        "estimated_hours",
    }

    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    df["category_id_key"] = df["category_id"].apply(
        normalize_category_id
    )
    df["category_name_key"] = (
        df["detected_category"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
    )
    df["estimated_hours"] = pd.to_numeric(
        df["estimated_hours"], errors="coerce"
    )

    df = df[
        (df["category_id_key"] != "")
        & (df["category_name_key"] != "")
        & df["estimated_hours"].notna()
        & (df["estimated_hours"] > 0)
        & (df["estimated_hours"] <= 100)
    ].copy()

    baseline = (
        df.groupby(
            ["category_id_key", "category_name_key"],
            dropna=False,
        )
        .agg(
            sample_count=("session_id", "nunique"),
            average_hours=("estimated_hours", "mean"),
            median_hours=("estimated_hours", "median"),
            p75_hours=(
                "estimated_hours",
                lambda values: values.quantile(0.75),
            ),
            p90_hours=(
                "estimated_hours",
                lambda values: values.quantile(0.90),
            ),
            minimum_hours=("estimated_hours", "min"),
            maximum_hours=("estimated_hours", "max"),
        )
        .reset_index()
        .rename(columns={
            "category_id_key": "category_id",
            "category_name_key": "category",
        })
    )

    baseline["data_quality"] = baseline["sample_count"].apply(
        lambda n: (
            "low_data_manual_review"
            if n < MIN_CATEGORY_SAMPLES
            else "preliminary_category_baseline"
        )
    )

    baseline["estimate_source"] = "historical_quoted_hours"
    baseline["training_record_count"] = len(df)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    baseline.to_csv(OUTPUT, index=False)

    print("\n=== Clean category duration baseline ===")
    print(baseline.to_string(index=False))
    print(f"\nSaved: {OUTPUT}")


if __name__ == "__main__":
    main()
