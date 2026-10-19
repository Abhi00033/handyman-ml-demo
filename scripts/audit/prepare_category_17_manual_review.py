
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

SOURCE = ROOT / "datasets" / "reports" / "category_17_text_review.csv"
OUTPUT = ROOT / "datasets" / "reports" / "category_17_manual_review.csv"


def main():
    if not SOURCE.exists():
        raise FileNotFoundError(f"Source file not found: {SOURCE}")

    df = pd.read_csv(SOURCE)

    if "id" not in df.columns:
        raise ValueError("Expected an 'id' column in the source file.")

    if df["id"].duplicated().any():
        raise ValueError("Duplicate session IDs found in source file.")

    # Add review fields without changing the original data.
    review_columns = {
        "reviewed_job_type": "",
        "proposed_category_id": "",
        "proposed_category_name": "",
        "review_decision": "",
        "review_notes": "",
    }

    for column, default in review_columns.items():
        if column not in df.columns:
            df[column] = default

    # Add guidance, not an automatic classification.
    df["allowed_category_options"] = (
        "1=Plumbing; 3=Home Repairs; 4=Electrical; "
        "5=Carpentry; 6=Appliance Services; 7=HVAC; "
        "17=Home Improvement; 18=Assembly; 19=Mounting; "
        "2=Home Improving (soft-deleted: do not approve "
        "for new jobs without verification)"
    )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT, index=False)

    print(f"Review rows: {len(df)}")
    print(f"Saved: {OUTPUT}")
    print("\nFill these columns manually:")
    print("reviewed_job_type")
    print("proposed_category_id")
    print("proposed_category_name")
    print("review_decision")
    print("review_notes")


if __name__ == "__main__":
    main()
