
import csv
import json
import re
from collections import Counter
from pathlib import Path

from db import get_connection


# ---------------------------------------------------------
# PATHS
# ---------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parents[2]

PREPARED_DIR = ROOT_DIR / "datasets" / "prepared"
REPORTS_DIR = ROOT_DIR / "datasets" / "reports"

PAIRS_FILE = PREPARED_DIR / "question_answer_pairs.csv"
SUMMARY_FILE = REPORTS_DIR / "question_answer_extraction_summary.csv"


# ---------------------------------------------------------
# GENERAL HELPERS
# ---------------------------------------------------------

def parse_json(value):
    """Parse JSON safely. Return None if parsing fails."""
    if value is None:
        return None

    if isinstance(value, (list, dict)):
        return value

    if not isinstance(value, str):
        return None

    value = value.strip()

    if not value:
        return None

    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def clean_text(value):
    """Normalize extracted text and remove common Markdown artifacts."""
    if value is None:
        return ""

    if isinstance(value, list):
        parts = []

        for item in value:
            if isinstance(item, dict):
                text_value = item.get("text")

                if text_value:
                    parts.append(str(text_value))
            elif isinstance(item, str):
                parts.append(item)

        value = "\n".join(parts)

    elif isinstance(value, dict):
        value = value.get("text", "")

    value = str(value)

    # Remove common Markdown formatting without deleting the text.
    value = re.sub(r"!\[[^\]]*\]\([^)]*\)", "[Image attachment]", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"```.*?```", " ", value, flags=re.DOTALL)
    value = re.sub(r"(?<!\*)\*\*(.*?)\*\*(?!\*)", r"\1", value, flags=re.DOTALL)
    value = re.sub(r"(?<!\*)\*(.*?)\*(?!\*)", r"\1", value, flags=re.DOTALL)
    value = re.sub(r"(?<!_)__(.*?)__(?!_)", r"\1", value, flags=re.DOTALL)
    value = re.sub(r"`([^`]*)`", r"\1", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)

    return value.strip()


def content_to_text(content):
    """
    Convert a message's content to readable text.

    Handles ordinary strings and common structured content formats.
    Image-only content is not treated as a textual answer.
    """
    if isinstance(content, str):
        return clean_text(content)

    if isinstance(content, list):
        parts = []

        for item in content:
            if isinstance(item, str):
                parts.append(item)
                continue

            if not isinstance(item, dict):
                continue

            item_type = item.get("type", "")

            if item_type in ("text", "input_text", "output_text"):
                text_value = item.get("text")

                if text_value:
                    parts.append(str(text_value))

            elif item_type in ("image_url", "input_image"):
                # Do not include image URLs or encoded image data.
                continue

        return clean_text("\n".join(parts))

    if isinstance(content, dict):
        return clean_text(content.get("text", ""))

    return ""


def normalize_role(role):
    """Normalize common message-role variations."""
    role = str(role or "").strip().lower()

    if role in ("user", "customer", "human"):
        return "user"

    if role in ("assistant", "ai", "bot"):
        return "assistant"

    return role


def extract_messages(raw_messages):
    """Convert stored conversation JSON into normalized messages."""
    data = parse_json(raw_messages)

    if isinstance(data, dict):
        data = data.get("messages", [])

    if not isinstance(data, list):
        return []

    messages = []

    for index, item in enumerate(data):
        if not isinstance(item, dict):
            continue

        role = normalize_role(
            item.get("role")
            or item.get("sender")
            or item.get("type")
        )

        content = item.get("content")

        if content is None:
            content = item.get("message", item.get("text", ""))

        text = content_to_text(content)

        if not role or not text:
            continue

        messages.append({
            "message_index": index,
            "role": role,
            "text": text,
        })

    return messages


# ---------------------------------------------------------
# FINAL QUOTE DETECTION
# ---------------------------------------------------------

FINAL_QUOTE_PATTERNS = [
    r"\bPROJECT ESTIMATE\b",
    r"\bPROJECT SCOPE\b",
    r"\bLABOU?R TIME\b",
    r"\bESTIMATED TOTAL\b",
    r"\bESTIMATED PRICE\b",
    r"\bTASKER NEEDED\b",
    r"\bDETECTED CATEGORY\b",
    r"\bTOTAL HOURS\b",
]


def is_final_quote_message(text):
    """
    Detect generated quote/estimate messages.

    Acceptance questions inside a final quote must not be learned
    as technical scope questions.
    """
    text_upper = str(text or "").upper()

    return any(
        re.search(pattern, text_upper, re.IGNORECASE)
        for pattern in FINAL_QUOTE_PATTERNS
    )


# ---------------------------------------------------------
# QUESTION EXTRACTION
# ---------------------------------------------------------

def clean_question(question):
    """Clean question prefixes and formatting."""
    question = clean_text(question)

    question = re.sub(
        r"^\s*(?:question\s*)?\d+\s*/\s*\d+\s*:\s*",
        "",
        question,
        flags=re.IGNORECASE,
    )

    question = re.sub(r"^\s*[-*•]+\s*", "", question)
    question = re.sub(r"^\s*[*_`]+", "", question)
    question = re.sub(r"[*_`]+\s*$", "", question)
    question = re.sub(r"\s+", " ", question)

    return question.strip(" \t\n-*")



def extract_questions(text):
    """
    Extract clarification questions without splitting a compound
    question at every question mark.

    Explicit Question N/N labels separate distinct follow-up turns.
    Otherwise, each paragraph containing a question is kept together.
    """
    text = clean_text(text)

    if not text or is_final_quote_message(text):
        return []

    labelled_pattern = re.compile(
        r"(?:^|\n)\s*(?:\*\*)?\s*"
        r"Question\s+\d+\s*/\s*\d+\s*:\s*"
        r"(.*?)"
        r"(?=(?:\n\s*(?:\*\*)?\s*Question\s+\d+\s*/\s*\d+\s*:)|$)",
        flags=re.IGNORECASE | re.DOTALL,
    )

    labelled_matches = labelled_pattern.findall(text)

    if labelled_matches:
        questions = []

        for match in labelled_matches:
            question = clean_question(match)

            # Keep all related question marks and examples together.
            if "?" in question and not is_quote_acceptance_question(question):
                questions.append(question)

        return unique_questions(questions)

    return split_question_sentences(text)


def split_question_sentences(text):
    """
    Keep compound questions and their examples together.
    Split only at paragraph boundaries, not at every '?'.
    """
    text = clean_text(text)

    if not text:
        return []

    paragraphs = re.split(r"\n\s*\n+", text)
    questions = []

    for paragraph in paragraphs:
        paragraph = clean_question(paragraph)

        if "?" not in paragraph:
            continue

        if is_quote_acceptance_question(paragraph):
            continue

        if len(paragraph) < 8:
            continue

        questions.append(paragraph)

    return unique_questions(questions)


def split_question_sentences(text):
    """
    Extract question sentences while preserving common abbreviations
    and avoiding splitting on decimal numbers.
    """
    text = clean_text(text)

    if not text:
        return []

    # Remove common Markdown list/heading markers.
    text = re.sub(r"(?m)^\s*#{1,6}\s*", "", text)
    text = re.sub(r"(?m)^\s*[-*•]\s+", "", text)

    # Split on question marks. A question may span multiple clauses.
    chunks = re.split(r"(?<=\?)\s+", text)

    questions = []

    for chunk in chunks:
        chunk = clean_question(chunk)

        if "?" not in chunk:
            continue

        # Keep each question-mark-terminated segment.
        segments = re.findall(r"[^?]*\?", chunk)

        for segment in segments:
            question = clean_question(segment)

            if not question:
                continue

            # Reject obvious acceptance/confirmation questions.
            if is_quote_acceptance_question(question):
                continue

            if len(question) < 8:
                continue

            questions.append(question)

    return questions


def is_quote_acceptance_question(text):
    """Identify quote approval questions, not technical scope questions."""
    normalized = re.sub(r"\s+", " ", str(text or "").lower()).strip()

    patterns = [
        r"\bdo you accept (?:this|the) (?:estimate|quote)\b",
        r"\bwould you like to proceed\b",
        r"\bdo you approve (?:this|the) (?:estimate|quote)\b",
        r"\bshall we proceed\b",
        r"\bis (?:this|the) (?:estimate|quote) acceptable\b",
        r"\bdo you agree to (?:this|the) (?:estimate|quote)\b",
    ]

    return any(re.search(pattern, normalized) for pattern in patterns)


def unique_questions(questions):
    """Remove duplicate questions while preserving order."""
    result = []
    seen = set()

    for question in questions:
        question = clean_question(question)
        key = question.casefold()

        if key and key not in seen:
            seen.add(key)
            result.append(question)

    return result


# ---------------------------------------------------------
# QUESTION TOPIC CLASSIFICATION
# ---------------------------------------------------------

def classify_question(question):
    """
    Classify common handyman follow-up questions.

    This is rule-based classification, not a verified semantic label.
    Multiple matching topics are explicitly marked as multiple_topics.
    """
    text = re.sub(r"\s+", " ", str(question or "").lower()).strip()

    # Quote acceptance is not a job-scope clarification.
    if is_quote_acceptance_question(text):
        return "quote_acceptance"

    rules = [
        (
            "repair_action",
            r"\brepair\b|\breplace\b|\bfully replaced\b|\bfix(?:ed|ing)?\b"
            r"|\binstall(?:ation)?\b|\bremove\b|\brefinish\b",
        ),
        (
            "size_or_replacement_scope",
            r"\bhow much\b|\bhow many\b|\bhow long\b|\bsize\b"
            r"|\bdimensions?\b|\bmeasurements?\b|\bsection\b|\blength\b"
            r"|\barea\b|\bsquare feet\b|\bvisible piping\b|\bwhole\b"
            r"|\bpart of\b|\bextent\b",
        ),
        (
            "water_shutoff",
            r"\bwater shut\b|\bshut off\b|\bshutoff\b|\bactively leaking\b"
            r"|\bstill leaking\b|\bwater supply\b|\bwater turned off\b",
        ),
        (
            "material_supplier",
            r"\bmaterials?\b|\bsuppl(?:y|ied)\b|\bbring\b|\bpurchased\b"
            r"|\bbought\b|\bhave you got\b|\bwho provides\b|\btasker\b"
            r"|\bprovided by\b",
        ),
        (
            "access",
            r"\baccess\b|\baccessible\b|\breach\b|\breachable\b|\bladder\b"
            r"|\bheight\b|\bceiling\b|\bbehind the wall\b|\bunder the sink\b",
        ),
        (
            "location",
            r"\bwhere\b|\bwhich room\b|\bwhich wall\b|\blocation\b"
            r"|\bindoors?\b|\boutdoors?\b|\bgarage\b|\bbasement\b"
            r"|\bbathroom\b|\bkitchen\b|\bliving room\b|\bbedroom\b",
        ),
        (
            "existing_condition",
            r"\bcurrent(?:ly)?\b|\bexisting\b|\bcondition\b|\bdamaged\b"
            r"|\bbroken\b|\bcracked\b|\bleaking\b|\bworking\b|\bfunctional\b",
        ),
        (
            "dimensions_or_quantity",
            r"\bquantity\b|\bnumber of\b|\bcount\b|\bhow many\b|\bmeasure\b"
            r"|\bmeasurements?\b|\binches?\b|\bcentimeters?\b"
            r"|\bmillimeters?\b|\bfeet\b|\bmeters?\b|\bmetres?\b",
        ),
        (
            "preferences_or_finish",
            r"\bprefer\b|\bpreference\b|\bfinish\b|\bcolour\b|\bcolor\b"
            r"|\bstyle\b|\bdesign\b|\beye level\b|\bappearance\b"
            r"|\blook\b|\bvisible\b|\bhide\b",
        ),
        (
            "schedule_or_urgency",
            r"\bwhen\b|\bavailable\b|\bschedule\b|\bdate\b|\btime\b"
            r"|\burgent\b|\bemergency\b|\btoday\b|\bas soon as possible\b",
        ),
        (
            "property_or_job_context",
            r"\bproperty\b|\bhouse\b|\bhome\b|\bbuilding\b|\bunit\b"
            r"|\bcondo\b|\bapartment\b|\btenant\b|\bowner\b",
        ),
        (
            "safety_or_qualification",
            r"\bsafe\b|\bsafety\b|\blicensed\b|\belectrician\b|\bplumber\b"
            r"|\bpermit\b|\bcode\b|\bpower off\b|\bbreaker\b",
        ),
        (
            "confirmation_or_acceptance",
            r"\bdo you agree\b|\bdo you accept\b|\bsound good\b"
            r"|\bis that okay\b|\bconfirm\b|\bwould you like to proceed\b",
        ),
    ]

    matches = [
        label
        for label, pattern in rules
        if re.search(pattern, text, re.IGNORECASE)
    ]

    if len(matches) == 1:
        return matches[0]

    if len(matches) > 1:
        return "multiple_topics"

    return "other"


# ---------------------------------------------------------
# CONVERSATION PAIRING
# ---------------------------------------------------------

def get_answer_candidate(text):
    """
    Return a usable customer answer, or an empty string for image-only
    or placeholder messages.
    """
    text = clean_text(text)

    if not text:
        return ""

    normalized = text.casefold().strip()

    placeholders = {
        "[image attachment]",
        "[image]",
        "[photo attachment]",
        "[attachment]",
        "image attachment",
    }

    if normalized in placeholders:
        return ""

    if re.fullmatch(r"(?:\s*\[image attachment\]\s*)+", normalized):
        return ""

    return text


def extract_pairs_for_session(session, messages):
    """
    Pair assistant questions with the next customer response.

    If an assistant message contains multiple questions and only one
    customer reply follows, the pairing is ambiguous. Those rows are
    retained for review and marked accordingly.
    """
    rows = []
    pending_questions = []
    pending_assistant_index = None
    pending_question_count = 0

    for message in messages:
        role = message["role"]
        text = message["text"]
        message_index = message["message_index"]

        if role == "assistant":
            # Final quote/estimate messages are not technical follow-ups.
            if is_final_quote_message(text):
                pending_questions = []
                pending_assistant_index = None
                pending_question_count = 0
                continue

            questions = extract_questions(text)

            if questions:
                pending_questions = questions
                pending_assistant_index = message_index
                pending_question_count = len(questions)

        elif role == "user":
            answer = get_answer_candidate(text)

            if not answer or not pending_questions:
                continue

            ambiguous = pending_question_count > 1

            for question_number, question in enumerate(pending_questions, start=1):
                rows.append({
                    "session_id": session.get("id"),
                    "status": session.get("status"),
                    "assistant_message_index": pending_assistant_index,
                    "customer_message_index": message_index,
                    "question_number_in_message": question_number,
                    "questions_in_assistant_message": pending_question_count,
                    "question": question,
                    "answer": answer,
                    "question_type": classify_question(question),
                    "detected_category": session.get("detected_category"),
                    "category_id": session.get("category_id"),
                    "estimated_hours": session.get("estimated_hours"),
                    "estimated_price": session.get("estimated_price"),
                    "pairing_confidence": (
                        "ambiguous_multiple_questions"
                        if ambiguous
                        else "sequence_based_not_verified"
                    ),
                    "is_verified_training_label": False,
                })

            # A customer response consumes the pending question(s).
            pending_questions = []
            pending_assistant_index = None
            pending_question_count = 0

    return rows


# ---------------------------------------------------------
# DATABASE EXTRACTION
# ---------------------------------------------------------

def load_sessions():
    """
    Read the required fields from MariaDB.
    This script does not insert, update, or delete database records.
    """
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    status,
                    detected_category,
                    category_id,
                    estimated_hours,
                    estimated_price,
                    openai_messages
                FROM quote_sessions
                WHERE status <> 'deleted'
                  AND deleted_at IS NULL
                ORDER BY id
                """
            )

            return cursor.fetchall()

    finally:
        connection.close()


# ---------------------------------------------------------
# OUTPUT FILES
# ---------------------------------------------------------

def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(rows)


def main():
    PREPARED_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    print("Reading quote sessions from MariaDB...")

    sessions = load_sessions()

    all_pairs = []
    summary_rows = []

    total_sessions_with_messages = 0
    total_sessions_with_questions = 0
    total_assistant_messages = 0
    total_questions_extracted = 0

    for session in sessions:
        messages = extract_messages(session.get("openai_messages"))

        if messages:
            total_sessions_with_messages += 1

        assistant_messages = [
            message for message in messages
            if message["role"] == "assistant"
        ]

        extracted_questions = []

        for message in assistant_messages:
            if is_final_quote_message(message["text"]):
                continue

            extracted_questions.extend(extract_questions(message["text"]))

        if extracted_questions:
            total_sessions_with_questions += 1

        total_assistant_messages += len(assistant_messages)
        total_questions_extracted += len(extracted_questions)

        session_pairs = extract_pairs_for_session(session, messages)
        all_pairs.extend(session_pairs)

        summary_rows.append({
            "session_id": session.get("id"),
            "status": session.get("status"),
            "message_count": len(messages),
            "assistant_message_count": len(assistant_messages),
            "questions_extracted": len(extracted_questions),
            "question_answer_pairs": len(session_pairs),
            "has_messages": bool(messages),
            "has_questions": bool(extracted_questions),
            "has_pairs": bool(session_pairs),
            "pairing_is_verified": False,
        })

    pair_fields = [
        "session_id",
        "status",
        "assistant_message_index",
        "customer_message_index",
        "question_number_in_message",
        "questions_in_assistant_message",
        "question",
        "answer",
        "question_type",
        "detected_category",
        "category_id",
        "estimated_hours",
        "estimated_price",
        "pairing_confidence",
        "is_verified_training_label",
    ]

    summary_fields = [
        "session_id",
        "status",
        "message_count",
        "assistant_message_count",
        "questions_extracted",
        "question_answer_pairs",
        "has_messages",
        "has_questions",
        "has_pairs",
        "pairing_is_verified",
    ]

    write_csv(PAIRS_FILE, all_pairs, pair_fields)
    write_csv(SUMMARY_FILE, summary_rows, summary_fields)

    type_counts = Counter(
        row["question_type"] for row in all_pairs
    )

    confidence_counts = Counter(
        row["pairing_confidence"] for row in all_pairs
    )

    print("\nQuestion-answer extraction completed.")
    print(f"Sessions read: {len(sessions)}")
    print(f"Sessions with messages: {total_sessions_with_messages}")
    print(f"Sessions with extracted questions: {total_sessions_with_questions}")
    print(f"Assistant messages inspected: {total_assistant_messages}")
    print(f"Questions extracted: {total_questions_extracted}")
    print(f"Question-answer pairs written: {len(all_pairs)}")

    print("\nQuestion types:")
    for question_type, count in sorted(type_counts.items()):
        print(f"  {question_type}: {count}")

    print("\nPairing confidence:")
    for confidence, count in sorted(confidence_counts.items()):
        print(f"  {confidence}: {count}")

    print("\nOutput files:")
    print(f"  {PAIRS_FILE.relative_to(ROOT_DIR)}")
    print(f"  {SUMMARY_FILE.relative_to(ROOT_DIR)}")

    print("\nImportant:")
    print("  Extracted pairs are not verified training labels.")
    print("  Ambiguous multi-question pairs should be reviewed before training.")


if __name__ == "__main__":
    main()
