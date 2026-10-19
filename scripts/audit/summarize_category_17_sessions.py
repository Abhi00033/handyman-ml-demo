
from collections import Counter
from db import get_connection
import json

def main():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    id,
                    status,
                    detected_category,
                    task_title,
                    estimated_hours,
                    estimated_price,
                    openai_messages
                FROM quote_sessions
                WHERE deleted_at IS NULL
                  AND category_id = 17
                ORDER BY id
            """)

            rows = cursor.fetchall()

        print(f"Total sessions: {len(rows)}")

        print("\n=== COUNTS BY LABEL AND STATUS ===")
        counts = Counter(
            (row["detected_category"], row["status"])
            for row in rows
        )

        for (label, status), count in sorted(
            counts.items(),
            key=lambda item: (
                str(item[0][0]),
                str(item[0][1])
            )
        ):
            print(f"{label or '[MISSING]'} | {status}: {count}")

        print("\n=== COMPACT SESSION REVIEW ===")

        for row in rows:
            messages = row["openai_messages"]

            try:
                if isinstance(messages, str):
                    messages = json.loads(messages)

                first_user = next(
                    (
                        m.get("content", "")
                        for m in messages
                        if isinstance(m, dict)
                        and m.get("role") == "user"
                    ),
                    ""
                )
            except (TypeError, ValueError):
                first_user = ""

            print(
                f"ID={row['id']} | "
                f"label={row['detected_category']} | "
                f"status={row['status']} | "
                f"hours={row['estimated_hours']} | "
                f"price={row['estimated_price']} | "
                f"message={str(first_user)[:160]}"
            )

    finally:
        connection.close()

if __name__ == "__main__":
    main()

