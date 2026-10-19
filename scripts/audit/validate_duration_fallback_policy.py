"""
Validate a conservative duration fallback policy using grouped cross-validation.
Policy:
- >=10 training examples in category: category median
- 5-9 examples: category median with limited-support warning
- <5 examples: global training median with insufficient-support warning
- Large/complex scope keywords produce a review warning, not an automatic duration multiplier.
No database writes, no app.py changes, no rows removed because of high hours.
Run from project root:
    python -m scripts.audit.validate_duration_fallback_policy
"""
from pathlib import Path
import re
import pandas as pd
from sklearn.model_selection import GroupKFold

ROOT = Path.cwd()
INPUTS = [
    ROOT / "datasets" / "prepared" / "automatically_clean_duration_dataset.csv",
    ROOT / "datasets" / "prepared" / "automatically_clean_duration_baseline.csv",
]
OUT = ROOT / "datasets" / "reports"

def locate_input():
    for p in INPUTS:
        if p.exists():
            return p
    raise FileNotFoundError("Clean duration dataset not found in datasets/prepared.")

def get_col(df, names, required=True):
    lookup = {str(c).strip().lower(): c for c in df.columns}
    for n in names:
        if n.lower() in lookup:
            return lookup[n.lower()]
    if required:
        raise ValueError(f"Missing column from {names}; available: {list(df.columns)}")
    return None

def normalize(s):
    s = str(s or "").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s)).strip()

def scope_warning(text):
    t = normalize(text)
    patterns = [
        r"\b(200 amp|100 amp|150 amp|electrical panel|breaker panel|service panel)\b",
        r"\b(deck|balcony)\b.*\b(board|sq ft|square feet|pressure wash|powerwash|seal)\b",
        r"\b(multi visit|multiple visits|second visit|return visit|after it cures|cure time)\b",
        r"\b(whole house|entire house|multiple rooms|all bedroom walls|entire wall)\b",
        r"\b(structural|joists|framing|underlying structure)\b",
        r"\b(water heater|hot water tank)\b",
    ]
    return any(re.search(p, t) for p in patterns)

def main():
    path = locate_input()
    df = pd.read_csv(path)
    cat = get_col(df, ["category_id"])
    name = get_col(df, ["detected_category", "category_name", "category"], required=False)
    hours = get_col(df, ["estimated_hours", "hours"])
    text = get_col(df, ["job_text", "final_scope", "scope_text", "customer_messages"])
    sid = get_col(df, ["session_id", "quote_session_id"], required=False)

    df[hours] = pd.to_numeric(df[hours], errors="coerce")
    df = df[df[hours].notna() & (df[hours] > 0) & (df[hours] <= 100)].copy()
    df[cat] = df[cat].fillna("missing").astype(str)
    df["_group_text"] = df[text].map(normalize)
    df = df[df["_group_text"].str.len() > 0].reset_index(drop=True)
    folds = min(5, df["_group_text"].nunique())
    if folds < 2:
        raise ValueError("Not enough unique descriptions for grouped cross-validation.")

    predictions = []
    cv = GroupKFold(n_splits=folds)
    for fold, (tr_idx, te_idx) in enumerate(cv.split(df, df[hours], groups=df["_group_text"]), 1):
        train, test = df.iloc[tr_idx], df.iloc[te_idx]
        global_median = float(train[hours].median())
        cat_groups = train.groupby(cat)[hours]
        cat_medians = cat_groups.median().to_dict()
        cat_counts = cat_groups.size().to_dict()
        for idx in te_idx:
            r = df.iloc[idx]
            c = str(r[cat])
            n = int(cat_counts.get(c, 0))
            baseline = float(cat_medians[c]) if c in cat_medians else global_median
            if n >= 10:
                pred, tier, fallback = baseline, "category_supported", False
            elif n >= 5:
                pred, tier, fallback = baseline, "limited_support_category_median", False
            else:
                pred, tier, fallback = global_median, "global_median_fallback", True
            y = float(r[hours])
            txt = str(r[text])
            predictions.append({
                "fold": fold,
                "session_id": r[sid] if sid else "",
                "category_id": c,
                "category": r[name] if name else c,
                "actual_quoted_hours": y,
                "training_category_count": n,
                "global_training_median": global_median,
                "category_median_prediction": baseline,
                "fallback_policy_prediction": pred,
                "support_tier": tier,
                "used_global_fallback": fallback,
                "large_or_complex_scope_warning": scope_warning(txt),
                "category_median_absolute_error": abs(y - baseline),
                "fallback_policy_absolute_error": abs(y - pred),
                "job_text": txt[:1000],
            })

    p = pd.DataFrame(predictions)
    OUT.mkdir(parents=True, exist_ok=True)
    pred_path = OUT / "duration_fallback_policy_cv_predictions.csv"
    summary_path = OUT / "duration_fallback_policy_cv_summary.csv"
    p.to_csv(pred_path, index=False)

    summary_rows = []
    for model, col in [
        ("category_median_reference", "category_median_absolute_error"),
        ("support_aware_fallback_policy", "fallback_policy_absolute_error"),
    ]:
        e = p[col]
        summary_rows.append({
            "model": model, "records": len(p), "folds": p["fold"].nunique(),
            "mae_hours": round(float(e.mean()), 4),
            "median_absolute_error_hours": round(float(e.median()), 4),
            "p90_absolute_error_hours": round(float(e.quantile(.90)), 4),
            "errors_at_least_1h": int((e >= 1).sum()),
            "errors_at_least_3h": int((e >= 3).sum()),
        })
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(summary_path, index=False)

    print(f"Input: {path}")
    print(f"Records: {len(p)} | folds: {p['fold'].nunique()}")
    print("\n=== POLICY VS CATEGORY-MEDIAN REFERENCE ===")
    print(summary.to_string(index=False))
    print("\n=== POLICY RESULTS BY CATEGORY ===")
    by_cat = p.groupby(["category_id", "category"], dropna=False).agg(
        records=("actual_quoted_hours", "size"),
        fallback_records=("used_global_fallback", "sum"),
        warning_records=("large_or_complex_scope_warning", "sum"),
        median_absolute_error=("fallback_policy_absolute_error", "median"),
        mean_absolute_error=("fallback_policy_absolute_error", "mean"),
        support_tiers=("support_tier", lambda x: ", ".join(sorted(set(x)))),
    ).reset_index()
    print(by_cat.round(3).to_string(index=False))
    print("\nGenerated reports:")
    print(pred_path.resolve())
    print(summary_path.resolve())
    print("\nThe scope warning is a review signal only; it does not change predicted hours.")
    print("This validates a fallback policy, not calibrated probability confidence.")

if __name__ == "__main__":
    main()
