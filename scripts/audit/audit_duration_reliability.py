"""
Generate an automatic reliability report for the current cleaned quote-hours dataset.
Read-only: does not modify the database or app.py.
Run from the project root:
    python -m scripts.audit.audit_duration_reliability
"""
from pathlib import Path
import pandas as pd

ROOT = Path.cwd()
INPUT_CANDIDATES = [
    ROOT / "datasets" / "prepared" / "automatically_clean_duration_dataset.csv",
    ROOT / "datasets" / "prepared" / "automatically_clean_duration_baseline.csv",
]
REPORT_DIR = ROOT / "datasets" / "reports"
MIN_HOURS, MAX_HOURS = 0, 100

def find_input():
    for path in INPUT_CANDIDATES:
        if path.exists():
            return path
    raise FileNotFoundError(
        "No cleaned duration dataset found under datasets/prepared. "
        "Run scripts.data.rebuild_duration_pipeline first."
    )

def choose_column(df, candidates, required=True):
    columns = {str(c).strip().lower(): c for c in df.columns}
    for candidate in candidates:
        if candidate.lower() in columns:
            return columns[candidate.lower()]
    if required:
        raise ValueError(
            f"Missing required column from {candidates}. "
            f"Available columns: {list(df.columns)}"
        )
    return None

def confidence_tier(n):
    if n >= 20:
        return "higher_support"
    if n >= 10:
        return "moderate_support"
    if n >= 5:
        return "limited_support"
    return "insufficient_support"

def main():
    input_path = find_input()
    df = pd.read_csv(input_path)

    category_id_col = choose_column(df, ["category_id"])
    category_name_col = choose_column(
        df, ["detected_category", "category_name", "category"], required=False
    )
    hours_col = choose_column(df, ["estimated_hours", "hours"])
    session_col = choose_column(df, ["session_id", "quote_session_id"], required=False)

    df[hours_col] = pd.to_numeric(df[hours_col], errors="coerce")
    before = len(df)
    df = df[df[hours_col].notna() & (df[hours_col] > MIN_HOURS) &
            (df[hours_col] <= MAX_HOURS)].copy()
    df[category_id_col] = df[category_id_col].fillna("missing").astype(str)
    if category_name_col:
        df[category_name_col] = df[category_name_col].fillna("Unknown").astype(str)
    else:
        category_name_col = category_id_col

    rows = []
    group_cols = [category_id_col, category_name_col]
    for keys, group in df.groupby(group_cols, dropna=False):
        values = group[hours_col].astype(float)
        n = len(values)
        q10, q25, q50, q75, q90 = values.quantile([.10, .25, .50, .75, .90])
        iqr = q75 - q25
        mad = (values - q50).abs().median()
        # Flag for diagnosis only; do not remove/cap these records.
        robust_outlier_count = int(((values < q25 - 1.5 * iqr) |
                                    (values > q75 + 1.5 * iqr)).sum()) if iqr > 0 else 0
        rows.append({
            "category_id": keys[0],
            "category": keys[1],
            "sample_count": n,
            "support_tier": confidence_tier(n),
            "median_hours": round(float(q50), 3),
            "p75_hours": round(float(q75), 3),
            "p90_hours": round(float(q90), 3),
            "p10_hours": round(float(q10), 3),
            "min_hours": round(float(values.min()), 3),
            "max_hours": round(float(values.max()), 3),
            "iqr_hours": round(float(iqr), 3),
            "median_absolute_deviation_hours": round(float(mad), 3),
            "robust_outlier_count_review_only": robust_outlier_count,
            "quotes_8h_or_more": int((values >= 8).sum()),
            "quotes_16h_or_more": int((values >= 16).sum()),
            "distinct_sessions": int(group[session_col].nunique()) if session_col else n,
            "recommended_default": (
                "category_median_with_uncertainty_warning"
                if n >= 10 else
                "category_median_low_support_warning"
                if n >= 5 else
                "fallback_to_global_median_or_manual_scope_review"
            ),
        })

    report = pd.DataFrame(rows).sort_values(
        ["sample_count", "category"], ascending=[False, True]
    )
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REPORT_DIR / "duration_reliability_by_category.csv"
    summary_path = REPORT_DIR / "duration_reliability_summary.csv"
    report.to_csv(out_path, index=False)

    vals = df[hours_col].astype(float)
    summary = pd.DataFrame([{
        "input_file": str(input_path),
        "rows_before_numeric_range_filter": before,
        "valid_duration_rows": len(df),
        "excluded_invalid_or_out_of_range_rows": before - len(df),
        "category_groups": len(report),
        "global_median_hours": round(float(vals.median()), 3) if len(vals) else None,
        "global_p75_hours": round(float(vals.quantile(.75)), 3) if len(vals) else None,
        "global_p90_hours": round(float(vals.quantile(.90)), 3) if len(vals) else None,
        "quotes_8h_or_more": int((vals >= 8).sum()),
        "quotes_16h_or_more": int((vals >= 16).sum()),
        "important_note": "Outlier counts are diagnostic only; no historical quote was deleted or capped.",
    }])
    summary.to_csv(summary_path, index=False)

    print(f"Input: {input_path}")
    print(f"Rows before filtering: {before}; valid rows: {len(df)}")
    print("\n=== GLOBAL SUMMARY ===")
    print(summary.to_string(index=False))
    print("\n=== RELIABILITY BY CATEGORY ===")
    display_cols = [
        "category_id", "category", "sample_count", "support_tier",
        "median_hours", "p75_hours", "p90_hours", "iqr_hours",
        "median_absolute_deviation_hours", "robust_outlier_count_review_only",
        "quotes_8h_or_more", "quotes_16h_or_more", "recommended_default"
    ]
    print(report[display_cols].to_string(index=False))
    print("\nReports generated:")
    print(out_path.resolve())
    print(summary_path.resolve())
    print("\nSupport tiers are simple sample-count rules, not calibrated probabilities.")
    print("Large jobs/outliers remain in the data; flags are for reliability assessment only.")

if __name__ == "__main__":
    main()
