
import csv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    BASE_DIR
    / "datasets"
    / "reports"
    / "refined_question_answer_review.csv"
)

OUTPUT_FILE = (
    BASE_DIR
    / "datasets"
    / "reports"
    / "question_answer_review_dispositions.csv"
)

# Provisional review decisions, not verified training labels.
DECISIONS = {
    ("86", "1"): (
        "manual_review",
        "Yes does not distinguish wall mounting from ceiling mounting."
    ),
    ("88", "1"): (
        "manual_review",
        "Yes does not identify the intended mounting wall."
    ),
    ("92", "1"): (
        "manual_review",
        "Yes does not identify the intended outlet arrangement."
    ),
    ("140", "1"): (
        "exclude_from_job_scope_qa",
        "Conversation or next-step question, not job-scope clarification."
    ),
    ("158", "1"): (
        "manual_review",
        "Yes does not select clear sealant or stain."
    ),
    ("168", "1"): (
        "manual_review",
        "Yes sure does not identify battery-powered versus wired."
    ),
    ("169", "1"): (
        "manual_review",
        "Yes does not select repair versus replacement."
    ),
    ("169", "2"): (
        "manual_review",
        "Yes does not select option A or B."
    ),
    ("169", "3"): (
        "manual_review",
        "Yes does not select repair versus replacement."
    ),
    ("169", "4"): (
        "manual_review",
        "Yes does not select manual versus smart thermostat."
    ),
    ("201", "1"): (
        "exclude_from_job_scope_qa",
        "Estimate acceptance or adjustment question, not job-scope clarification."
    ),
    ("219", "1"): (
        "manual_review",
        "Yes does not specify the finish or on-site matching preference."
    ),
    ("222", "1"): (
        "manual_review",
        "Yes does not clearly confirm the intended repair scope."
    ),
    ("228", "1"): (
        "manual_review",
        "Yes does not clearly identify who will supply the paint."
    ),
    ("230", "1"): (
        "manual_review",
        "Yes does not clearly identify who will supply the paint."
    ),
    ("230", "2"): (
        "manual_review",
        "Yes does not clearly identify who will supply the paint."
    ),
    ("232", "1"): (
        "manual_review",
        "No does not unambiguously resolve the preparation question."
    ),
    ("232", "2"): (
        "manual_review",
        "Yes does not clearly identify who will supply the paint."
    ),
    ("234", "1"): (
        "manual_review",
        "Yes does not clearly identify who will supply the caulk."
    ),
    ("242", "1"): (
        "manual_review",
        "Yes does not clearly identify who will supply the fixture."
    ),
}


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Review input not found: {INPUT_FILE}"
        )

    with INPUT_FILE.open(
        "r", newline="", encoding="utf-8-sig"
    ) as file:
        reader = csv.DictReader(file)
        rows = list(reader)
        fields = reader.fieldnames or []

    required = {
        "session_id",
        "question",
        "answer",
        "review_flags",
    }

    missing = required.difference(fields)
    if missing:
        raise ValueError(
            f"Input is missing required columns: {sorted(missing)}"
        )

    # Remove duplicate header names while preserving their original order.
    fields = list(dict.fromkeys(fields))

    occurrence_counts = {}
    output_rows = []
    unmatched = []

    for row in rows:
        session_id = str(row.get("session_id", "")).strip()

        occurrence_counts[session_id] = (
            occurrence_counts.get(session_id, 0) + 1
        )

        occurrence = occurrence_counts[session_id]
        key = (session_id, str(occurrence))

        decision, reason = DECISIONS.get(
            key,
            (
                "manual_review",
                "No explicit disposition supplied; manual review required."
            ),
        )

        # Preserve existing fields, updating rather than duplicating columns.
        output_row = dict(row)
        output_row["review_disposition"] = decision
        output_row["disposition_reason"] = reason
        output_row["verified_for_training"] = "False"

        output_rows.append(output_row)

        if key not in DECISIONS:
            unmatched.append(key)

    # Include each output column exactly once.
    output_fields = list(dict.fromkeys(
        fields + [
            "review_disposition",
            "disposition_reason",
            "verified_for_training",
        ]
    ))

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_FILE.open(
        "w", newline="", encoding="utf-8-sig"
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=output_fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(output_rows)

    print("Review disposition file created.")
    print(f"Input records: {len(rows)}")
    print(f"Output records: {len(output_rows)}")
    print(f"Output: {OUTPUT_FILE}")
    print("\nDisposition counts:")

    counts = {}
    for row in output_rows:
        decision = row["review_disposition"]
        counts[decision] = counts.get(decision, 0) + 1

    for decision, count in sorted(counts.items()):
        print(f"{decision}: {count}")

    if unmatched:
        print("\nRecords without explicit decisions:")
        for key in unmatched:
            print(key)

    print("\nNo database records were modified.")
    print("No records were marked as verified for training.")


if __name__ == "__main__":
    main()
