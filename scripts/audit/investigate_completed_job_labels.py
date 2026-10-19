
from pathlib import Path

import pandas as pd
from db import get_connection

ROOT = Path(__file__).resolve().parents[2]

OUTPUT = (
    ROOT
    / "datasets"
    / "reports"
    / "completed_job_label_investigation.csv"
)


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    a.id AS appointment_id,
                    a.quote_session_id,
                    a.category_id,
                    c.name AS category_name,
                    a.status,

                    a.estimated_hours,
                    a.job_duration_minutes,
                    a.job_started_at,
                    a.job_completed_at,

                    a.labour_cost,
                    a.estimated_total,
                    a.service_fee,
                    a.material_expense_amount,
                    a.parking_amount,

                    a.payment_status,
                    a.invoice_status,
                    a.final_invoice_number,

                    q.estimated_hours AS quote_estimated_hours,
                    q.estimated_price AS quote_estimated_price,
                    q.estimated_total AS quote_estimated_total,
                    q.final_quote

                FROM appointments a

                LEFT JOIN categories c
                    ON c.id = a.category_id

                LEFT JOIN quote_sessions q
                    ON q.id = a.quote_session_id

                WHERE a.deleted_at IS NULL
                  AND a.status = 'completed'

                ORDER BY a.id
            """)

            rows = cursor.fetchall()

    finally:
        connection.close()

    df = pd.DataFrame(rows)

    if df.empty:
        print("No completed appointments found.")
        return

    # Convert numeric fields to consistent pandas numeric types.
    numeric_columns = [
        "estimated_hours",
        "job_duration_minutes",
        "labour_cost",
        "estimated_total",
        "service_fee",
        "material_expense_amount",
        "parking_amount",
        "quote_estimated_hours",
        "quote_estimated_price",
        "quote_estimated_total",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    # Convert timestamps.
    for column in ["job_started_at", "job_completed_at"]:
        df[column] = pd.to_datetime(
            df[column],
            errors="coerce",
        )

    # Calculate elapsed time between recorded timestamps.
    df["timestamp_duration_minutes"] = (
        df["job_completed_at"] - df["job_started_at"]
    ).dt.total_seconds() / 60.0

    df["duration_difference_minutes"] = (
        df["job_duration_minutes"]
        - df["timestamp_duration_minutes"]
    )

    # Flag suspicious durations for manual review.
    df["duration_review_reason"] = ""

    df.loc[
        df["job_duration_minutes"].isna(),
        "duration_review_reason",
    ] = "Missing recorded duration"

    df.loc[
        df["job_duration_minutes"].eq(0),
        "duration_review_reason",
    ] = "Zero recorded duration"

    df.loc[
        df["timestamp_duration_minutes"].lt(0),
        "duration_review_reason",
    ] = "Completion timestamp precedes start"

    short_duration = (
        df["estimated_hours"].notna()
        & df["job_duration_minutes"].notna()
        & (
            df["job_duration_minutes"]
            < df["estimated_hours"] * 60.0 * 0.25
        )
    )

    df.loc[
        short_duration,
        "duration_review_reason",
    ] = "Recorded duration far below estimate"

    # Flag financial fields for review.
    df["pricing_review_reason"] = ""

    df.loc[
        df["labour_cost"].isna(),
        "pricing_review_reason",
    ] = "Missing labour cost"

    df.loc[
        df["estimated_total"].isna(),
        "pricing_review_reason",
    ] = "Missing estimated total"

    paid_without_invoice = (
        df["payment_status"]
        .astype("string")
        .str.lower()
        .eq("paid")
        & df["final_invoice_number"].isna()
        & df["invoice_status"].isna()
    )

    df.loc[
        paid_without_invoice,
        "pricing_review_reason",
    ] = "Paid status but no invoice reference/status"

    # Save all investigation fields for manual inspection.
    df.to_csv(
        OUTPUT,
        index=False,
        encoding="utf-8-sig",
    )

    print("\nCOMPLETED JOB LABEL INVESTIGATION")
    print("=" * 65)
    print(f"Completed appointments: {len(df)}")

    print("\nRecorded duration distribution:")
    print(
        df["job_duration_minutes"]
        .describe()
        .to_string()
    )

    print("\nTimestamp elapsed duration distribution:")
    print(
        df["timestamp_duration_minutes"]
        .describe()
        .to_string()
    )

    print("\nDuration review reasons:")
    print(
        df["duration_review_reason"]
        .replace("", "No rule triggered")
        .value_counts()
        .to_string()
    )

    print("\nPricing review reasons:")
    print(
        df["pricing_review_reason"]
        .replace("", "No rule triggered")
        .value_counts()
        .to_string()
    )

    print("\nKey comparison:")
    preview_columns = [
        "appointment_id",
        "category_name",
        "estimated_hours",
        "job_duration_minutes",
        "timestamp_duration_minutes",
        "labour_cost",
        "estimated_total",
        "payment_status",
        "invoice_status",
    ]

    print(
        df[preview_columns].to_string(index=False)
    )

    print(f"\nFull report saved to:\n{OUTPUT}")


if __name__ == "__main__":
    main()
