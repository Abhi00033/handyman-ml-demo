
import csv
import re
from collections import Counter
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    BASE_DIR
    / "datasets"
    / "prepared"
    / "question_answer_pairs.csv"
)

REPORT_DIR = BASE_DIR / "datasets" / "reports"

DETAIL_REPORT = REPORT_DIR / "question_answer_validation.csv"
SUMMARY_REPORT = REPORT_DIR / "question_answer_validation_summary.csv"


PLACEHOLDERS = {
    "",
    "*",
    "**",
    "n/a",
    "na",
    "none",
    "null",
    "unknown",
    "not specified",
    "[image attachment]",
    "[image]",
    "[attachment]",
    "image attachment",
}

KNOWN_CONFIDENCES = {
    "ambiguous_multiple_questions",
    "sequence_based_not_verified",
}


def clean_text(value):
    """Normalize whitespace and formatting without removing underscores."""
    if value is None:
        return ""

    text = str(value).strip()
    text = re.sub(r"\s+", " ", text)

    # Preserve underscores because they are part of confidence labels.
    text = text.replace("*", "").replace("`", "")

    return text.strip()


def is_placeholder(value):
    """Return True for empty or known placeholder values."""
    text = clean_text(value).casefold()

    if text in PLACEHOLDERS:
        return True

    if re.fullmatch(
        r"(?:\s*\[image attachment\]\s*)+",
        text,
        flags=re.IGNORECASE,
    ):
        return True

    return False


def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def split_issues(value):
    """Convert a semicolon-separated issue string to a set."""
    return {
        item.strip()
        for item in str(value or "").split(";")
        if item.strip()
    }


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Input CSV not found: {INPUT_FILE}"
        )

    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    with INPUT_FILE.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        reader = csv.DictReader(file)

        required_columns = {
            "session_id",
            "assistant_message_index",
            "customer_message_index",
            "question_number_in_message",
            "questions_in_assistant_message",
            "question",
            "answer",
            "question_type",
            "pairing_confidence",
        }

        actual_columns = set(reader.fieldnames or [])
        missing_columns = required_columns - actual_columns

        if missing_columns:
            raise ValueError(
                "Input CSV is missing required columns: "
                + ", ".join(sorted(missing_columns))
            )

        rows = list(reader)

    # Count duplicate question-answer pairs within each session.
    pair_counts = Counter()

    for row in rows:
        key = (
            str(row.get("session_id", "")).strip(),
            clean_text(row.get("question")).casefold(),
            clean_text(row.get("answer")).casefold(),
        )
        pair_counts[key] += 1

    issues_count = Counter()
    report_rows = []

    for row in rows:
        question = clean_text(row.get("question"))
        answer = clean_text(row.get("answer"))
        question_type = clean_text(
            row.get("question_type")
        ).lower()

        # IMPORTANT: clean_text now preserves underscores.
        confidence = clean_text(
            row.get("pairing_confidence")
        ).lower()

        session_id = str(
            row.get("session_id", "")
        ).strip()

        questions_in_message = safe_int(
            row.get("questions_in_assistant_message")
        )

        issues = set()

        # 1. Question content checks.
        if is_placeholder(question):
            issues.add("empty_or_placeholder_question")

        if len(question) < 10:
            issues.add("question_too_short")

        if len(question) > 500:
            issues.add("question_unusually_long")

        # 2. Answer content checks.
        if is_placeholder(answer):
            issues.add("empty_or_placeholder_answer")

        if "[image attachment]" in answer.casefold():
            issues.add("answer_is_image_placeholder")

        if len(answer) > 2000:
            issues.add("answer_unusually_long")

        # 3. Question classification checks.
        if question_type in ("", "other"):
            issues.add("unclassified_question_type")

        if question_type == "quote_acceptance":
            issues.add("quote_acceptance_not_scope_question")

        # 4. Duplicate checks.
        pair_key = (
            session_id,
            question.casefold(),
            answer.casefold(),
        )

        if pair_counts[pair_key] > 1:
            issues.add("duplicate_pair_within_session")

        # 5. Compound-question review.
        if questions_in_message > 1:
            issues.add("multiple_questions_from_same_message")

        # 6. Pairing-confidence checks.
        if not confidence:
            issues.add("missing_pairing_confidence")

        elif confidence not in KNOWN_CONFIDENCES:
            issues.add("unknown_pairing_confidence")

        elif confidence == "ambiguous_multiple_questions":
            issues.add("ambiguous_question_answer_pairing")

        elif confidence == "sequence_based_not_verified":
            issues.add("sequence_pairing_not_verified")

        # 7. Separate content quality from pairing verification.
        content_issue_names = {
            "empty_or_placeholder_question",
            "empty_or_placeholder_answer",
            "question_too_short",
            "question_unusually_long",
            "answer_is_image_placeholder",
            "answer_unusually_long",
        }

        review_issue_names = {
            "ambiguous_question_answer_pairing",
            "sequence_pairing_not_verified",
            "multiple_questions_from_same_message",
            "duplicate_pair_within_session",
            "unclassified_question_type",
            "quote_acceptance_not_scope_question",
            "missing_pairing_confidence",
            "unknown_pairing_confidence",
        }

        content_issues = issues & content_issue_names
        review_issues = issues & review_issue_names

        report_row = dict(row)
        report_row["clean_question"] = question
        report_row["clean_answer"] = answer
        report_row["normalized_pairing_confidence"] = confidence
        report_row["validation_issues"] = ";".join(sorted(issues))
        report_row["content_issues"] = ";".join(
            sorted(content_issues)
        )
        report_row["review_issues"] = ";".join(
            sorted(review_issues)
        )

        report_row["passes_basic_content_checks"] = (
            len(content_issues) == 0
        )

        report_row["requires_pairing_review"] = (
            len(review_issues) > 0
        )

        # This is a screening result, not proof of semantic correctness.
        report_row["eligible_for_manual_review"] = (
            len(content_issues) == 0
            and confidence in KNOWN_CONFIDENCES
            and "quote_acceptance_not_scope_question" not in issues
        )

        for issue in issues:
            issues_count[issue] += 1

        report_rows.append(report_row)

    # Write detailed report.
    default_fields = [
        "session_id",
        "question",
        "answer",
        "question_type",
        "pairing_confidence",
        "validation_issues",
        "content_issues",
        "review_issues",
        "passes_basic_content_checks",
        "requires_pairing_review",
        "eligible_for_manual_review",
    ]

    fields = (
        list(report_rows[0].keys())
        if report_rows
        else default_fields
    )

    with DETAIL_REPORT.open(
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
        writer.writerows(report_rows)

    # Calculate separate content and pairing-review metrics.
    content_clean_count = sum(
        1
        for row in report_rows
        if row["passes_basic_content_checks"]
    )

    ambiguous_count = sum(
        1
        for row in report_rows
        if "ambiguous_question_answer_pairing"
        in split_issues(row["validation_issues"])
    )

    unverified_count = sum(
        1
        for row in report_rows
        if "sequence_pairing_not_verified"
        in split_issues(row["validation_issues"])
    )

    multiple_question_count = sum(
        1
        for row in report_rows
        if "multiple_questions_from_same_message"
        in split_issues(row["validation_issues"])
    )

    unknown_confidence_count = sum(
        1
        for row in report_rows
        if "unknown_pairing_confidence"
        in split_issues(row["validation_issues"])
    )

    manual_review_count = sum(
        1
        for row in report_rows
        if row["eligible_for_manual_review"]
    )

    review_required_count = sum(
        1
        for row in report_rows
        if row["requires_pairing_review"]
    )

    all_content_and_review_checks_count = sum(
        1
        for row in report_rows
        if row["passes_basic_content_checks"]
        and not row["requires_pairing_review"]
    )

    summary_rows = [
        {"metric": "pairs_checked", "value": len(rows)},
        {
            "metric": "pairs_with_basic_content_checks_passed",
            "value": content_clean_count,
        },
        {
            "metric": "pairs_with_content_issues",
            "value": len(rows) - content_clean_count,
        },
        {
            "metric": "ambiguous_pairs_requiring_review",
            "value": ambiguous_count,
        },
        {
            "metric": "sequence_pairs_not_verified",
            "value": unverified_count,
        },
        {
            "metric": "pairs_with_multiple_questions_in_message",
            "value": multiple_question_count,
        },
        {
            "metric": "pairs_with_unknown_confidence",
            "value": unknown_confidence_count,
        },
        {
            "metric": "pairs_requiring_pairing_review",
            "value": review_required_count,
        },
        {
            "metric": "pairs_eligible_for_manual_review",
            "value": manual_review_count,
        },
        {
            "metric": "pairs_passing_content_and_review_checks",
            "value": all_content_and_review_checks_count,
        },
    ]

    for issue, count in sorted(issues_count.items()):
        summary_rows.append({
            "metric": f"issue_{issue}",
            "value": count,
        })

    with SUMMARY_REPORT.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["metric", "value"],
        )
        writer.writeheader()
        writer.writerows(summary_rows)

    print("\nQuestion-and-answer validation completed.")
    print("Pairs checked:", len(rows))
    print("Pairs passing basic content checks:", content_clean_count)
    print("Pairs with content issues:", len(rows) - content_clean_count)
    print("Ambiguous pairs requiring review:", ambiguous_count)
    print("Sequence pairs not verified:", unverified_count)
    print("Pairs with multiple questions in one message:", multiple_question_count)
    print("Pairs with unknown confidence:", unknown_confidence_count)
    print("Pairs requiring pairing review:", review_required_count)
    print("Pairs eligible for manual review:", manual_review_count)
    print(
        "Pairs passing content and review checks:",
        all_content_and_review_checks_count,
    )

    print("\nIssue counts:")
    if issues_count:
        for issue, count in sorted(issues_count.items()):
            print(f"{issue}: {count}")
    else:
        print("No validation issues found.")

    print("\nDetailed report:", DETAIL_REPORT)
    print("Summary report:", SUMMARY_REPORT)

    print(
        "\nImportant: eligibility for manual review does not mean "
        "a question-answer pair is semantically correct or verified "
        "for training."
    )


if __name__ == "__main__":
    main()
