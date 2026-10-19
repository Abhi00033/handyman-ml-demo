
import csv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]

CANDIDATES_FILE = (
    BASE_DIR
    / "datasets"
    / "prepared"
    / "refined_question_answer_candidates.csv"
)

DISPOSITIONS_FILE = (
    BASE_DIR
    / "datasets"
    / "reports"
    / "question_answer_review_dispositions.csv"
)

OUTPUT_DIR = BASE_DIR / "datasets" / "prepared"
REPORT_DIR = BASE_DIR / "datasets" / "reports"

ELIGIBLE_FILE = OUTPUT_DIR / "unverified_qa_candidates.csv"
MANUAL_REVIEW_FILE = OUTPUT_DIR / "qa_manual_review.csv"
EXCLUDED_FILE = OUTPUT_DIR / "qa_excluded_from_job_scope.csv"
SUMMARY_FILE = REPORT_DIR / "controlled_qa_dataset_summary.csv"


def read_csv(path):
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")

    with path.open("r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        rows = list(reader)
        fields = list(dict.fromkeys(reader.fieldnames or []))

    return rows, fields


def write_csv(path, rows, fields):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fields,
            extrasaction="ignore",
        )
        writer.writeheader()
        writer.writerows(rows)


def main():
    candidates, candidate_fields = read_csv(CANDIDATES_FILE)
    dispositions, disposition_fields = read_csv(DISPOSITIONS_FILE)

    required = {"session_id", "question", "answer"}
    missing = required - set(candidate_fields)

    if missing:
        raise ValueError(
            f"Candidate dataset is missing columns: {sorted(missing)}"
        )

    # Match records by session and occurrence, preserving file order.
    def add_occurrences(rows):
        counts = {}
        result = []

        for row in rows:
            session_id = str(row.get("session_id", "")).strip()
            counts[session_id] = counts.get(session_id, 0) + 1

            result.append({
                **row,
                "_session_occurrence": str(counts[session_id]),
            })

        return result

    candidate_indexed = add_occurrences(candidates)
    disposition_indexed = add_occurrences(dispositions)

    decisions = {}

    for row in disposition_indexed:
        key = (row["session_id"].strip(), row["_session_occurrence"])

        if key in decisions:
            raise ValueError(
                f"Duplicate disposition key detected: {key}"
            )

        decisions[key] = row

    eligible = []
    manual_review = []
    excluded = []
    unmatched_dispositions = []

    for row in candidate_indexed:
        key = (row["session_id"].strip(), row["_session_occurrence"])
        disposition = decisions.get(key)

        output_row = {
            field: row.get(field, "")
            for field in candidate_fields
        }

        # Never promote unverified pairs to verified training labels.
        output_row["verified_for_training"] = "False"

        if disposition:
            decision = disposition.get("review_disposition", "")

            if decision == "exclude_from_job_scope_qa":
                excluded.append(output_row)
                continue

            if decision == "manual_review":
                output_row["review_disposition"] = "manual_review"
                output_row["disposition_reason"] = disposition.get(
                    "disposition_reason", ""
                )
                manual_review.append(output_row)
                continue

        output_row["review_disposition"] = "unreviewed_candidate"
        output_row["disposition_reason"] = (
            "Not individually verified; requires validation before training."
        )
        eligible.append(output_row)

    candidate_keys = {
        (row["session_id"].strip(), row["_session_occurrence"])
        for row in candidate_indexed
    }

    for row in disposition_indexed:
        key = (row["session_id"].strip(), row["_session_occurrence"])

        if key not in candidate_keys:
            unmatched_dispositions.append(key)

    output_fields = list(dict.fromkeys(
        candidate_fields + ["review_disposition", "disposition_reason"]
    ))

    write_csv(ELIGIBLE_FILE, eligible, output_fields)
    write_csv(MANUAL_REVIEW_FILE, manual_review, output_fields)
    write_csv(EXCLUDED_FILE, excluded, output_fields)

    summary = [
        {
            "dataset": "input_candidates",
            "records": len(candidates),
            "verified_for_training": 0,
        },
        {
            "dataset": "unverified_qa_candidates",
            "records": len(eligible),
            "verified_for_training": 0,
        },
        {
            "dataset": "qa_manual_review",
            "records": len(manual_review),
            "verified_for_training": 0,
        },
        {
            "dataset": "qa_excluded_from_job_scope",
            "records": len(excluded),
            "verified_for_training": 0,
        },
    ]

    write_csv(
        SUMMARY_FILE,
        summary,
        ["dataset", "records", "verified_for_training"],
    )

    print("Controlled Q&A dataset build complete.")
    print(f"Input candidates: {len(candidates)}")
    print(f"Unverified candidates: {len(eligible)}")
    print(f"Manual review: {len(manual_review)}")
    print(f"Excluded: {len(excluded)}")
    print(f"Unmatched dispositions: {len(unmatched_dispositions)}")

    if unmatched_dispositions:
        print(
            "WARNING: Some reviewed records did not match candidate records."
        )
        for key in unmatched_dispositions:
            print(f"  {key}")

    if len(candidates) != len(eligible) + len(manual_review) + len(excluded):
        print(
            "WARNING: Output counts do not reconcile with the input count."
        )

    print("\nDatabase was not accessed or modified.")


if __name__ == "__main__":
    main()
