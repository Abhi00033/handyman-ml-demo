"""
Experimental scope-aware duration validation.
Reads the existing automatically cleaned duration dataset and compares:
1) category median
2) category + rule-based job subtype median (fallback to category median)
Uses GroupKFold grouped by normalized job text to reduce exact-text leakage.
This is a diagnostic experiment only; it does not modify the database or app.
"""
from pathlib import Path
import re
import sys
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold

ROOT = Path.cwd()
DATA_PATHS = [
    ROOT / "datasets" / "prepared" / "automatically_clean_duration_dataset.csv",
    ROOT / "datasets" / "prepared" / "automatically_clean_duration_baseline.csv",
]
OUT_DIR = ROOT / "datasets" / "reports"

def first_existing(paths):
    for path in paths:
        if path.exists():
            return path
    raise FileNotFoundError(
        "Could not find automatically_clean_duration_dataset.csv or "
        "automatically_clean_duration_baseline.csv under datasets/prepared."
    )

def normalize_text(value):
    value = str(value or "").lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def classify_scope(text):
    t = normalize_text(text)
    rules = [
        ("electrical_panel_upgrade", r"\b(panel|breaker box|service panel)\b.*\b(upgrad|replac|install|200 amp|100 amp|150 amp)\b|\b(upgrad|replac|install)\b.*\b(panel|breaker box|service panel)\b"),
        ("water_heater_replace_install", r"\b(water heater|hot water tank)\b"),
        ("deck_large_surface", r"\b(deck|balcony)\b.*\b(board|sq ft|square feet|powerwash|pressure wash|sealant|seal)\b|\b(board|powerwash|pressure wash)\b.*\b(deck|balcony)\b"),
        ("painting_large_or_multi_surface", r"\b(paint|painting|repaint)\b.*\b(walls|bedroom|exterior|entire wall|two coats|two coat|primer)\b"),
        ("grout_regrout", r"\b(grout|regrout|re grouting|regrouting)\b"),
        ("drywall_patch_repair", r"\b(drywall|joint compound|wall patch|patch.*wall|crack.*wall)\b"),
        ("fixture_or_faucet_plumbing", r"\b(faucet|tap|sink|toilet|shower head|leak|pipe|drain)\b"),
        ("door_hardware_or_door_install", r"\b(door knob|door handle|door handle|hinge|door slab|door installation)\b"),
        ("tv_or_item_mounting", r"\b(tv|television|mirror|shelf|mount|mounting)\b"),
        ("assembly", r"\b(assemble|assembly|put together|flat pack)\b"),
        ("lighting_electrical", r"\b(light fixture|outlet|switch|wiring|electrical fixture)\b"),
        ("general_cleaning_or_washing", r"\b(clean|cleaning|powerwash|pressure wash|wash)\b"),
        ("carpentry_trim_or_woodwork", r"\b(trim|baseboard|molding|wood|cabinet|tabletop|shelf|wooden)\b"),
    ]
    for label, pattern in rules:
        if re.search(pattern, t):
            return label
    return "other_or_unclear"

def find_col(df, choices, required=True):
    lookup = {c.lower().strip(): c for c in df.columns}
    for candidate in choices:
        if candidate.lower() in lookup:
            return lookup[candidate.lower()]
    if required:
        raise ValueError(f"Missing required column. Tried {choices}. Found: {list(df.columns)}")
    return None

def main():
    data_path = first_existing(DATA_PATHS)
    df = pd.read_csv(data_path)
    cat_col = find_col(df, ["category_id"])
    name_col = find_col(df, ["detected_category", "category_name"], required=False)
    hours_col = find_col(df, ["estimated_hours", "hours"])
    text_col = find_col(df, ["job_text", "final_scope", "scope_text", "customer_messages"])
    id_col = find_col(df, ["session_id", "quote_session_id"], required=False)

    df[hours_col] = pd.to_numeric(df[hours_col], errors="coerce")
    df = df[df[hours_col].notna() & (df[hours_col] > 0) & (df[hours_col] <= 100)].copy()
    df[cat_col] = df[cat_col].astype(str)
    df["normalized_job_text"] = df[text_col].map(normalize_text)
    df["scope_type"] = df[text_col].map(classify_scope)
    df = df[df["normalized_job_text"].str.len() > 0].reset_index(drop=True)

    n_splits = min(5, df["normalized_job_text"].nunique())
    if n_splits < 2:
        raise ValueError("Not enough unique job descriptions for grouped cross-validation.")
    splitter = GroupKFold(n_splits=n_splits)
    rows = []

    for fold, (train_idx, test_idx) in enumerate(
        splitter.split(df, df[hours_col], groups=df["normalized_job_text"]), start=1
    ):
        train = df.iloc[train_idx]
        test = df.iloc[test_idx]
        category_median = train.groupby(cat_col)[hours_col].median().to_dict()
        category_scope_median = train.groupby([cat_col, "scope_type"])[hours_col].median().to_dict()

        for idx in test_idx:
            row = df.iloc[idx]
            cat = str(row[cat_col])
            scope = row["scope_type"]
            cat_pred = float(category_median.get(cat, train[hours_col].median()))
            scope_pred = float(category_scope_median.get((cat, scope), cat_pred))
            rows.append({
                "fold": fold,
                "session_id": row[id_col] if id_col else "",
                "category_id": cat,
                "detected_category": row[name_col] if name_col else "",
                "estimated_hours": float(row[hours_col]),
                "scope_type": scope,
                "category_median_prediction": cat_pred,
                "scope_aware_prediction": scope_pred,
                "scope_baseline_used": "category_and_scope" if (cat, scope) in category_scope_median else "category_fallback",
                "absolute_error_category_median": abs(float(row[hours_col]) - cat_pred),
                "absolute_error_scope_aware": abs(float(row[hours_col]) - scope_pred),
                "job_text": str(row[text_col])[:1000],
            })

    pred = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pred_path = OUT_DIR / "scope_aware_duration_cv_predictions.csv"
    summary_path = OUT_DIR / "scope_aware_duration_cv_summary.csv"
    pred.to_csv(pred_path, index=False)

    summary = []
    for model, col in [
        ("category_median", "absolute_error_category_median"),
        ("category_plus_scope_median", "absolute_error_scope_aware"),
    ]:
        errs = pred[col]
        summary.append({
            "model": model,
            "records": int(len(errs)),
            "folds": int(pred["fold"].nunique()),
            "mae_hours": round(float(errs.mean()), 4),
            "median_absolute_error_hours": round(float(errs.median()), 4),
            "p90_absolute_error_hours": round(float(errs.quantile(0.90)), 4),
            "errors_at_least_1h": int((errs >= 1).sum()),
            "errors_at_least_3h": int((errs >= 3).sum()),
        })
    pd.DataFrame(summary).to_csv(summary_path, index=False)

    print(f"Input: {data_path}")
    print(f"Usable records: {len(df)} | unique normalized descriptions: {df['normalized_job_text'].nunique()} | folds: {n_splits}")
    print("\n=== OVERALL CROSS-VALIDATION COMPARISON ===")
    print(pd.DataFrame(summary).to_string(index=False))
    print("\n=== SCOPE TYPES ===")
    print(df["scope_type"].value_counts().to_string())
    print("\n=== SCOPE-AWARE RESULTS BY CATEGORY ===")
    by_cat = pred.groupby(["category_id", "detected_category"], dropna=False).agg(
        records=("estimated_hours", "size"),
        category_median_mae=("absolute_error_category_median", "mean"),
        scope_aware_mae=("absolute_error_scope_aware", "mean"),
        scope_aware_median_abs_error=("absolute_error_scope_aware", "median"),
        scope_groups=("scope_type", "nunique"),
        category_scope_fallbacks=("scope_baseline_used", lambda s: int((s == "category_fallback").sum())),
    ).reset_index()
    print(by_cat.round(3).to_string(index=False))
    print("\nGenerated reports:")
    print(pred_path.resolve())
    print(summary_path.resolve())
    print("\nInterpretation: this is a rule-based experiment, not a production estimator. Scope subgroups with few training examples can overfit; compare the CV results with the category-only baseline before adopting it.")

if __name__ == "__main__":
    main()
