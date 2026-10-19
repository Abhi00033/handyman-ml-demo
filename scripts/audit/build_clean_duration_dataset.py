
from pathlib import Path
import json

import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error

ROOT = Path(__file__).resolve().parents[2]

SOURCE = ROOT / "datasets" / "prepared" / "job_level_dataset.csv"
PREPARED = ROOT / "datasets" / "prepared"
REPORTS = ROOT / "datasets" / "reports"

CLEAN_FILE = PREPARED / "clean_duration_dataset.csv"
EXCLUSION_FILE = REPORTS / "duration_dataset_exclusions.csv"
SUMMARY_FILE = REPORTS / "clean_duration_dataset_summary.csv"
VALIDATION_FILE = REPORTS / "clean_duration_validation_summary.csv"
CATEGORY_VALIDATION_FILE = (
    REPORTS / "clean_duration_validation_by_category.csv"
)
PREDICTIONS_FILE = (
    REPORTS / "clean_duration_validation_predictions.csv"
)

# These statuses are not used in this finalized-quote experiment.
EXCLUDED_STATUSES = {
    "deleted",
    "rejected",
    "draft",
    "questioning",
    "address_required",
}

# This is a sanity limit, not an eight-hour cap.
# Valid large projects such as 32-hour jobs remain eligible.
MAX_VALID_HOURS = 100

TEST_SIZE = 0.20
RANDOM_STATE = 42
MIN_TRAIN_SAMPLES = 5


def normalize_text(value):
    if pd.isna(value):
        return ""
    return " ".join(str(value).strip().lower().split())


def normalize_category_id(value):
    if pd.isna(value):
        return ""
    value = str(value).strip()
    if value.endswith(".0"):
        value = value[:-2]
    return value


def has_usable_scope(value):
    """Accept nonempty plain text or a nonempty JSON/list scope."""
    if pd.isna(value):
        return False

    text = str(value).strip()

    if not text or text.lower() in {"nan", "none", "null", "[]", "{}"}:
        return False

    try:
        parsed = json.loads(text)

        if isinstance(parsed, list):
            return any(
                str(item).strip()
                for item in parsed
                if item is not None
            )

        if isinstance(parsed, dict):
            return bool(parsed)

        if isinstance(parsed, str):
            return bool(parsed.strip())

        return parsed is not None
    except (json.JSONDecodeError, TypeError):
        # Some records may contain usable plain text rather than JSON.
        return bool(text)


def prepare_dataset():
    if not SOURCE.exists():
        raise FileNotFoundError(f"Source dataset not found: {SOURCE}")

    df = pd.read_csv(SOURCE)

    required = {
        "session_id",
        "status",
        "category_id",
        "detected_category",
        "estimated_hours",
        "final_quote_scope",
    }

    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    df["category_id_normalized"] = df["category_id"].apply(
        normalize_category_id
    )
    df["category_name_normalized"] = (
        df["detected_category"].apply(normalize_text)
    )
    df["status_normalized"] = (
        df["status"].fillna("").astype(str).str.strip().str.lower()
    )
    df["estimated_hours_numeric"] = pd.to_numeric(
        df["estimated_hours"], errors="coerce"
    )
    df["scope_is_usable"] = df["final_quote_scope"].apply(
        has_usable_scope
    )

    reasons = []

    for _, row in df.iterrows():
        row_reasons = []

        if row["status_normalized"] in EXCLUDED_STATUSES:
            row_reasons.append(
                f"excluded_status:{row['status_normalized']}"
            )

        if not row["category_id_normalized"]:
            row_reasons.append("missing_category_id")

        if not row["category_name_normalized"]:
            row_reasons.append("missing_category_name")

        hours = row["estimated_hours_numeric"]

        if pd.isna(hours):
            row_reasons.append("missing_or_invalid_estimated_hours")
        elif hours <= 0:
            row_reasons.append("estimated_hours_not_positive")
        elif hours > MAX_VALID_HOURS:
            row_reasons.append("estimated_hours_over_sanity_limit")

        if not row["scope_is_usable"]:
            row_reasons.append("missing_or_unusable_final_scope")

        reasons.append("; ".join(row_reasons))

    df["exclusion_reasons"] = reasons

    excluded = df[df["exclusion_reasons"] != ""].copy()
    eligible = df[df["exclusion_reasons"] == ""].copy()

    # Keep the original session ID and category name.
    # Group by BOTH category ID and category name in validation.
    eligible["estimated_hours"] = eligible[
        "estimated_hours_numeric"
    ].astype(float)

    # Mark large jobs for review, without excluding them.
    eligible["large_estimate_review"] = (
        eligible["estimated_hours"] > 8
    )

    # Do not train on the helper columns.
    helper_columns = [
        "category_id_normalized",
        "category_name_normalized",
        "status_normalized",
        "estimated_hours_numeric",
        "scope_is_usable",
        "exclusion_reasons",
    ]

    clean = eligible.drop(
        columns=[c for c in helper_columns if c in eligible.columns]
    ).copy()

    PREPARED.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    clean.to_csv(CLEAN_FILE, index=False)

    exclusion_columns = [
        "session_id",
        "status",
        "detected_category",
        "category_id",
        "estimated_hours",
        "final_quote_scope",
        "exclusion_reasons",
    ]

    excluded[exclusion_columns].to_csv(
        EXCLUSION_FILE, index=False
    )

    # Duplicate session IDs should never silently count as separate jobs.
    duplicate_ids = int(clean["session_id"].duplicated().sum())

    if duplicate_ids:
        raise ValueError(
            f"Duplicate session IDs in eligible dataset: {duplicate_ids}"
        )

    summary = pd.DataFrame([{
        "source_records": len(df),
        "eligible_records": len(clean),
        "excluded_records": len(excluded),
        "eligible_large_estimates_over_8_hours": int(
            clean["large_estimate_review"].sum()
        ),
        "eligible_multiple_visit_records": int(
            clean["multi_visit"].astype(str).str.lower().eq("true").sum()
        ) if "multi_visit" in clean.columns else 0,
        "unique_eligible_sessions": clean["session_id"].nunique(),
        "duplicate_eligible_session_ids": duplicate_ids,
    }])

    summary.to_csv(SUMMARY_FILE, index=False)

    print("\n=== Dataset preparation ===")
    print(summary.to_string(index=False))

    print("\n=== Exclusion reasons ===")
    if excluded.empty:
        print("No excluded records.")
    else:
        print(
            excluded["exclusion_reasons"]
            .str.split("; ")
            .explode()
            .value_counts()
            .to_string()
        )

    print("\n=== Eligible category groups ===")
    print(
        clean.groupby(
            ["category_id", "detected_category"],
            dropna=False,
        )
        .size()
        .rename("records")
        .reset_index()
        .sort_values("records", ascending=False)
        .to_string(index=False)
    )

    print(f"\nClean dataset: {CLEAN_FILE}")
    print(f"Exclusion report: {EXCLUSION_FILE}")
    print(f"Summary report: {SUMMARY_FILE}")

    return clean


def validate_dataset(clean):
    if len(clean) < 10:
        raise ValueError(
            f"Not enough eligible records for validation: {len(clean)}"
        )

    df = clean.copy()

    df["estimated_hours"] = pd.to_numeric(
        df["estimated_hours"], errors="coerce"
    )
    df["category_id_key"] = df["category_id"].apply(
        normalize_category_id
    )
    df["category_name_key"] = (
        df["detected_category"].apply(normalize_text)
    )

    # Split before computing medians or percentiles.
    train, test = train_test_split(
        df,
        test_size=TEST_SIZE,
        random_state=RANDOM_STATE,
    )

    # All baselines are calculated from training data only.
    baselines = (
        train.groupby(
            ["category_id_key", "category_name_key"],
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
        on=["category_id_key", "category_name_key"],
        how="left",
    )

    # Don't evaluate categories with too few training examples.
    results = results[
        results["train_sample_count"] >= MIN_TRAIN_SAMPLES
    ].copy()

    if results.empty:
        raise ValueError(
            "No test records have categories with at least "
            f"{MIN_TRAIN_SAMPLES} training examples."
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
        "eligible_records": len(df),
        "training_records": len(train),
        "test_records_before_minimum_sample_filter": len(test),
        "test_records_evaluated": len(results),
        "category_groups_evaluated": results[
            ["category_id_key", "category_name_key"]
        ].drop_duplicates().shape[0],
        "median_estimate_mae_hours": mean_absolute_error(
            results["estimated_hours"],
            results["median_hours"],
        ),
        "p75_estimate_mae_hours": mean_absolute_error(
            results["estimated_hours"],
            results["p75_hours"],
        ),
        "p75_coverage_percent": (
            results["within_p75"].mean() * 100
        ),
    }])

    by_category = (
        results.groupby(
            ["category_id_key", "category_name_key"],
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
            p75_coverage_percent=(
                "within_p75", lambda values: values.mean() * 100
            ),
        )
        .reset_index()
        .rename(columns={
            "category_id_key": "category_id",
            "category_name_key": "category",
        })
    )

    results.to_csv(PREDICTIONS_FILE, index=False)
    overall.to_csv(VALIDATION_FILE, index=False)
    by_category.to_csv(CATEGORY_VALIDATION_FILE, index=False)

    print("\n=== Clean dataset validation ===")
    print(overall.to_string(index=False))

    print("\n=== Validation by category ===")
    print(by_category.to_string(index=False))

    print("\nValidation reports:")
    print(VALIDATION_FILE)
    print(CATEGORY_VALIDATION_FILE)
    print(PREDICTIONS_FILE)


def main():
    clean = prepare_dataset()
    validate_dataset(clean)


if __name__ == "__main__":
    main()
