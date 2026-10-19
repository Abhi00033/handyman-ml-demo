
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

SOURCE = ROOT / "datasets" / "prepared" / "job_level_dataset.csv"
OUTPUT = ROOT / "datasets" / "reports" / "duration_review_queue.csv"


def main():
    df = pd.read_csv(SOURCE)

    df["estimated_hours"] = pd.to_numeric(
        df["estimated_hours"], errors="coerce"
    )

    # Flag records for investigation; do not automatically exclude them.
    flags = []

    for _, row in df.iterrows():
        reasons = []

        hours = row.get("estimated_hours")
        status = str(row.get("status", "")).strip().lower()
        category = str(row.get("detected_category", "")).strip()

        multi_visit = str(row.get("multi_visit", "")).strip().lower()
        scope = str(row.get("final_quote_scope", "")).lower()
        initial = str(row.get("initial_customer_message", "")).lower()

        if pd.notna(hours) and hours >= 8:
            reasons.append("high_estimated_hours")

        if multi_visit == "true":
            reasons.append("multiple_visits")

        if status in {"draft", "questioning", "address_required"}:
            reasons.append("quote_not_finalized")

        if not category or category.lower() == "nan":
            reasons.append("missing_category")

        if not scope or scope == "nan":
            reasons.append("missing_final_scope")

        # Potential scope change: use as a review prompt, not proof of error.
        if (
            initial and initial != "nan"
            and any(term in initial for term in [
                "circuit", "leak", "repair"
            ])
            and any(term in scope for term in [
                "panel", "drywall", "replace"
            ])
        ):
            reasons.append("possible_initial_vs_final_scope_change")

        flags.append({
            "session_id": row.get("session_id"),
            "status": row.get("status"),
            "detected_category": row.get("detected_category"),
            "initial_customer_message": row.get(
                "initial_customer_message"
            ),
            "final_quote_scope": row.get("final_quote_scope"),
            "estimated_hours": hours,
            "multi_visit": row.get("multi_visit"),
            "review_reasons": "; ".join(reasons),
            "review_decision": "",
            "corrected_quote_hours": "",
            "review_notes": "",
        })

    result = pd.DataFrame(flags)

    # Include only records that need review.
    result = result[result["review_reasons"] != ""].copy()

    # Preserve existing human decisions if the report already exists.
    if OUTPUT.exists():
        previous = pd.read_csv(OUTPUT)
        keep_columns = [
            "session_id", "review_decision",
            "corrected_quote_hours", "review_notes"
        ]
        if all(c in previous.columns for c in keep_columns):
            previous = previous[keep_columns].drop_duplicates(
                "session_id", keep="last"
            )
            result = result.drop(columns=[
                "review_decision", "corrected_quote_hours", "review_notes"
            ]).merge(previous, on="session_id", how="left")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(OUTPUT, index=False)

    print(f"Records requiring review: {len(result)}")
    print(f"Saved to: {OUTPUT}")
    print("\nReview reasons:")
    print(
        result["review_reasons"]
        .str.split("; ")
        .explode()
        .value_counts()
        .to_string()
    )


if __name__ == "__main__":
    main()
