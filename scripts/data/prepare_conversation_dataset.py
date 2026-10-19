import csv
import json
from pathlib import Path

from db import get_connection


BASE_DIR = Path(__file__).resolve().parents[2]
DATASET_DIR = BASE_DIR / "datasets"
PREPARED_DIR = DATASET_DIR / "prepared"
REPORTS_DIR = DATASET_DIR / "reports"

IMAGE_MANIFEST_FILE = DATASET_DIR / "image_download_manifest.csv"

CONVERSATION_OUTPUT = (
    PREPARED_DIR / "conversation_training_pairs.csv"
)

SCOPE_OUTPUT = PREPARED_DIR / "job_scope_records.csv"

SUMMARY_OUTPUT = (
    REPORTS_DIR / "job_scope_extraction_summary.csv"
)


def parse_json(value):
    """Parse JSON values stored in the database."""
    if isinstance(value, (dict, list)):
        return value

    if not isinstance(value, str) or not value.strip():
        return None

    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def content_to_text(content):
    """
    Extract readable text without copying image URLs or image payloads
    into the text dataset.
    """
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts = [
            content_to_text(item)
            for item in content
        ]

        return "\n".join(
            part for part in parts if part
        )

    if isinstance(content, dict):
        content_type = str(content.get("type") or "").lower()

        if content_type in {
            "image",
            "image_url",
            "input_image",
        }:
            return "[Image attachment]"

        if content_type in {
            "text",
            "input_text",
            "output_text",
        }:
            text = content.get("text")

            if isinstance(text, str):
                return text.strip()

        # Handle common content structures.
        for key in ("text", "content", "value"):
            if key in content:
                text = content_to_text(content[key])

                if text:
                    return text

        # Do not serialize arbitrary dictionaries because they may
        # contain image URLs, encoded images, or other non-text data.

    return ""


def normalize_role(message):
    """Normalize known customer and assistant role names."""
    role = str(
        message.get("role")
        or message.get("sender")
        or ""
    ).strip().lower()

    if role in {"user", "customer", "human"}:
        return "user"

    if role in {"assistant", "ai", "bot"}:
        return "assistant"

    return role or "unknown"


def extract_messages(raw_messages):
    """
    Convert stored conversation messages into ordered text records.

    Non-user/non-assistant messages are preserved as roles but are
    not used as customer answers or assistant responses.
    """
    messages = parse_json(raw_messages)

    if not isinstance(messages, list):
        return []

    extracted = []

    for index, message in enumerate(messages, start=1):
        if not isinstance(message, dict):
            continue

        role = normalize_role(message)
        content = content_to_text(message.get("content"))

        if not content:
            continue

        extracted.append({
            "message_number": index,
            "role": role,
            "content": content,
        })

    return extracted


def make_message_pairs(messages):
    """
    Pair a customer message with the next assistant response.

    This preserves the existing dataset's pairing approach.
    These pairs are conversation examples, not verified answer labels.
    """
    pairs = []
    pending_user = None

    for message in messages:
        role = message["role"]
        content = message["content"]

        if role == "user":
            # An unanswered earlier user message is not paired.
            pending_user = message

        elif role == "assistant" and pending_user:
            pairs.append({
                "customer_message": pending_user["content"],
                "assistant_response": content,
                "user_message_number": pending_user[
                    "message_number"
                ],
                "assistant_message_number": message[
                    "message_number"
                ],
            })

            pending_user = None

    return pairs


def load_image_manifest():
    """
    Load successfully downloaded images grouped by quote session.

    Only images with confirmed local download statuses are included.
    """
    images_by_session = {}

    if not IMAGE_MANIFEST_FILE.exists():
        print(
            "Image manifest not found. "
            "Image paths will be empty."
        )
        return images_by_session

    with IMAGE_MANIFEST_FILE.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            if row.get("status") not in {
                "downloaded",
                "already_downloaded",
            }:
                continue

            session_id = row.get("session_id")
            local_path = row.get("local_path")

            if not session_id or not local_path:
                continue

            images_by_session.setdefault(
                str(session_id), []
            ).append(local_path)

    # Avoid duplicate local paths.
    for session_id in images_by_session:
        images_by_session[session_id] = list(
            dict.fromkeys(images_by_session[session_id])
        )

    return images_by_session


def json_text(value):
    """Convert structured values to compact JSON for CSV storage."""
    if value is None:
        return ""

    return json.dumps(
        value,
        ensure_ascii=False,
        default=str,
    )


def first_customer_message(messages):
    """Return the first recorded customer message."""
    for message in messages:
        if message["role"] == "user":
            return message["content"]

    return ""


def collect_customer_messages(messages):
    """Return all customer messages in conversation order."""
    return [
        message["content"]
        for message in messages
        if message["role"] == "user"
    ]


def collect_assistant_messages(messages):
    """Return all assistant messages in conversation order."""
    return [
        message["content"]
        for message in messages
        if message["role"] == "assistant"
    ]


def extract_scope(quote):
    """
    Extract stored final quote fields.

    The presence of a stored scope does not prove that it was
    independently verified or that the final work matched it.
    """
    if not isinstance(quote, dict):
        quote = {}

    scope = quote.get("scope")
    notes = quote.get("notes")

    if isinstance(scope, str):
        scope_text = scope.strip()
    elif scope is None:
        scope_text = ""
    else:
        scope_text = json_text(scope)

    if isinstance(notes, str):
        notes_text = notes.strip()
    elif notes is None:
        notes_text = ""
    else:
        notes_text = json_text(notes)

    return scope_text, notes_text


def main():
    PREPARED_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    images_by_session = load_image_manifest()

    connection = None
    conversation_rows = []
    scope_rows = []
    sessions_read = 0
    sessions_with_messages = 0
    sessions_with_initial_request = 0
    sessions_with_final_scope = 0
    sessions_with_images = 0
    sessions_without_category = 0
    sessions_without_hours = 0

    try:
        connection = get_connection()

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    status,
                    detected_category,
                    category_id,
                    task_level,
                    task_level_id,
                    estimated_hours,
                    estimated_price,
                    estimated_price_min,
                    estimated_price_max,
                    estimated_total,
                    estimated_total_min,
                    estimated_total_max,
                    openai_messages,
                    final_quote
                FROM quote_sessions
                WHERE status <> 'deleted'
                  AND deleted_at IS NULL
                ORDER BY id
                """
            )

            sessions = cursor.fetchall()

        sessions_read = len(sessions)

        for session in sessions:
            session_id = session["id"]

            messages = extract_messages(
                session.get("openai_messages")
            )

            quote = parse_json(
                session.get("final_quote")
            )

            if not isinstance(quote, dict):
                quote = {}

            pairs = make_message_pairs(messages)

            initial_request = first_customer_message(messages)
            customer_messages = collect_customer_messages(messages)
            assistant_messages = collect_assistant_messages(messages)

            followup_answers = customer_messages[1:]

            image_paths = images_by_session.get(
                str(session_id), []
            )

            scope_text, notes_text = extract_scope(quote)

            category = (
                session.get("detected_category")
                or quote.get("detected_category")
            )

            category_id = (
                session.get("category_id")
                if session.get("category_id") is not None
                else quote.get("detected_category_id")
            )

            estimated_hours = session.get("estimated_hours")

            if estimated_hours is None:
                estimated_hours = quote.get("total_hours")

            if messages:
                sessions_with_messages += 1

            if initial_request:
                sessions_with_initial_request += 1

            if scope_text:
                sessions_with_final_scope += 1

            if image_paths:
                sessions_with_images += 1

            if not category_id and not category:
                sessions_without_category += 1

            if estimated_hours is None:
                sessions_without_hours += 1

            # One row per session for job-scope analysis.
            scope_rows.append({
                "session_id": session_id,
                "status": session.get("status"),
                "initial_customer_request": initial_request,
                "all_customer_messages": json_text(
                    customer_messages
                ),
                "customer_followup_answers": json_text(
                    followup_answers
                ),
                "assistant_messages": json_text(
                    assistant_messages
                ),
                "customer_message_count": len(
                    customer_messages
                ),
                "assistant_message_count": len(
                    assistant_messages
                ),
                "session_image_paths": json_text(image_paths),
                "session_image_count": len(image_paths),
                "detected_category": category,
                "category_id": category_id,
                "task_level": (
                    session.get("task_level")
                    if session.get("task_level") is not None
                    else quote.get("task_level")
                ),
                "task_level_id": (
                    session.get("task_level_id")
                    if session.get("task_level_id") is not None
                    else quote.get("task_level_id")
                ),
                "estimated_hours": estimated_hours,
                "estimated_price": session.get(
                    "estimated_price"
                ),
                "estimated_price_min": session.get(
                    "estimated_price_min"
                ),
                "estimated_price_max": session.get(
                    "estimated_price_max"
                ),
                "estimated_total": session.get(
                    "estimated_total"
                ),
                "estimated_total_min": session.get(
                    "estimated_total_min"
                ),
                "estimated_total_max": session.get(
                    "estimated_total_max"
                ),
                "final_quote_total_hours": quote.get(
                    "total_hours"
                ),
                "final_quote_scope": scope_text,
                "final_quote_notes": notes_text,
                "multi_visit": quote.get("multi_visit"),
                "tasker_needed": quote.get("tasker_needed"),
                "has_initial_request": bool(initial_request),
                "has_final_quote_scope": bool(scope_text),
                "has_category": bool(category_id or category),
                "has_estimated_hours": estimated_hours is not None,
                "has_downloaded_images": bool(image_paths),
                "assistant_text_is_verified_ground_truth": False,
            })

            # Keep the existing conversation-pair dataset, but make
            # the distinction between conversation examples and
            # verified training labels explicit.
            for turn_number, pair in enumerate(pairs, start=1):
                conversation_rows.append({
                    "session_id": session_id,
                    "turn_number": turn_number,
                    "user_message_number": pair[
                        "user_message_number"
                    ],
                    "assistant_message_number": pair[
                        "assistant_message_number"
                    ],
                    "status": session.get("status"),
                    "customer_message": pair[
                        "customer_message"
                    ],
                    "assistant_response": pair[
                        "assistant_response"
                    ],
                    "session_image_paths": json_text(
                        image_paths
                    ),
                    "detected_category": category,
                    "category_id": category_id,
                    "estimated_hours": estimated_hours,
                    "estimated_price": session.get(
                        "estimated_price"
                    ),
                    "estimated_price_min": session.get(
                        "estimated_price_min"
                    ),
                    "estimated_price_max": session.get(
                        "estimated_price_max"
                    ),
                    "estimated_total": session.get(
                        "estimated_total"
                    ),
                    "final_quote_scope": scope_text,
                    "final_quote_notes": notes_text,
                    "multi_visit": quote.get("multi_visit"),
                    "tasker_needed": quote.get("tasker_needed"),
                    "assistant_response_is_verified_label": False,
                })

        scope_fields = [
            "session_id",
            "status",
            "initial_customer_request",
            "all_customer_messages",
            "customer_followup_answers",
            "assistant_messages",
            "customer_message_count",
            "assistant_message_count",
            "session_image_paths",
            "session_image_count",
            "detected_category",
            "category_id",
            "task_level",
            "task_level_id",
            "estimated_hours",
            "estimated_price",
            "estimated_price_min",
            "estimated_price_max",
            "estimated_total",
            "estimated_total_min",
            "estimated_total_max",
            "final_quote_total_hours",
            "final_quote_scope",
            "final_quote_notes",
            "multi_visit",
            "tasker_needed",
            "has_initial_request",
            "has_final_quote_scope",
            "has_category",
            "has_estimated_hours",
            "has_downloaded_images",
            "assistant_text_is_verified_ground_truth",
        ]

        conversation_fields = [
            "session_id",
            "turn_number",
            "user_message_number",
            "assistant_message_number",
            "status",
            "customer_message",
            "assistant_response",
            "session_image_paths",
            "detected_category",
            "category_id",
            "estimated_hours",
            "estimated_price",
            "estimated_price_min",
            "estimated_price_max",
            "estimated_total",
            "final_quote_scope",
            "final_quote_notes",
            "multi_visit",
            "tasker_needed",
            "assistant_response_is_verified_label",
        ]

        def write_csv(path, fields, rows):
            with path.open(
                "w",
                newline="",
                encoding="utf-8-sig",
            ) as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=fields,
                    extrasaction="ignore",
                )
                writer.writeheader()
                writer.writerows(rows)

        write_csv(
            SCOPE_OUTPUT,
            scope_fields,
            scope_rows,
        )

        write_csv(
            CONVERSATION_OUTPUT,
            conversation_fields,
            conversation_rows,
        )

        summary = [
            {
                "metric": "sessions_read",
                "value": sessions_read,
            },
            {
                "metric": "sessions_with_messages",
                "value": sessions_with_messages,
            },
            {
                "metric": "sessions_with_initial_request",
                "value": sessions_with_initial_request,
            },
            {
                "metric": "sessions_with_final_scope",
                "value": sessions_with_final_scope,
            },
            {
                "metric": "sessions_with_downloaded_images",
                "value": sessions_with_images,
            },
            {
                "metric": "sessions_without_category",
                "value": sessions_without_category,
            },
            {
                "metric": "sessions_without_estimated_hours",
                "value": sessions_without_hours,
            },
            {
                "metric": "conversation_pairs_created",
                "value": len(conversation_rows),
            },
        ]

        write_csv(
            SUMMARY_OUTPUT,
            ["metric", "value"],
            summary,
        )

        print("\nJob-scope extraction completed.")
        print("Database sessions read:", sessions_read)
        print("Sessions with messages:", sessions_with_messages)
        print(
            "Sessions with initial request:",
            sessions_with_initial_request,
        )
        print(
            "Sessions with final quote scope:",
            sessions_with_final_scope,
        )
        print(
            "Sessions with downloaded images:",
            sessions_with_images,
        )
        print(
            "Sessions without category:",
            sessions_without_category,
        )
        print(
            "Sessions without estimated hours:",
            sessions_without_hours,
        )
        print(
            "Conversation pairs created:",
            len(conversation_rows),
        )
        print("\nGenerated files:")
        print("Job scope records:", SCOPE_OUTPUT)
        print("Conversation pairs:", CONVERSATION_OUTPUT)
        print("Extraction summary:", SUMMARY_OUTPUT)
        print(
            "\nImportant: these records are automatically extracted "
            "historical data, not verified training labels. Image paths "
            "are session-level and are not assigned to individual turns."
        )

    except Exception as exc:
        print("Job-scope extraction failed:", str(exc))
        raise

    finally:
        if connection:
            connection.close()


if __name__ == "__main__":
    main()