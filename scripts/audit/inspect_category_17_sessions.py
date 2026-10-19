
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
                    category_id,
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
            print(f"Sessions found: {len(rows)}")

            for row in rows:
                print("\n" + "=" * 70)
                print(
                    f"ID: {row['id']} | "
                    f"Status: {row['status']} | "
                    f"Label: {row['detected_category']} | "
                    f"Title: {row['task_title']}"
                )
                print(
                    f"Hours: {row['estimated_hours']} | "
                    f"Price: {row['estimated_price']}"
                )

                try:
                    messages = row["openai_messages"]
                    if isinstance(messages, str):
                        messages = json.loads(messages)

                    first_user_message = next(
                        (
                            message.get("content", "")
                            for message in messages
                            if message.get("role") == "user"
                        ),
                        ""
                    )
                    print(f"First customer message: {first_user_message}")

                except (TypeError, ValueError, AttributeError):
                    print("First customer message: unavailable")

    finally:
        connection.close()


if __name__ == "__main__":
    main()
