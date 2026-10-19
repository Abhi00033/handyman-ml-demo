
import json
from db import get_connection

def main():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, status, detected_category, openai_messages
                FROM quote_sessions
                WHERE openai_messages IS NOT NULL
                  AND openai_messages != ''
                ORDER BY id DESC
                LIMIT 5
            """)

            rows = cursor.fetchall()

            for row in rows:
                print("\n" + "=" * 70)
                print(f"Session ID: {row['id']}")
                print(f"Status: {row['status']}")
                print(f"Detected category: {row['detected_category']}")

                try:
                    messages = json.loads(row["openai_messages"])

                    if isinstance(messages, list):
                        for message in messages:
                            if not isinstance(message, dict):
                                continue

                            role = message.get("role", "unknown")
                            content = message.get("content", "")

                            print(f"\n[{role}]")

                            if isinstance(content, str):
                                print(content[:1500])
                            else:
                                print(json.dumps(
                                    content, ensure_ascii=False
                                )[:1500])
                    else:
                        print(json.dumps(
                            messages, ensure_ascii=False
                        )[:3000])

                except (json.JSONDecodeError, TypeError):
                    print("Could not parse openai_messages as JSON.")

    finally:
        connection.close()

if __name__ == "__main__":
    main()
