
import csv
import json
from pathlib import Path
from collections import Counter

from db import get_connection

BASE_DIR = Path(__file__).resolve().parents[2]
DATASET_DIR = BASE_DIR / "datasets"
PREPARED_DIR = DATASET_DIR / "prepared"
REPORT_DIR = DATASET_DIR / "reports"

IMAGE_MANIFEST = DATASET_DIR / "image_download_manifest.csv"
IMAGE_VALIDATION = DATASET_DIR / "image_validation_report.csv"
QUOTE_AUDIT = DATASET_DIR / "quote_label_audit.csv"

OUTPUT_FILE = PREPARED_DIR / "job_level_dataset.csv"
SUMMARY_FILE = REPORT_DIR / "job_level_dataset_summary.csv"


def parse_json(value):
    if isinstance(value, (dict, list)):
        return value

    if not isinstance(value, str) or not value.strip():
        return None

    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def content_to_text(content):
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts = [content_to_text(item) for item in content]
        return "\n".join(part for part in parts if part)

    if isinstance(content, dict):
        if content.get("type") == "image":
            return "[Image attachment]"

        for key in ("text", "content", "value"):
            if key in content:
                result = content_to_text(content[key])
                if result:
                    return result

    return ""


def read_csv(path):
    if not path.is_file():
        raise FileNotFoundError(f"Required file not found: {path}")

    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def extract_customer_messages(messages):
    """
    Extract customer messages in chronological order.
    Assistant responses are kept separate and are not used as
    customer-provided facts.
    """
    if not isinstance(messages, list):
        return [], []

    customer_messages = []
    assistant_messages = []

    for message in messages:
        if not isinstance(message, dict):
            continue

        role = str(
            message.get("role") or message.get("sender") or ""
        ).strip().lower()

        content = content_to_text(message.get("content"))

        if not content:
            continue

        if role in {"user", "customer"}:
            customer_messages.append(content)
        elif role in {"assistant", "ai"}:
            assistant_messages.append(content)

    return customer_messages, assistant_messages


def number_or_blank(value):
    try:
        if value is None or str(value).strip() == "":
            return ""

        number = float(value)

        if number < 0:
            return ""

        return number
    except (TypeError, ValueError):
        return ""


def main():
    PREPARED_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    manifest = read_csv(IMAGE_MANIFEST)
    validation = read_csv(IMAGE_VALIDATION)
    audit = read_csv(QUOTE_AUDIT)

    valid_image_ids = {
        str(row.get("image_id", "")).strip()
        for row in validation
        if row.get("validation_status") == "valid"
    }

    images_by_session = {}

    for image in manifest:
        session_id = str(image.get("session_id", "")).strip()
        image_id = str(image.get("image_id", "")).strip()

        if not session_id or not image_id:
            continue

        if image_id not in valid_image_ids:
            continue

        if image.get("disk") != "s3":
            continue

        if image.get("status") not in {
            "downloaded",
            "already_downloaded",
        }:
            continue

        local_path = (image.get("local_path") or "").strip()

        if not local_path:
            continue

        # Keep only paths that actually exist on this machine.
        if not Path(local_path).is_file():
            continue

        images_by_session.setdefault(session_id, []).append({
            "image_id": image_id,
            "path": local_path,
        })

    audit_by_session = {
        str(row.get("session_id", "")).strip(): row
        for row in audit
    }

    connection = None
    output_rows = []
    summary_rows = []
    status_counts = Counter()

    try:
        connection = get_connection()

        with connection.cursor() as cursor:
            
            cursor.execute("""
                SELECT
                    id,
                    status,
                    openai_messages,
                    final_quote,
                    estimated_hours,
                    estimated_price,
                    estimated_price_min,
                    estimated_price_max,
                    estimated_total,
                    estimated_total_min,
                    estimated_total_max,
                    service_fee,
                    hst,
                    detected_category,
                    category_id,
                    task_level,
                    task_level_id,
                    task_title
                FROM quote_sessions
                WHERE deleted_at IS NULL
                ORDER BY id
            """)


            sessions = cursor.fetchall()

        for session in sessions:
            session_id = str(session["id"])
            status = str(session.get("status") or "").strip().lower()

            messages = parse_json(session.get("openai_messages"))
            quote = parse_json(session.get("final_quote"))

            if not isinstance(quote, dict):
                quote = {}

            customer_messages, assistant_messages = (
                extract_customer_messages(messages)
            )

            initial_message = (
                customer_messages[0] if customer_messages else ""
            )

            followup_answers = customer_messages[1:]

            images = images_by_session.get(session_id, [])
            image_paths = [item["path"] for item in images]

            audit_row = audit_by_session.get(session_id, {})

            category = (
                session.get("detected_category")
                or quote.get("detected_category")
                or ""
            )

            hours = number_or_blank(
                session.get("estimated_hours")
            )

            if hours == "":
                hours = number_or_blank(
                    quote.get("total_hours")
                )

            price = number_or_blank(
                session.get("estimated_price")
            )

            review_group = audit_row.get("review_group", "")

            # This is a review flag, not proof of label accuracy.
            has_core_labels = (
                bool(str(category).strip())
                and hours != ""
                and price != ""
            )

            output_rows.append({
                "session_id": session_id,
                "status": status,
                "review_group": review_group,
                "initial_customer_message": initial_message,
                "customer_followup_answers": json.dumps(
                    followup_answers, ensure_ascii=False
                ),
                "all_customer_messages": json.dumps(
                    customer_messages, ensure_ascii=False
                ),
                "assistant_messages_for_review": json.dumps(
                    assistant_messages, ensure_ascii=False
                ),
                "image_count": len(images),
                "image_ids": json.dumps(
                    [item["image_id"] for item in images]
                ),
                "image_paths": json.dumps(
                    image_paths, ensure_ascii=False
                ),
                "detected_category": category,
                "category_id": (
                    session.get("category_id")
                    if session.get("category_id") is not None
                    else quote.get("detected_category_id", "")
                ),
                "task_level": (
                    session.get("task_level")
                    if session.get("task_level") is not None
                    else quote.get("task_level", "")
                ),
                "task_level_id": (
                    session.get("task_level_id")
                    if session.get("task_level_id") is not None
                    else quote.get("task_level_id", "")
                ),
                "task_title": session.get("task_title") or "",
                "estimated_hours": hours,
                "estimated_price": price,
                "estimated_price_min": number_or_blank(
                    session.get("estimated_price_min")
                ),
                "estimated_price_max": number_or_blank(
                    session.get("estimated_price_max")
                ),
                "estimated_total": number_or_blank(
                    session.get("estimated_total")
                ),
                "estimated_total_min": number_or_blank(
                    session.get("estimated_total_min")
                ),
                "estimated_total_max": number_or_blank(
                    session.get("estimated_total_max")
                ),
                "service_fee": number_or_blank(
                    session.get("service_fee")
                ),
                "hst": number_or_blank(session.get("hst")),
                "final_quote_scope": json.dumps(
                    quote.get("scope"), ensure_ascii=False
                ),
                "final_quote_notes": json.dumps(
                    quote.get("notes"), ensure_ascii=False
                ),
                "multi_visit": quote.get("multi_visit", ""),
                "tasker_needed": quote.get("tasker_needed", ""),
                "has_validated_images": bool(images),
                "has_initial_customer_message": bool(initial_message),
                "has_category_hours_and_price": has_core_labels,
                "requires_human_review": True,
            })

            status_counts[status or "missing_status"] += 1

            summary_rows.append({
                "session_id": session_id,
                "status": status,
                "review_group": review_group,
                "image_count": len(images),
                "customer_message_count": len(customer_messages),
                "has_initial_customer_message": bool(initial_message),
                "has_category": bool(str(category).strip()),
                "has_estimated_hours": hours != "",
                "has_estimated_price": price != "",
                "has_core_labels": has_core_labels,
                "requires_human_review": True,
            })

        if len({row["session_id"] for row in output_rows}) != len(output_rows):
            raise RuntimeError("Duplicate session IDs detected.")

        columns = list(output_rows[0].keys()) if output_rows else []

        with OUTPUT_FILE.open(
            "w", newline="", encoding="utf-8-sig"
        ) as file:
            writer = csv.DictWriter(file, fieldnames=columns)
            writer.writeheader()
            writer.writerows(output_rows)

        summary_columns = (
            list(summary_rows[0].keys()) if summary_rows else []
        )

        with SUMMARY_FILE.open(
            "w", newline="", encoding="utf-8-sig"
        ) as file:
            writer = csv.DictWriter(
                file, fieldnames=summary_columns
            )
            writer.writeheader()
            writer.writerows(summary_rows)

        print("\nJOB-LEVEL DATASET CREATED")
        print("=" * 42)
        print("Sessions exported:", len(output_rows))
        print(
            "Sessions with validated local images:",
            sum(row["has_validated_images"] for row in output_rows),
        )
        print(
            "Sessions with an initial customer message:",
            sum(
                row["has_initial_customer_message"]
                for row in output_rows
            ),
        )
        print(
            "Sessions with category, hours and price:",
            sum(
                row["has_category_hours_and_price"]
                for row in output_rows
            ),
        )

        print("\nSession counts by status:")
        for name, count in sorted(status_counts.items()):
            print(f"  {name}: {count}")

        print("\nDataset:", OUTPUT_FILE)
        print("Quality summary:", SUMMARY_FILE)
        print("\nNo database records were modified.")
        print("All records still require label review.")

    finally:
        if connection:
            connection.close()


if __name__ == "__main__":
    main()
