
from pathlib import Path

import pandas as pd
from db import get_connection

ROOT = Path(__file__).resolve().parents[2]

OUTPUT = (
    ROOT
    / "datasets"
    / "reports"
    / "completed_job_outcomes_audit.csv"
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
                    a.status,
                    a.category_id,
                    c.name AS category_name,

                    a.estimated_hours,
                    a.job_duration_minutes,
                    a.job_started_at,
                    a.job_completed_at,

                    a.labour_cost,
                    a.estimated_total,
                    a.bill_total_before_change,
                    a.bill_total_after_change,
                    a.bill_change_count,

                    a.material_expense_amount,
                    a.parking_amount,

                    a.payment_status,
                    a.remaining_payment_status,
                    a.invoice_status,
                    a.final_invoice_number,
                    a.final_invoice_sent_at,

                    q.estimated_hours AS quote_estimated_hours,
                    q.estimated_price AS quote_estimated_price,
                    q.estimated_total AS quote_estimated_total

                FROM appointments a

                LEFT JOIN categories c
                    ON c.id = a.category_id

                LEFT JOIN quote_sessions q
                    ON q.id = a.quote_session_id

                WHERE a.deleted_at IS NULL

                ORDER BY a.id
            """)

            rows = cursor.fetchall()

    finally:
        connection.close()

    df = pd.DataFrame(rows)

    if df.empty:
        print("No appointment records found.")
        return

    # Export the complete audit dataset, including non-completed
    # appointments for status comparison.
    df.to_csv(
        OUTPUT,
        index=False,
        encoding="utf-8-sig",
    )

    completed = df[
        df["status"].eq("completed")
    ].copy()

    print("\n" + "=" * 65)
    print("COMPLETED JOB OUTCOME AUDIT")
    print("=" * 65)

    print(f"Appointments exported: {len(df)}")
    print(f"Completed appointments: {len(completed)}")

    fields = [
        "estimated_hours",
        "job_duration_minutes",
        "job_started_at",
        "job_completed_at",
        "labour_cost",
        "estimated_total",
        "bill_total_before_change",
        "bill_total_after_change",
        "material_expense_amount",
        "parking_amount",
        "payment_status",
        "invoice_status",
        "final_invoice_number",
    ]

    print("\nCompleted-job field completeness:")
    for field in fields:
        if field not in completed.columns:
            continue

        present = completed[field].notna().sum()
        print(
            f"{field:<30} "
            f"{present:>3}/{len(completed)} populated"
        )

    print("\nCompleted jobs by category:")
    print(
        completed["category_name"]
        .value_counts(dropna=False)
        .to_string()
    )

    # Compare the recorded duration with timestamp-derived duration.
    started = pd.to_datetime(
        completed["job_started_at"],
        errors="coerce",
    )

    finished = pd.to_datetime(
        completed["job_completed_at"],
        errors="coerce",
    )

    completed["timestamp_duration_minutes"] = (
        (finished - started).dt.total_seconds() / 60
    )

    completed["duration_difference_minutes"] = (
        completed["job_duration_minutes"]
        - completed["timestamp_duration_minutes"]
    )

    print("\nDuration cross-check:")
    valid_duration = completed[
        completed["job_duration_minutes"].notna()
        & completed["timestamp_duration_minutes"].notna()
    ]

    print(
        "Jobs with recorded duration and both timestamps: "
        f"{len(valid_duration)}"
    )

    if not valid_duration.empty:
        print(
            "Mean absolute difference (minutes): "
            f"{valid_duration['duration_difference_minutes'].abs().mean():.2f}"
        )

    print("\nCompleted job sample:")
    preview_columns = [
        "appointment_id",
        "category_name",
        "estimated_hours",
        "job_duration_minutes",
        "labour_cost",
        "estimated_total",
        "bill_total_after_change",
        "payment_status",
        "invoice_status",
    ]

    print(
        completed[preview_columns]
        .head(25)
        .to_string(index=False)
    )

    print(f"\nFull report saved to:\n{OUTPUT}")


if __name__ == "__main__":
    main()
