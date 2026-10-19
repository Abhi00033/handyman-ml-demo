
import csv
import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))

from db import get_connection

OUTPUT_DIR = BASE_DIR / "datasets" / "prepared"
REPORT_DIR = BASE_DIR / "datasets" / "reports"

OUTPUT_FILE = OUTPUT_DIR / "refined_question_answer_candidates.csv"
REVIEW_FILE = REPORT_DIR / "refined_question_answer_review.csv"
NON_ANSWER_FILE = REPORT_DIR / "refined_question_answer_non_answers.csv"
SUMMARY_FILE = REPORT_DIR / "refined_question_answer_summary.csv"


# Exclude final estimate/acceptance prompts from clarification-question extraction.
EXCLUDED_PATTERNS = [
    r"\bdo you accept (?:this|the) estimate\b",
    r"\bwould you like to accept (?:this|the) estimate\b",
]

# Customer messages matching these patterns are instructions or requests,
# not answers to the immediately preceding clarification question.
NON_ANSWER_PATTERNS = [
    r"\bplease\s+(?:now\s+)?provide\b",
    r"\bprovide\s+(?:the\s+)?full\s+project\s+estimate\b",
    r"\bgenerate\s+(?:the|a|my)\s+(?:full\s+)?(?:project\s+)?estimate\b",
    r"\busing the project estimate template\b",
    r"\bwrite\s+(?:the|a)\s+project estimate\b",
    r"\bcreate\s+(?:the|a)\s+project estimate\b",
    r"\bprepare\s+(?:the|a)\s+project estimate\b",
    r"\bskip\s+(?:this|that|the)\s+question\b",
]

GENERIC_YES_NO = {
    "yes", "yes please", "yes sure", "yeah", "yep", "yup",
    "no", "no thanks", "no thank you", "nope",
    "sure", "okay", "ok", "correct", "right", "absolutely",
}

CHOICE_PATTERNS = [
    r"\beither\b.{0,300}\bor\b",
    r"\bor would you\b",
    r"\bor do you\b",
    r"\bor is it\b",
    r"\bor will\b",
    r"\bwould you prefer\b",
    r"\bwhich (?:option|one)\b",
    r"\bwhich one\b",
    r"\bwhich would you like\b",
    r"\bwhich option works best\b",
    r"\bchoose\b",
    r"\boption\s*a\b",
    r"\boption\s*b\b",
    r"\boption\s+[ab]\s*:",
    r"\bA\s*\)",
    r"\bB\s*\)",
    r"\bA\s+or\s+B\b",
]

SPECIFIC_QUESTION_PATTERNS = [
    r"\bwhere\b",
    r"\bwhich wall\b",
    r"\bwhich room\b",
    r"\bwhat size\b",
    r"\bhow many\b",
    r"\bhow much\b",
    r"\bwhich one\b",
    r"\bwhich option\b",
    r"\bwhat material\b",
    r"\bwhat type\b",
    r"\bwhat kind\b",
    r"\bwhat is the issue\b",
    r"\bwhat's the issue\b",
    r"\bbattery[- ]powered\b",
    r"\bwired\b",
    r"\bdo you already have\b",
    r"\bshould the tasker bring\b",
    r"\bcould you send me a photo\b",
    r"\bcan you send me a photo\b",
]


def normalize_text(value):
    """Normalize whitespace without removing meaningful punctuation."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def parse_conversation(raw):
    """Parse the conversation JSON stored in quote_sessions."""
    if not raw:
        return []

    if isinstance(raw, (dict, list)):
        data = raw
    else:
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []

    if isinstance(data, dict):
        data = data.get("messages", [])

    if not isinstance(data, list):
        return []

    messages = []

    for item in data:
        if not isinstance(item, dict):
            continue

        role = str(
            item.get("role")
            or item.get("sender")
            or item.get("type")
            or ""
        ).strip().lower()

        if role not in {"assistant", "user"}:
            continue

        content = (
            item.get("content")
            or item.get("message")
            or item.get("text")
            or ""
        )

        if isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") in {
                        "text", "input_text", "output_text"
                    }:
                        parts.append(str(part.get("text") or ""))
                elif isinstance(part, str):
                    parts.append(part)
            content = " ".join(parts)
        elif isinstance(content, dict):
            content = content.get("text", "")

        messages.append({
            "role": role,
            "content": normalize_text(content),
        })

    return messages


def is_excluded_question(text):
    """Identify estimate acceptance prompts and final estimate questions."""
    lowered = text.casefold()

    if "project estimate" in lowered and "?" in lowered:
        return True

    return any(
        re.search(pattern, lowered, re.IGNORECASE)
        for pattern in EXCLUDED_PATTERNS
    )


def is_question_message(text):
    """Treat a complete assistant message containing a question as one unit."""
    if not text or "?" not in text:
        return False

    return not is_excluded_question(text)


def is_non_answer(answer):
    """Detect common instructions that should not be treated as answers."""
    text = normalize_text(answer).casefold()

    return any(
        re.search(pattern, text, re.IGNORECASE)
        for pattern in NON_ANSWER_PATTERNS
    )


def asks_for_choice(question):
    return any(
        re.search(pattern, question, re.IGNORECASE | re.DOTALL)
        for pattern in CHOICE_PATTERNS
    )


def asks_for_specific_detail(question):
    return any(
        re.search(pattern, question, re.IGNORECASE | re.DOTALL)
        for pattern in SPECIFIC_QUESTION_PATTERNS
    )


def is_generic_yes_no(answer):
    cleaned = normalize_text(answer).casefold().strip(" .!?")
    return cleaned in GENERIC_YES_NO


def looks_like_fragment(question):
    text = normalize_text(question).casefold()

    return text in {
        "which one?",
        "which option?",
        "which one sounds better to you?",
        "(or both?)",
    }


def classify_question(question):
    """Heuristic classification; labels still need evaluation."""
    text = question.casefold()

    rules = [
        ("location", r"\bwhere\b|\bwhich wall\b|\bwhich room\b|\blocation\b"),
        (
            "dimensions_or_quantity",
            r"\bhow many\b|\bhow much\b|\bwhat size\b|\bheight\b|\bwidth\b|\binches\b|\bsquare feet\b",
        ),
        (
            "material_supplier",
            r"\bmaterial\b|\bsupply\b|\bbring\b|\balready have\b|\bsealant\b|\bstain\b",
        ),
        (
            "schedule_or_urgency",
            r"\bwhen\b|\bdate\b|\btime\b|\burgent\b|\bschedule\b",
        ),
        (
            "existing_condition",
            r"\bwhat's wrong\b|\bwhat is wrong\b|\bissue\b|\bdamage\b|\bnot working\b|\bleaking\b",
        ),
        (
            "repair_action",
            r"\brepair\b|\breplace\b|\binstall\b|\bmount\b|\bpowerwash\b|\btroubleshoot\b",
        ),
        (
            "preferences_or_finish",
            r"\bprefer\b|\bcolour\b|\bcolor\b|\bfinish\b|\bclear sealant\b|\bstain\b",
        ),
        ("water_shutoff", r"\bwater shut\b|\bshut off\b"),
        ("access", r"\baccess\b|\bavailable\b|\benter\b"),
    ]

    matches = [
        label
        for label, pattern in rules
        if re.search(pattern, text)
    ]

    if len(matches) == 1:
        return matches[0]

    if len(matches) > 1:
        return "multiple_topics"

    return "other"


def make_record(session, index, next_user_index, question, answer):
    """Create one auditable record with conservative confidence labels."""
    flags = []

    choice_question = asks_for_choice(question)
    specific_question = asks_for_specific_detail(question)
    generic_answer = is_generic_yes_no(answer)

    if generic_answer and (choice_question or specific_question):
        flags.append("generic_answer_to_choice_or_specific_question")

    if generic_answer and choice_question:
        flags.append("unresolved_either_or_choice")

    if looks_like_fragment(question):
        flags.append("possible_question_fragment")

    confidence = (
        "requires_manual_review"
        if flags
        else "sequence_based_not_verified"
    )

    return {
        "session_id": session.get("id"),
        "assistant_message_index": index + 1,
        "customer_message_index": next_user_index + 1,
        "question_number_in_message": 1,
        "questions_in_assistant_message": 1,
        "question": question,
        "answer": answer,
        "question_type": classify_question(question),
        "pairing_confidence": confidence,
        "review_flags": ";".join(flags),
        "source_status": session.get("status"),
        "source_category": session.get("detected_category"),
        "source_task_title": session.get("task_title"),
        "verified_for_training": False,
    }


def extract_candidate_pairs(session):
    """
    Extract question/reply candidates.

    Estimate requests and other recognized instructions are written to a
    separate non-answer output instead of the Q&A candidate dataset.
    """
    messages = parse_conversation(session.get("openai_messages"))

    candidates = []
    review_records = []
    non_answer_records = []

    for index, message in enumerate(messages):
        if message["role"] != "assistant":
            continue

        question = message["content"]

        if not is_question_message(question):
            continue

        next_user_index = None
        superseded_by_new_question = False

        for next_index in range(index + 1, len(messages)):
            next_message = messages[next_index]

            if next_message["role"] == "assistant":
                if is_question_message(next_message["content"]):
                    superseded_by_new_question = True
                    break

            elif next_message["role"] == "user":
                next_user_index = next_index
                break

        if superseded_by_new_question or next_user_index is None:
            continue

        answer = messages[next_user_index]["content"]

        if not answer:
            continue

        record = make_record(
            session=session,
            index=index,
            next_user_index=next_user_index,
            question=question,
            answer=answer,
        )

        if is_non_answer(answer):
            record["pairing_confidence"] = "excluded_non_answer"
            record["review_flags"] = "instruction_or_estimate_request"
            non_answer_records.append(record)
            continue

        candidates.append(record)

        if record["review_flags"]:
            review_records.append(record)

    return candidates, review_records, non_answer_records


def write_csv(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    # Read-only SELECT. This script does not modify database records.
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT
                    id,
                    status,
                    detected_category,
                    task_title,
                    openai_messages
                FROM quote_sessions
                WHERE deleted_at IS NULL
                  AND status <> 'deleted'
                  AND openai_messages IS NOT NULL
                ORDER BY id
            """)
            sessions = cursor.fetchall()
    finally:
        connection.close()

    candidate_rows = []
    review_rows = []
    non_answer_rows = []

    parsed_sessions = 0
    empty_or_unparsed_sessions = 0

    for session in sessions:
        messages = parse_conversation(session.get("openai_messages"))

        if messages:
            parsed_sessions += 1
        else:
            empty_or_unparsed_sessions += 1

        candidates, reviews, non_answers = extract_candidate_pairs(session)

        candidate_rows.extend(candidates)
        review_rows.extend(reviews)
        non_answer_rows.extend(non_answers)

    fields = [
        "session_id",
        "assistant_message_index",
        "customer_message_index",
        "question_number_in_message",
        "questions_in_assistant_message",
        "question",
        "answer",
        "question_type",
        "pairing_confidence",
        "review_flags",
        "source_status",
        "source_category",
        "source_task_title",
        "verified_for_training",
    ]

    write_csv(OUTPUT_FILE, candidate_rows, fields)
    write_csv(REVIEW_FILE, review_rows, fields)
    write_csv(NON_ANSWER_FILE, non_answer_rows, fields)

    summary = [
        {"metric": "sessions_returned_by_query", "value": len(sessions)},
        {"metric": "sessions_with_parseable_messages", "value": parsed_sessions},
        {"metric": "sessions_empty_or_unparsed", "value": empty_or_unparsed_sessions},
        {"metric": "candidate_pairs_after_non_answer_filter", "value": len(candidate_rows)},
        {"metric": "candidates_flagged_for_review", "value": len(review_rows)},
        {"metric": "non_answer_records_separated", "value": len(non_answer_rows)},
        {
            "metric": "sequence_pairs_not_verified",
            "value": sum(
                row["pairing_confidence"] == "sequence_based_not_verified"
                for row in candidate_rows
            ),
        },
        {
            "metric": "candidates_requiring_manual_review",
            "value": sum(
                row["pairing_confidence"] == "requires_manual_review"
                for row in candidate_rows
            ),
        },
        {"metric": "verified_for_training", "value": 0},
    ]

    with SUMMARY_FILE.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=["metric", "value"])
        writer.writeheader()
        writer.writerows(summary)

    print("\nRefined question-answer extraction completed.")
    for item in summary:
        print(f"{item['metric']}: {item['value']}")

    print("\nCandidate dataset:", OUTPUT_FILE)
    print("Manual review report:", REVIEW_FILE)
    print("Separated non-answer records:", NON_ANSWER_FILE)
    print("Summary report:", SUMMARY_FILE)
    print("\nDatabase was queried only. No records were modified.")
    print(
        "All remaining candidates are unverified. "
        "Do not use them for training without further validation."
    )


if __name__ == "__main__":
    main()
