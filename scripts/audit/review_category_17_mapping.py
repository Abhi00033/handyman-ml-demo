
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

INPUT = ROOT / "datasets" / "reports" / "category_17_text_review.csv"
OUTPUT = ROOT / "datasets" / "reports" / "category_17_mapping_review.csv"


def suggest_group(text):
    text = str(text).lower()

    if any(word in text for word in [
        "tv", "television", "modem", "mount", "remount",
        "reinstall", "bracket"
    ]):
        return "Mounting - review"

    if any(word in text for word in [
        "drywall", "patch", "plaster", "sanded",
        "sanding", "holes", "paint", "painted",
        "wall finished", "primed"
    ]):
        return "Wall Repair / Painting - review"

    if any(word in text for word in [
        "powerwash", "power wash", "balcony"
    ]):
        return "Pressure Washing - review"

    if any(word in text for word in [
        "table", "furniture", "laminate", "border",
        "trim", "edge banding", "screen"
    ]):
        return "Furniture / Carpentry - review"

    if any(word in text for word in [
        "mirror"
    ]):
        return "Mirror Installation / Replacement - review"

    return "Unclassified - manual review"


def main():
    if not INPUT.exists():
        raise FileNotFoundError(
            f"Input report not found: {INPUT}"
        )

    df = pd.read_csv(INPUT)

    df["suggested_group"] = df["customer_messages"].apply(
        suggest_group
    )

    # Preserve the original label and category ID.
    df["review_decision"] = ""
    df["verified_category_id"] = ""
    df["review_notes"] = ""

    df.to_csv(OUTPUT, index=False, encoding="utf-8-sig")

    print("\nCATEGORY 17 MAPPING REVIEW")
    print(f"Rows: {len(df)}")
    print(f"Output: {OUTPUT}")

    print("\nSuggested groups:")
    print(df["suggested_group"].value_counts().to_string())

    print("\nReview preview:")
    columns = [
        "id",
        "status",
        "detected_category",
        "category_id",
        "suggested_group",
        "customer_messages",
        "review_decision",
        "verified_category_id",
    ]
    print(
        df[columns].to_string(
            index=False,
            max_colwidth=100
        )
    )


if __name__ == "__main__":
    main()
