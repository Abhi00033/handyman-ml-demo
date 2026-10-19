
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
INPUT_FILE = BASE_DIR / "datasets" / "prepared" / "job_level_dataset.csv"
OUTPUT_DIR = BASE_DIR / "datasets" / "reports"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(INPUT_FILE)

    # Normalize text only for auditing; do not change the source dataset.
    df["message_normalized"] = (
        df["initial_customer_message"]
        .fillna("")
        .astype(str)
        .str.lower()
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )

    df["category_normalized"] = (
        df["detected_category"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
    )

    df["hours_numeric"] = pd.to_numeric(
        df["estimated_hours"], errors="coerce"
    )

    df["price_numeric"] = pd.to_numeric(
        df["estimated_price"], errors="coerce"
    )

    print("\nJOB DATA QUALITY AUDIT")
    print("=" * 45)
    print("Total rows:", len(df))
    print("Unique session IDs:", df["session_id"].nunique())
    print(
        "Duplicate session IDs:",
        int(df["session_id"].duplicated().sum()),
    )

    print("\nMissing values:")
    for column in [
        "initial_customer_message",
        "detected_category",
        "task_level",
        "estimated_hours",
        "estimated_price",
        "image_count",
    ]:
        print(f"  {column}: {int(df[column].isna().sum())}")

    print("\nCategory distribution:")
    print(
        df["detected_category"]
        .fillna("[MISSING]")
        .value_counts()
        .to_string()
    )

    print("\nStatus distribution:")
    print(df["status"].fillna("[MISSING]").value_counts().to_string())

    print("\nNumeric label summary:")
    print(
        df[["hours_numeric", "price_numeric"]]
        .describe()
        .to_string()
    )

    # These are review flags, not automatic proof of incorrect labels.
    suspicious = df[
        (df["hours_numeric"].notna() & (df["hours_numeric"] <= 0))
        | (df["price_numeric"].notna() & (df["price_numeric"] <= 0))
        | (
            df["estimated_price_min"].notna()
            & df["estimated_price_max"].notna()
            & (
                pd.to_numeric(
                    df["estimated_price_min"], errors="coerce"
                )
                > pd.to_numeric(
                    df["estimated_price_max"], errors="coerce"
                )
            )
        )
    ].copy()

    suspicious_file = OUTPUT_DIR / "suspicious_quote_labels.csv"
    suspicious.to_csv(suspicious_file, index=False, encoding="utf-8-sig")

    repeated_messages = (
        df[df["message_normalized"] != ""]
        .groupby("message_normalized")
        .agg(
            session_count=("session_id", "count"),
            session_ids=(
                "session_id",
                lambda values: ", ".join(map(str, values)),
            ),
            categories=(
                "detected_category",
                lambda values: ", ".join(
                    sorted(set(values.dropna().astype(str)))
                ),
            ),
        )
        .reset_index()
    )

    repeated_messages = repeated_messages[
        repeated_messages["session_count"] > 1
    ].sort_values("session_count", ascending=False)

    repeated_file = OUTPUT_DIR / "repeated_customer_messages.csv"
    repeated_messages.to_csv(
        repeated_file, index=False, encoding="utf-8-sig"
    )

    print("\nReview flags:")
    print("  Suspicious numeric/range labels:", len(suspicious))
    print("  Repeated message groups:", len(repeated_messages))

    print("\nReports created:")
    print(suspicious_file)
    print(repeated_file)

    print(
        "\nRepeated messages may represent separate legitimate jobs. "
        "Review them before excluding anything."
    )


if __name__ == "__main__":
    main()
