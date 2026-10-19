
from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from db import get_connection


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "datasets" / "prepared"
REPORT_DIR = ROOT / "datasets" / "reports"

SESSION_OUTPUT = OUTPUT_DIR / "historical_conversation_records.csv"
QUESTION_OUTPUT = OUTPUT_DIR / "historical_question_candidates.csv"
AUDIT_OUTPUT = REPORT_DIR / "historical_knowledge_audit.csv"


def parse_json(value: Any) -> tuple[Any, str]:
    """Parse JSON safely and report malformed or missing values."""
    if value is None or value == "":
        return None, "missing"

    if isinstance(value, (dict, list)):
        return value, "valid"

    try:
        return json.loads(value), "valid"
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, "invalid_json"


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def message_text(content: Any) -> str:
    """Extract readable text without assuming every message is plain text."""
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if text:
                    parts.append(str(text))
        return "\n".join(parts).strip()

    if isinstance(content, dict):
        return clean_text(content.get("text") or content.get("content"))

    return ""


def extract_image_references(content: Any) -> int:
    """Count image-like blocks; do not download or expose image URLs."""
    if isinstance(content, list):
        count = 0
        for item in content:
            if isinstance(item, dict):
                item_type = str(item.get("type", "")).lower()
                if "image" in item_type or "image" in item:
                    count += 1
        return count

    if isinstance(content, dict):
        item_type = str(content.get("type", "")).lower()
        return int("image" in item_type or "image" in content)

    return 0


def parse_messages(messages: Any) -> tuple[list[dict], int]:
    """Normalize conversation messages and count image blocks."""
    if not isinstance(messages, list):
        return [], 0

    result = []
    image_count = 0

    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            continue

        role = clean_text(message.get("role")).lower()
        content = message.get("content")
        text = message_text(content)

        image_count += extract_image_references(content)

        # Store only the relevant conversational roles.
        if role not in {"user", "assistant"}:
            continue

        result.append({
            "message_index": index,
            "role": role,
            "text": text,
        })

    return result, image_count


def extract_questions(text: str) -> list[str]:
    """Extract numbered questions and suggested-reply metadata."""
    if not text:
        return []

    questions = []

    # Leo's known historical format: Question 1/3: ...
    numbered = re.findall(
        r"Question\s*\d+\s*/\s*\d+\s*:\s*(.*?)(?=\n|$)",
        text,
        flags=re.IGNORECASE,
    )

    for question in numbered:
        question = re.sub(r"\*+", "", question).strip()
        if question and "?" in question:
            questions.append(question)

    # Fallback: standalone lines that appear to be questions.
    if not questions:
        for line in text.splitlines():
            line = re.sub(r"^\s*[-*]+\s*", "", line).strip()
            if "?" in line and len(line) <= 500:
                questions.append(line)

    return questions


def extract_suggested_replies(text: str) -> str:
    match = re.search(
        r"SUGGESTED_REPLIES\s*:\s*(.*)",
        text or "",
        flags=re.IGNORECASE,
    )
    return match.group(1).strip() if match else ""


def quote_field(quote: Any, field: str) -> Any:
    return quote.get(field) if isinstance(quote, dict) else None


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    session_rows = []
    question_rows = []
    audit_rows = []

    counters = Counter()
    conn = get_connection()

    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT
                    id,
                    status,
                    task_title,
                    detected_category,
                    category_id,
                    task_level,
                    task_level_id,
                    estimated_hours,
                    openai_messages,
                    final_quote
                FROM quote_sessions
                WHERE deleted_at IS NULL
                ORDER BY id
            """)

            records = cursor.fetchall()

        counters["sessions_read"] = len(records)

        for record in records:
            if not isinstance(record, dict):
                raise TypeError(
                    "Expected dictionary rows from db.py. "
                    "Check whether the connection uses DictCursor."
                )

            session_id = record.get("id")

            messages_json, messages_status = parse_json(
                record.get("openai_messages")
            )
            quote_json, quote_status = parse_json(
                record.get("final_quote")
            )

            messages, image_blocks = parse_messages(messages_json)

            category = clean_text(record.get("detected_category"))
            category_id = record.get("category_id")
            level_id = record.get("task_level_id")
            estimated_hours = record.get("estimated_hours")

            quote_title = clean_text(
                quote_field(quote_json, "task_title")
            )
            quote_category = clean_text(
                quote_field(quote_json, "detected_category")
            )
            quote_hours = quote_field(quote_json, "total_hours")
            quote_scope = quote_field(quote_json, "scope")
            quote_notes = quote_field(quote_json, "tasker_notes")

            if messages_status == "valid":
                counters["valid_message_json"] += 1
            else:
                counters[f"message_json_{messages_status}"] += 1

            if quote_status == "valid":
                counters["valid_quote_json"] += 1
            else:
                counters[f"quote_json_{quote_status}"] += 1

            if not category_id:
                counters["sessions_missing_category_id"] += 1

            if not level_id:
                counters["sessions_missing_task_level_id"] += 1

            if not category and not quote_category:
                counters["sessions_missing_category_name"] += 1

            user_messages = [
                item for item in messages if item["role"] == "user"
            ]
            assistant_messages = [
                item for item in messages if item["role"] == "assistant"
            ]

            session_rows.append({
                "session_id": session_id,
                "status": clean_text(record.get("status")),
                "task_title": clean_text(record.get("task_title")) or quote_title,
                "detected_category": category or quote_category,
                "category_id": category_id,
                "task_level": record.get("task_level"),
                "task_level_id": level_id,
                "estimated_hours": estimated_hours,
                "final_quote_hours": quote_hours,
                "message_json_status": messages_status,
                "quote_json_status": quote_status,
                "user_message_count": len(user_messages),
                "assistant_message_count": len(assistant_messages),
                "image_block_count": image_blocks,
                "conversation_json": json.dumps(
                    messages, ensure_ascii=False
                ),
                "final_scope": json.dumps(
                    quote_scope, ensure_ascii=False
                ) if quote_scope is not None else "",
                "tasker_notes": json.dumps(
                    quote_notes, ensure_ascii=False
                ) if quote_notes is not None else "",
                "review_status": "unverified",
            })

            # Conservative extraction: pair a question only with the
            # immediately following customer message in the stored sequence.
            # Multiple questions in one message are flagged for review.
            for index, item in enumerate(messages):
                if item["role"] != "assistant":
                    continue

                questions = extract_questions(item["text"])
                if not questions:
                    continue

                next_customer = None
                for following in messages[index + 1:]:
                    if following["role"] == "user":
                        next_customer = following
                        break
                    if following["role"] == "assistant":
                        break

                if not next_customer:
                    counters["questions_without_next_customer_message"] += len(
                        questions
                    )
                    continue

                for question in questions:
                    flags = []
                    if len(questions) > 1:
                        flags.append("multiple_questions_in_assistant_message")
                    if len(next_customer["text"]) <= 2:
                        flags.append("very_short_answer_review")
                    if next_customer["text"].strip().lower() in {
                        "yes", "no", "y", "n", "a", "b"
                    }:
                        flags.append("context_dependent_answer_review")

                    question_rows.append({
                        "session_id": session_id,
                        "category": category or quote_category,
                        "task_title": clean_text(record.get("task_title")) or quote_title,
                        "assistant_message_index": item["message_index"],
                        "question": question,
                        "suggested_replies": extract_suggested_replies(
                            item["text"]
                        ),
                        "next_customer_message_index": next_customer["message_index"],
                        "customer_answer_candidate": next_customer["text"],
                        "review_flags": ";".join(flags),
                        "verified_for_training": "no",
                    })

                    counters["question_candidates"] += 1

            audit_flags = []
            if messages_status != "valid":
                audit_flags.append(f"messages_{messages_status}")
            if quote_status not in {"valid", "missing"}:
                audit_flags.append(f"quote_{quote_status}")
            if not category_id:
                audit_flags.append("missing_category_id")
            if not level_id:
                audit_flags.append("missing_task_level_id")
            if not messages:
                audit_flags.append("no_parseable_messages")

            if audit_flags:
                audit_rows.append({
                    "session_id": session_id,
                    "status": clean_text(record.get("status")),
                    "detected_category": category,
                    "category_id": category_id,
                    "task_level_id": level_id,
                    "message_json_status": messages_status,
                    "quote_json_status": quote_status,
                    "audit_flags": ";".join(audit_flags),
                })

    finally:
        conn.close()

    write_csv(
        SESSION_OUTPUT,
        session_rows,
        [
            "session_id", "status", "task_title", "detected_category",
            "category_id", "task_level", "task_level_id", "estimated_hours",
            "final_quote_hours", "message_json_status", "quote_json_status",
            "user_message_count", "assistant_message_count", "image_block_count",
            "conversation_json", "final_scope", "tasker_notes", "review_status",
        ],
    )

    write_csv(
        QUESTION_OUTPUT,
        question_rows,
        [
            "session_id", "category", "task_title",
            "assistant_message_index", "question", "suggested_replies",
            "next_customer_message_index", "customer_answer_candidate",
            "review_flags", "verified_for_training",
        ],
    )

    write_csv(
        AUDIT_OUTPUT,
        audit_rows,
        [
            "session_id", "status", "detected_category", "category_id",
            "task_level_id", "message_json_status", "quote_json_status",
            "audit_flags",
        ],
    )

    print("\nHistorical extraction completed (read-only).")
    print(f"Sessions read: {counters['sessions_read']}")
    print(f"Question candidates: {counters['question_candidates']}")
    print(f"Audit rows requiring inspection: {len(audit_rows)}")
    print(f"Valid message JSON: {counters['valid_message_json']}")
    print(f"Valid quote JSON: {counters['valid_quote_json']}")
    print(f"Missing category IDs: {counters['sessions_missing_category_id']}")
    print(f"Missing task-level IDs: {counters['sessions_missing_task_level_id']}")
    print(f"\nSession records: {SESSION_OUTPUT}")
    print(f"Question candidates: {QUESTION_OUTPUT}")
    print(f"Audit report: {AUDIT_OUTPUT}")
    print("\nAll extracted questions remain unverified. No database rows were changed.")


if __name__ == "__main__":
    main()
