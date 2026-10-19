"""
Five-fold grouped cross-validation for the handyman quoted-hours baseline.

Compares:
  1) category median
  2) category P75
  3) TF-IDF text + category Ridge regression

Groups identical normalized job text into the same fold to reduce exact-text leakage.
Target is historical estimated_hours (quoted hours), not actual hands-on duration.

Run from project root:
  python -m scripts.audit.validate_duration_models_cv

Reads:
  datasets/prepared/automatically_clean_duration_dataset.csv

Writes:
  datasets/reports/duration_cv_summary.csv
  datasets/reports/duration_cv_by_category.csv
  datasets/reports/duration_cv_predictions.csv
"""
from pathlib import Path
import re

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

ROOT = Path(__file__).resolve().parents[2]
DATA_FILE = ROOT / "datasets" / "prepared" / "automatically_clean_duration_dataset.csv"
REPORT_DIR = ROOT / "datasets" / "reports"
SUMMARY_FILE = REPORT_DIR / "duration_cv_summary.csv"
CATEGORY_FILE = REPORT_DIR / "duration_cv_by_category.csv"
PREDICTIONS_FILE = REPORT_DIR / "duration_cv_predictions.csv"
N_SPLITS = 5


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


def build_text_model():
    preprocessor = ColumnTransformer(
        transformers=[
            ("text", TfidfVectorizer(
                ngram_range=(1, 2), min_df=2, max_features=5000, sublinear_tf=True
            ), "job_text"),
            ("category", OneHotEncoder(handle_unknown="ignore"), ["category_key"]),
        ],
        remainder="drop",
    )
    return Pipeline([
        ("features", preprocessor),
        ("regressor", Ridge(alpha=10.0)),
    ])


def main():
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Missing {DATA_FILE}. Run rebuild_duration_pipeline first.")

    df = pd.read_csv(DATA_FILE)
    required = {"session_id", "category_id", "detected_category", "estimated_hours"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    df["estimated_hours"] = pd.to_numeric(df["estimated_hours"], errors="coerce")
    df["category_id"] = pd.to_numeric(df["category_id"], errors="coerce")
    df = df.dropna(subset=["session_id", "category_id", "detected_category", "estimated_hours"])
    df = df[(df["estimated_hours"] > 0) & (df["estimated_hours"] <= 100)]
    df = df.drop_duplicates(subset=["session_id"], keep="first").reset_index(drop=True)

    customer_text = first_available_text(
        df, ["all_customer_messages", "customer_followup_answers", "initial_customer_message"]
    )
    scope_text = first_available_text(df, ["final_quote_scope", "final_quote_notes", "task_title"])
    df["job_text"] = (
        customer_text.fillna("").astype(str) + " " + scope_text.fillna("").astype(str)
    ).map(clean_text)
    df["job_text"] = df["job_text"].where(df["job_text"].str.len() > 0, "unknown job")
    df["category_key"] = (
        df["category_id"].astype(str) + "::" + df["detected_category"].astype(str)
    )

    unique_groups = int(df["job_text"].nunique())
    if len(df) < N_SPLITS or unique_groups < N_SPLITS:
        raise ValueError(
            f"Need at least {N_SPLITS} records and distinct normalized text groups; "
            f"found {len(df)} records and {unique_groups} groups."
        )

    splitter = GroupKFold(n_splits=N_SPLITS)
    fold_frames = []

    for fold, (train_idx, test_idx) in enumerate(
        splitter.split(df, df["estimated_hours"], groups=df["job_text"]), start=1
    ):
        train = df.iloc[train_idx].copy()
        test = df.iloc[test_idx].copy()

        category_stats = train.groupby(
            ["category_id", "detected_category"]
        )["estimated_hours"].agg(
            category_median="median",
            category_p75=lambda s: s.quantile(0.75),
            category_train_count="count",
        ).reset_index()

        global_median = float(train["estimated_hours"].median())
        global_p75 = float(train["estimated_hours"].quantile(0.75))

        fold_pred = test[[
            "session_id", "category_id", "detected_category", "estimated_hours", "job_text"
        ]].copy()
        fold_pred["fold"] = fold
        fold_pred = fold_pred.merge(
            category_stats, on=["category_id", "detected_category"], how="left"
        )
        fold_pred["category_median_prediction"] = fold_pred["category_median"].fillna(global_median)
        fold_pred["category_p75_prediction"] = fold_pred["category_p75"].fillna(global_p75)

        model = build_text_model()
        model.fit(train[["job_text", "category_key"]], train["estimated_hours"])
        fold_pred["text_category_prediction"] = np.maximum(
            model.predict(test[["job_text", "category_key"]]), 0.25
        )
        fold_frames.append(fold_pred)

    pred = pd.concat(fold_frames, ignore_index=True)
    model_columns = {
        "category_median": "category_median_prediction",
        "category_p75": "category_p75_prediction",
        "text_plus_category_ridge": "text_category_prediction",
    }

    summary_rows = []
    for model_name, pred_col in model_columns.items():
        errors = (pred["estimated_hours"] - pred[pred_col]).abs()
        summary_rows.append({
            "model": model_name,
            "records": int(pred["session_id"].nunique()),
            "folds": N_SPLITS,
            "mae_hours": float(errors.mean()),
            "median_absolute_error_hours": float(errors.median()),
            "max_absolute_error_hours": float(errors.max()),
            "target_definition": "historical estimated_hours (quoted hours), not actual hands-on duration",
            "split_method": f"{N_SPLITS}-fold GroupKFold by normalized job text",
        })
    summary = pd.DataFrame(summary_rows)

    category_rows = []
    for (category_id, category_name), group in pred.groupby(
        ["category_id", "detected_category"], dropna=False
    ):
        row = {
            "category_id": category_id,
            "detected_category": category_name,
            "records_across_test_folds": int(group["session_id"].nunique()),
        }
        for model_name, pred_col in model_columns.items():
            row[f"{model_name}_mae_hours"] = float(
                (group["estimated_hours"] - group[pred_col]).abs().mean()
            )
        category_rows.append(row)
    by_category = pd.DataFrame(category_rows)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(SUMMARY_FILE, index=False)
    by_category.to_csv(CATEGORY_FILE, index=False)
    pred.to_csv(PREDICTIONS_FILE, index=False)

    print("\n=== 5-FOLD GROUPED DURATION MODEL VALIDATION ===")
    print(summary.to_string(index=False))
    print("\n=== BY-CATEGORY METRICS ACROSS TEST FOLDS ===")
    print(by_category.to_string(index=False))
    print("\nGenerated reports:")
    print(SUMMARY_FILE)
    print(CATEGORY_FILE)
    print(PREDICTIONS_FILE)
    print("\nCaution: validation target is historical quoted hours, not actual completion duration.")


if __name__ == "__main__":
    main()
