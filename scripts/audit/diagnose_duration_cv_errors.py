"""
Diagnose large errors from the five-fold duration model validation.
Does not alter the source dataset or database.

Run from project root:
  python -m scripts.audit.diagnose_duration_cv_errors

Reads:
  datasets/reports/duration_cv_predictions.csv

Writes:
  datasets/reports/duration_cv_error_diagnostics.csv
  datasets/reports/duration_cv_error_summary.csv
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
INPUT_FILE = ROOT / "datasets" / "reports" / "duration_cv_predictions.csv"
DETAIL_FILE = ROOT / "datasets" / "reports" / "duration_cv_error_diagnostics.csv"
SUMMARY_FILE = ROOT / "datasets" / "reports" / "duration_cv_error_summary.csv"

PREDICTION_COLUMNS = {
    "category_median": "category_median_prediction",
    "category_p75": "category_p75_prediction",
    "text_plus_category_ridge": "text_category_prediction",
}


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Missing {INPUT_FILE}. Run validate_duration_models_cv first."
        )

    df = pd.read_csv(INPUT_FILE)
    required = {"session_id", "category_id", "detected_category", "estimated_hours"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    for col in ["estimated_hours", *PREDICTION_COLUMNS.values()]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    for model, prediction_col in PREDICTION_COLUMNS.items():
        if prediction_col not in df.columns:
            raise ValueError(f"Missing prediction column: {prediction_col}")
        df[f"{model}_absolute_error_hours"] = (
            df["estimated_hours"] - df[prediction_col]
        ).abs()

    df["best_baseline_prediction"] = df["category_median_prediction"]
    df["best_baseline_absolute_error_hours"] = df["category_median_absolute_error_hours"]
    df["is_large_quote_8h_plus"] = df["estimated_hours"] >= 8
    df["is_large_median_error_3h_plus"] = df["best_baseline_absolute_error_hours"] >= 3
    df["is_extreme_quote_16h_plus"] = df["estimated_hours"] >= 16

    detail_cols = [
        "session_id", "fold", "category_id", "detected_category", "estimated_hours",
        "category_median_prediction", "category_median_absolute_error_hours",
        "category_p75_prediction", "category_p75_absolute_error_hours",
        "text_category_prediction", "text_plus_category_ridge_absolute_error_hours",
        "is_large_quote_8h_plus", "is_extreme_quote_16h_plus",
        "is_large_median_error_3h_plus", "job_text",
    ]
    detail_cols = [c for c in detail_cols if c in df.columns]
    detail = df[detail_cols].sort_values(
        ["category_median_absolute_error_hours", "estimated_hours"],
        ascending=[False, False]
    )

    summary_rows = []
    for (category_id, category_name), group in df.groupby(
        ["category_id", "detected_category"], dropna=False
    ):
        errs = group["category_median_absolute_error_hours"]
        summary_rows.append({
            "category_id": category_id,
            "detected_category": category_name,
            "records": int(group["session_id"].nunique()),
            "median_baseline_mae_hours": float(errs.mean()),
            "median_baseline_median_absolute_error_hours": float(errs.median()),
            "records_with_error_at_least_1h": int((errs >= 1).sum()),
            "records_with_error_at_least_3h": int((errs >= 3).sum()),
            "quotes_8h_or_more": int((group["estimated_hours"] >= 8).sum()),
            "quotes_16h_or_more": int((group["estimated_hours"] >= 16).sum()),
            "largest_quoted_hours": float(group["estimated_hours"].max()),
        })
    summary = pd.DataFrame(summary_rows).sort_values(
        ["median_baseline_mae_hours", "records"], ascending=[False, False]
    )

    DETAIL_FILE.parent.mkdir(parents=True, exist_ok=True)
    detail.to_csv(DETAIL_FILE, index=False)
    summary.to_csv(SUMMARY_FILE, index=False)

    print("\n=== LARGE CATEGORY-MEDIAN ERRORS (TOP 20) ===")
    show_cols = [
        c for c in [
            "session_id", "detected_category", "estimated_hours",
            "category_median_prediction", "category_median_absolute_error_hours",
            "category_p75_prediction", "text_category_prediction", "job_text"
        ] if c in detail.columns
    ]
    print(detail[show_cols].head(20).to_string(index=False, max_colwidth=180))
    print("\n=== ERROR SUMMARY BY CATEGORY ===")
    print(summary.to_string(index=False))
    print("\nGenerated reports:")
    print(DETAIL_FILE)
    print(SUMMARY_FILE)
    print("\nDo not automatically delete high-hour jobs; inspect scope and label reliability first.")


if __name__ == "__main__":
    main()
