"""
Validate the automatic quoted-hours baseline with a held-out split.

Reads:
  datasets/prepared/automatically_clean_duration_dataset.csv

Writes:
  datasets/reports/automatic_duration_validation_summary.csv
  datasets/reports/automatic_duration_validation_by_category.csv
  datasets/reports/automatic_duration_validation_predictions.csv

This validates prediction of historical QUOTED HOURS, not actual hands-on duration.
It does not modify the database or the source dataset.
Run from the project root:
  python -m scripts.audit.validate_automatic_duration_baseline
"""
from pathlib import Path
import pandas as pd
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).resolve().parents[2]
DATA_FILE = ROOT / "datasets" / "prepared" / "automatically_clean_duration_dataset.csv"
REPORT_DIR = ROOT / "datasets" / "reports"
SUMMARY_FILE = REPORT_DIR / "automatic_duration_validation_summary.csv"
CATEGORY_FILE = REPORT_DIR / "automatic_duration_validation_by_category.csv"
PREDICTIONS_FILE = REPORT_DIR / "automatic_duration_validation_predictions.csv"

TEST_SIZE = 0.20
RANDOM_STATE = 42
MIN_TRAIN_SAMPLES_FOR_CATEGORY_METRIC = 2


def main():
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            f"Missing {DATA_FILE}. Run rebuild_duration_pipeline first."
        )

    df = pd.read_csv(DATA_FILE)
    required = {"session_id", "category_id", "detected_category", "estimated_hours"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Dataset is missing required columns: {sorted(missing)}. "
            f"Found columns: {list(df.columns)}"
        )

    df["estimated_hours"] = pd.to_numeric(df["estimated_hours"], errors="coerce")
    df["category_id"] = pd.to_numeric(df["category_id"], errors="coerce")
    df = df.dropna(subset=["session_id", "category_id", "detected_category", "estimated_hours"])
    df = df[(df["estimated_hours"] > 0) & (df["estimated_hours"] <= 100)]
    df = df.drop_duplicates(subset=["session_id"], keep="first").reset_index(drop=True)

    if len(df) < 10:
        raise ValueError(f"Only {len(df)} usable sessions; need at least 10 for a holdout test.")

    train, test = train_test_split(
        df, test_size=TEST_SIZE, random_state=RANDOM_STATE
    )

    # All estimates are calculated from TRAIN only to avoid test-label leakage.
    category_stats = (
        train.groupby(["category_id", "detected_category"])["estimated_hours"]
        .agg(
            train_sample_count="count",
            train_median_hours="median",
            train_p75_hours=lambda s: s.quantile(0.75),
        )
        .reset_index()
    )
    global_median = float(train["estimated_hours"].median())
    global_p75 = float(train["estimated_hours"].quantile(0.75))

    predictions = test.merge(
        category_stats, on=["category_id", "detected_category"], how="left"
    )
    predictions["used_global_fallback"] = predictions["train_median_hours"].isna()
    predictions["predicted_median_hours"] = predictions["train_median_hours"].fillna(global_median)
    predictions["predicted_p75_hours"] = predictions["train_p75_hours"].fillna(global_p75)
    predictions["absolute_error_median"] = (
        predictions["estimated_hours"] - predictions["predicted_median_hours"]
    ).abs()
    predictions["absolute_error_p75"] = (
        predictions["estimated_hours"] - predictions["predicted_p75_hours"]
    ).abs()
    predictions["p75_covers_actual_quote"] = (
        predictions["estimated_hours"] <= predictions["predicted_p75_hours"]
    )

    def safe_mean(series):
        return float(series.mean()) if len(series) else None

    summary = pd.DataFrame([{
        "dataset_sessions": int(len(df)),
        "train_sessions": int(len(train)),
        "test_sessions": int(len(test)),
        "category_groups_in_train": int(train[["category_id", "detected_category"]].drop_duplicates().shape[0]),
        "global_train_median_hours": global_median,
        "global_train_p75_hours": global_p75,
        "median_baseline_mae_hours": safe_mean(predictions["absolute_error_median"]),
        "p75_baseline_mae_hours": safe_mean(predictions["absolute_error_p75"]),
        "p75_coverage_percent": float(predictions["p75_covers_actual_quote"].mean() * 100),
        "test_rows_using_global_fallback": int(predictions["used_global_fallback"].sum()),
        "test_rows": int(len(predictions)),
        "target_definition": "historical_estimated_hours (quoted hours), not actual hands-on duration",
        "split_method": f"random holdout; test_size={TEST_SIZE}; random_state={RANDOM_STATE}",
    }])

    by_category = (
        predictions.groupby(["category_id", "detected_category"], dropna=False)
        .agg(
            test_sample_count=("session_id", "nunique"),
            train_sample_count=("train_sample_count", "first"),
            median_baseline_mae_hours=("absolute_error_median", "mean"),
            p75_baseline_mae_hours=("absolute_error_p75", "mean"),
            p75_coverage_percent=("p75_covers_actual_quote", lambda s: s.mean() * 100),
            test_min_hours=("estimated_hours", "min"),
            test_median_hours=("estimated_hours", "median"),
            test_max_hours=("estimated_hours", "max"),
            used_global_fallback=("used_global_fallback", "max"),
        )
        .reset_index()
    )
    by_category["metric_warning"] = by_category["train_sample_count"].apply(
        lambda n: "very_small_training_group" if pd.isna(n) or n < MIN_TRAIN_SAMPLES_FOR_CATEGORY_METRIC else ""
    )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(SUMMARY_FILE, index=False)
    by_category.to_csv(CATEGORY_FILE, index=False)
    predictions.to_csv(PREDICTIONS_FILE, index=False)

    print("\n=== AUTOMATIC DURATION HOLDOUT VALIDATION ===")
    print(summary.to_string(index=False))
    print("\n=== METRICS BY CATEGORY ===")
    print(by_category.to_string(index=False))
    print("\nGenerated reports:")
    print(SUMMARY_FILE)
    print(CATEGORY_FILE)
    print(PREDICTIONS_FILE)
    print("\nNote: this evaluates historical quoted hours, not actual job completion time.")


if __name__ == "__main__":
    main()
