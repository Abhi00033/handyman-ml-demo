
from pathlib import Path

import pandas as pd
from db import get_connection

ROOT = Path(__file__).resolve().parents[2]

OUTPUT = (
    ROOT
    / "datasets"
    / "reports"
    / "appointment_category_consistency.csv"
)


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            # Compare appointment category with its originating quote.
            cursor.execute("""
                SELECT
                    a.id AS appointment_id,
                    a.status AS appointment_status,
                    a.category_id AS appointment_category_id,
                    ac.name AS appointment_category_name,
                    a.quote_session_id,
                    q.status AS quote_status,
                    q.category_id AS quote_category_id,
                    qc.name AS quote_category_name,
                    q.detected_category AS quote_detected_category,
                    q.estimated_hours,
                    q.estimated_price,
                    q.estimated_total,
                    a.created_at AS appointment_created_at
                FROM appointments a
                LEFT JOIN categories ac
                    ON ac.id = a.category_id
                LEFT JOIN quote_sessions q
                    ON q.id = a.quote_session_id
                LEFT JOIN categories qc
                    ON qc.id = q.category_id
                ORDER BY a.id
            """)

            rows = cursor.fetchall()

    finally:
        connection.close()

    df = pd.DataFrame(rows)

    if df.empty:
        print("No appointments found.")
        return

    # Compare category IDs without changing their original values.
    appointment_category = df["appointment_category_id"]
    quote_category = df["quote_category_id"]

    both_present = (
        appointment_category.notna()
        & quote_category.notna()
    )

    df["category_consistency"] = "not_comparable"

    df.loc[
        both_present
        & (appointment_category == quote_category),
        "category_consistency",
    ] = "matching"

    df.loc[
        both_present
        & (appointment_category != quote_category),
        "category_consistency",
    ] = "mismatch"

    df.loc[
        appointment_category.isna(),
        "category_consistency",
    ] = "missing_appointment_category"

    df.loc[
        appointment_category.notna()
        & quote_category.isna(),
        "category_consistency",
    ] = "missing_quote_category"

    df.to_csv(OUTPUT, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 65)
    print("APPOINTMENT CATEGORY CONSISTENCY AUDIT")
    print("=" * 65)

    print(f"Total appointments: {len(df)}")

    print("\nAppointment statuses:")
    if "appointment_status" in df.columns:
        print(
            df["appointment_status"]
            .value_counts(dropna=False)
            .to_string()
        )

    print("\nCategory consistency:")
    print(
        df["category_consistency"]
        .value_counts(dropna=False)
        .to_string()
    )

    print("\nCategory distribution:")
    print(
        df["appointment_category_name"]
        .value_counts(dropna=False)
        .to_string()
    )

    print("\nAppointments with a quote session:")
    print(f"{df['quote_session_id'].notna().sum()}")

    print("\nSample records:")
    print(
        df[
            [
                "appointment_id",
                "appointment_status",
                "appointment_category_id",
                "appointment_category_name",
                "quote_session_id",
                "quote_category_id",
                "quote_category_name",
                "category_consistency",
            ]
        ]
        .head(25)
        .to_string(index=False)
    )

    print(f"\nReport saved to:\n{OUTPUT}")


if __name__ == "__main__":
    main()
