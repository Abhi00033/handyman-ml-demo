
import csv
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))

from db import get_connection


SESSION_IDS = (88, 158, 168, 169)

OUTPUT_DIR = BASE_DIR / "datasets" / "reports"
OUTPUT_FILE = OUTPUT_DIR / "ambiguous_session_context.csv"


def parse_messages(raw):
    """Decode the stored conversation without assuming its JSON structure."""
    if not raw:
        return []

    if isinstance(raw, (list, dict)):
        return raw

    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    status,
                    detected_category,
                    task_title,
                    openai_messages
                FROM quote_sessions
                WHERE id IN (%s, %s, %s, %s)
                ORDER BY id
                """,
                SESSION_IDS,
            )
            sessions = cursor.fetchall()
    finally:
        connection.close()

    print("Sessions found:", len(sessions))

    output_rows = []

    for session in sessions:
        session_id = session["id"]
        raw_messages = session.get("openai_messages")
        messages = parse_messages(raw_messages)

        print("\n" + "=" * 70)
        print(
            f"Session {session_id} | "
            f"Status: {session.get('status')} | "
            f"Category: {session.get('detected_category')} | "
            f"Title: {session.get('task_title')}"
        )

        if isinstance(messages, dict):
            messages = messages.get("messages", [messages])

        if not isinstance(messages, list):
            print("Stored conversation is not a JSON message list.")
            print("Stored value preview:", str(messages)[:500])

            output_rows.append({
                "session_id": session_id,
                "message_index": "",
                "role": "",
                "content": str(messages),
                "parse_status": "not_a_message_list",
            })
            continue

        for index, message in enumerate(messages, start=1):
            if isinstance(message, dict):
                role = (
                    message.get("role")
                    or message.get("sender")
                    or message.get("type")
                    or ""
                )

                content = (
                    message.get("content")
                    or message.get("message")
                    or message.get("text")
                    or ""
                )

                if isinstance(content, (dict, list)):
                    content = json.dumps(
                        content,
                        ensure_ascii=False,
                    )

                parse_status = "parsed"
            else:
                role = ""
                content = str(message)
                parse_status = "unrecognized_message_format"

            content = str(content)

            print(f"\n[{index}] {role}: {content[:1000]}")

            output_rows.append({
                "session_id": session_id,
                "message_index": index,
                "role": role,
                "content": content,
                "parse_status": parse_status,
            })

    with OUTPUT_FILE.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "session_id",
                "message_index",
                "role",
                "content",
                "parse_status",
            ],
        )
        writer.writeheader()
        writer.writerows(output_rows)

    print("\nExport saved to:", OUTPUT_FILE)
    print("Database access was read-only; no records were modified.")


if __name__ == "__main__":
    main()
