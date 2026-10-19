
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

SOURCE = ROOT / "datasets" / "reports" / "duration_review_queue.csv"
OUTPUT = ROOT / "datasets" / "reports" / "duration_review_prioritized.csv"


def priority(reasons):
    reasons = set(str(reasons).split("; "))

    if {
        "missing_category",
        "missing_final_scope",
    } & reasons:
        return "P1 - Missing essential information"

    if "possible_initial_vs_final_scope_change" in reasons:
        return "P2 - Verify final scope"

    if "high_estimated_hours" in reasons:
        return "P2 - Verify large estimate"

    if "quote_not_finalized" in reasons:
        return "P3 - Non-final quote"

    if "multiple_visits" in reasons:
        return "P4 - Preserve visit information"

    return "P5 - General review"


def main():
    if not SOURCE.exists():
        raise FileNotFoundError(f"Missing input file: {SOURCE}")

    df = pd.read_csv(SOURCE)

    df["review_priority"] = df["review_reasons"].apply(priority)

    # Put the most important records first.
    order = {
        "P1 - Missing essential information": 1,
        "P2 - Verify final scope": 2,
        "P2 - Verify large estimate": 3,
        "P3 - Non-final quote": 4,
        "P4 - Preserve visit information": 5,
        "P5 - General review": 6,
    }

    df["_order"] = df["review_priority"].map(order)
    df = df.sort_values(
        ["_order", "session_id"],
        kind="stable",
    ).drop(columns="_order")

    df.to_csv(OUTPUT, index=False)

    print(f"Total flagged sessions: {len(df)}")
    print("\nPriorities:")
    print(df["review_priority"].value_counts().to_string())
    print(f"\nSaved to: {OUTPUT}")


if __name__ == "__main__":
    main()
