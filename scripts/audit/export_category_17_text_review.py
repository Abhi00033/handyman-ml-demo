
from pathlib import Path
import json
import pandas as pd

from db import get_connection

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "datasets" / "reports" / "category_17_text_review.csv"


def extract_user_text(messages):
    if isinstance(messages, str):
        try:
            messages = json.loads(messages)
        except json.JSONDecodeError:
            return ""

    if not isinstance(messages, list):
        return ""

    texts = []

    for message in messages:
        if not isinstance(message, dict):
            continue

        if message.get("role") != "user":
            continue

        content = message.get("content", "")

        if isinstance(content, str):
            text = content.strip()
            if text:
                texts.append(text)

        elif isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue

                # Extract text only; never export base64 image payloads.
                if item.get("type") == "text":
                    text = item.get("text", "").strip()
                    if text:
                        texts.append(text)

    return " | ".join(texts)


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
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

        for row in rows:
            row["customer_messages"] = extract_user_text(
                row.pop("openai_messages")
            )

        df = pd.DataFrame(rows)
        df.to_csv(OUTPUT, index=False, encoding="utf-8-sig")

        print(f"Exported {len(df)} sessions.")
        print(f"Report: {OUTPUT}")
        print("\nLabel counts:")
        print(df["detected_category"].value_counts(dropna=False))
        print("\nText preview:")
        print(
            df[
                [
                    "id",
                    "status",
                    "detected_category",
                    "task_title",
                    "customer_messages",
                ]
            ].to_string(index=False, max_colwidth=180)
        )

    finally:
        connection.close()


if __name__ == "__main__":
    main()
