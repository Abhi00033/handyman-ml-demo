
from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error

ROOT = Path(__file__).resolve().parents[2]

DATA_FILE = ROOT / "datasets" / "prepared" / "job_level_dataset.csv"
REPORT_DIR = ROOT / "datasets" / "reports"

RANDOM_STATE = 42
TEST_SIZE = 0.20
MIN_TRAIN_SAMPLES = 5


def main():
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Dataset not found: {DATA_FILE}")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(DATA_FILE)

    required = {
        "session_id",
        "status",
        "category_id",
        "detected_category",
        "estimated_hours",
    }

    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    df["estimated_hours"] = pd.to_numeric(
        df["estimated_hours"], errors="coerce"
    )

    df["category_id"] = (
        df["category_id"]
        .astype("string")
        .str.replace(r"\.0$", "", regex=True)
        .str.strip()
    )

    df["detected_category"] = (
        df["detected_category"].astype("string").str.strip()
    )

    # Keep usable historical quote estimates.
    df = df[
        ~df["status"].astype(str).str.lower().isin(
            ["deleted", "rejected"]
        )
        & df["category_id"].notna()
        & df["detected_category"].notna()
        & df["estimated_hours"].notna()
        & (df["estimated_hours"] > 0)
        & (df["estimated_hours"] <= 100)
    ].copy()

    df = df[
        (df["category_id"] != "")
        & (df["detected_category"] != "")
    ]

    if len(df) < 10:
        raise ValueError(
            f"Not enough usable records for validation: {len(df)}"
        )

    # Split before calculating any baseline.
    train, test = train_test_split(
        df,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
    )

    # Calculate category statistics from training records only.
    baselines = (
        train.groupby(
            ["category_id", "detected_category"],
            dropna=False,
        )["estimated_hours"]
        .agg(
            train_sample_count="count",
            median_hours="median",
            p75_hours=lambda values: values.quantile(0.75),
        )
        .reset_index()
    )

    results = test.merge(
        baselines,
        on=["category_id", "detected_category"],
        how="left",
    )

    # Avoid claiming reliable estimates from tiny training groups.
    results = results[
        results["train_sample_count"] >= MIN_TRAIN_SAMPLES
    ].copy()

    if results.empty:
        raise ValueError(
            "No test records have a category with enough training "
            "examples. Review the split or minimum sample threshold."
        )

    results["absolute_error_median"] = (
        results["estimated_hours"] - results["median_hours"]
    ).abs()

    results["absolute_error_p75"] = (
        results["estimated_hours"] - results["p75_hours"]
    ).abs()

    results["within_p75"] = (
        results["estimated_hours"] <= results["p75_hours"]
    )

    overall = pd.DataFrame([{
        "test_records_evaluated": len(results),
        "category_groups_evaluated": results[
            ["category_id", "detected_category"]
        ].drop_duplicates().shape[0],
        "median_estimate_mae_hours": mean_absolute_error(
            results["estimated_hours"],
            results["median_hours"],
        ),
        "p75_estimate_mae_hours": mean_absolute_error(
            results["estimated_hours"],
            results["p75_hours"],
        ),
        "conservative_coverage_percent": (
            results["within_p75"].mean() * 100
        ),
    }])

    by_category = (
        results.groupby(
            ["category_id", "detected_category"],
            dropna=False,
        )
        .agg(
            test_sample_count=("session_id", "count"),
            train_sample_count=("train_sample_count", "first"),
            median_hours=("median_hours", "first"),
            p75_hours=("p75_hours", "first"),
            median_estimate_mae_hours=(
                "absolute_error_median", "mean"
            ),
            p75_estimate_mae_hours=(
                "absolute_error_p75", "mean"
            ),
            conservative_coverage_percent=(
                "within_p75", lambda values: values.mean() * 100
            ),
        )
        .reset_index()
    )

    overall_path = REPORT_DIR / "duration_validation_summary.csv"
    category_path = REPORT_DIR / "duration_validation_by_category.csv"
    predictions_path = REPORT_DIR / "duration_validation_predictions.csv"

    overall.to_csv(overall_path, index=False)
    by_category.to_csv(category_path, index=False)

    results.to_csv(predictions_path, index=False)

    print("\n=== Overall validation ===")
    print(overall.to_string(index=False))

    print("\n=== Validation by category ===")
    print(by_category.to_string(index=False))

    print("\nReports saved:")
    print(overall_path)
    print(category_path)
    print(predictions_path)


if __name__ == "__main__":
    main()
