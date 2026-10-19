"""
Compare a text+category duration regressor against category-only baselines.

Target: historical estimated_hours (quoted hours), NOT actual hands-on duration.
Uses a group holdout based on normalized job text so exact duplicate/near-identical
text records are kept together where their normalized text matches.

Run from project root:
  python -m scripts.audit.compare_duration_models

Reads:
  datasets/prepared/automatically_clean_duration_dataset.csv

Writes:
  datasets/reports/duration_model_comparison_summary.csv
  datasets/reports/duration_model_comparison_by_category.csv
  datasets/reports/duration_model_comparison_predictions.csv

No database writes. Small dataset means results are exploratory, not production proof.
"""
from pathlib import Path
import re
import warnings

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.compose import TransformedTargetRegressor

ROOT = Path(__file__).resolve().parents[2]
DATA_FILE = ROOT / "datasets" / "prepared" / "automatically_clean_duration_dataset.csv"
REPORT_DIR = ROOT / "datasets" / "reports"
SUMMARY_FILE = REPORT_DIR / "duration_model_comparison_summary.csv"
CATEGORY_FILE = REPORT_DIR / "duration_model_comparison_by_category.csv"
PREDICTIONS_FILE = REPORT_DIR / "duration_model_comparison_predictions.csv"
RANDOM_STATE = 42
TEST_SIZE = 0.20


def clean_text(value):
    if pd.isna(value):
        return ""
    value = str(value).lower()
    value = re.sub(r"https?://\S+", " ", value)
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def first_available_text(df, candidates):
    out = pd.Series("", index=df.index, dtype="object")
    for col in candidates:
        if col in df.columns:
            vals = df[col].fillna("").astype(str)
            out = out.where(out.str.strip().ne(""), vals)
    return out


def main():
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Missing {DATA_FILE}. Run the duration pipeline first.")

    df = pd.read_csv(DATA_FILE)
    required = {"session_id", "category_id", "detected_category", "estimated_hours"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    df["estimated_hours"] = pd.to_numeric(df["estimated_hours"], errors="coerce")
    df["category_id"] = pd.to_numeric(df["category_id"], errors="coerce")
    df = df.dropna(subset=["session_id", "category_id", "detected_category", "estimated_hours"])
    df = df[(df["estimated_hours"] > 0) & (df["estimated_hours"] <= 100)]
    df = df.drop_duplicates(subset=["session_id"], keep="first").copy()
    if len(df) < 20:
        raise ValueError(f"Only {len(df)} usable records; at least 20 are required for this experiment.")

    customer_text = first_available_text(
        df, ["all_customer_messages", "customer_followup_answers", "initial_customer_message"]
    )
    scope_text = first_available_text(df, ["final_quote_scope", "final_quote_notes", "task_title"])
    df["job_text"] = (
        customer_text.fillna("").astype(str) + " " + scope_text.fillna("").astype(str)
    ).map(clean_text)
    df["job_text"] = df["job_text"].where(df["job_text"].str.len() > 0, "unknown job")
    # Exact normalized job text is kept within one split to reduce duplicate-text leakage.
    groups = df["job_text"]
    if groups.nunique() < 2:
        raise ValueError("Could not create at least two distinct normalized text groups.")

    splitter = GroupShuffleSplit(n_splits=1, test_size=TEST_SIZE, random_state=RANDOM_STATE)
    train_idx, test_idx = next(splitter.split(df, groups=groups))
    train = df.iloc[train_idx].copy()
    test = df.iloc[test_idx].copy()

    # Category-only baselines are calculated from train records only.
    stats = train.groupby(["category_id", "detected_category"])["estimated_hours"].agg(
        category_median="median",
        category_p75=lambda s: s.quantile(0.75),
        category_train_count="count",
    ).reset_index()
    global_median = float(train["estimated_hours"].median())
    global_p75 = float(train["estimated_hours"].quantile(0.75))

    pred = test[["session_id", "category_id", "detected_category", "estimated_hours", "job_text"]].copy()
    pred = pred.merge(stats, on=["category_id", "detected_category"], how="left")
    pred["category_median_prediction"] = pred["category_median"].fillna(global_median)
    pred["category_p75_prediction"] = pred["category_p75"].fillna(global_p75)

    # Text + category model. The model sees only training targets during fit.
    preprocessor = ColumnTransformer(
        transformers=[
            ("text", TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_features=5000, sublinear_tf=True), "job_text"),
            ("category", OneHotEncoder(handle_unknown="ignore"), ["category_key"]),
        ],
        remainder="drop",
    )
    train_model = train[["job_text", "category_id", "detected_category"]].copy()
    test_model = test[["job_text", "category_id", "detected_category"]].copy()
    train_model["category_key"] = train_model["category_id"].astype(str) + "::" + train_model["detected_category"].astype(str)
    test_model["category_key"] = test_model["category_id"].astype(str) + "::" + test_model["detected_category"].astype(str)

    model = Pipeline([
        ("features", preprocessor),
        ("regressor", Ridge(alpha=10.0)),
    ])
    model.fit(train_model, train["estimated_hours"])
    text_predictions = model.predict(test_model)
    # Quoted hours cannot be negative; don't round, preserve fractional-hour estimates.
    pred["text_category_prediction"] = np.maximum(text_predictions, 0.25)

    methods = [
        ("category_median", "category_median_prediction"),
        ("category_p75", "category_p75_prediction"),
        ("text_plus_category_ridge", "text_category_prediction"),
    ]
    summary_rows = []
    for name, col in methods:
        errors = (pred["estimated_hours"] - pred[col]).abs()
        summary_rows.append({
            "model": name,
            "train_records": int(len(train)),
            "test_records": int(len(test)),
            "train_unique_text_groups": int(train["job_text"].nunique()),
            "test_unique_text_groups": int(test["job_text"].nunique()),
            "mae_hours": float(errors.mean()),
            "median_absolute_error_hours": float(errors.median()),
            "max_absolute_error_hours": float(errors.max()),
            "target_definition": "historical estimated_hours (quoted hours), not actual hands-on duration",
            "split_method": f"group holdout by normalized job text; test_size={TEST_SIZE}; random_state={RANDOM_STATE}",
        })
    summary = pd.DataFrame(summary_rows)

    category_rows = []
    for (category_id, category_name), group in pred.groupby(["category_id", "detected_category"], dropna=False):
        row = {
            "category_id": category_id,
            "detected_category": category_name,
            "test_sample_count": int(group["session_id"].nunique()),
        }
        for name, col in methods:
            row[f"{name}_mae_hours"] = float((group["estimated_hours"] - group[col]).abs().mean())
        category_rows.append(row)
    by_category = pd.DataFrame(category_rows)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(SUMMARY_FILE, index=False)
    by_category.to_csv(CATEGORY_FILE, index=False)
    pred.to_csv(PREDICTIONS_FILE, index=False)

    print("\n=== DURATION MODEL COMPARISON (GROUP HOLDOUT) ===")
    print(summary.to_string(index=False))
    print("\n=== BY-CATEGORY TEST METRICS ===")
    print(by_category.to_string(index=False))
    print("\nReports generated:")
    print(SUMMARY_FILE)
    print(CATEGORY_FILE)
    print(PREDICTIONS_FILE)
    print("\nImportant: exploratory validation of quoted hours only. It is not actual-duration validation.")


if __name__ == "__main__":
    main()
