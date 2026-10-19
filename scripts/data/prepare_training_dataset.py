
import csv
from pathlib import Path
from collections import Counter


BASE_DIR = Path(__file__).resolve().parents[2]
DATASET_DIR = BASE_DIR / "datasets"

QUOTE_AUDIT = DATASET_DIR / "quote_label_audit.csv"
IMAGE_MANIFEST = DATASET_DIR / "image_download_manifest.csv"
IMAGE_VALIDATION = DATASET_DIR / "image_validation_report.csv"

OUTPUT_ALL = DATASET_DIR / "training_candidates.csv"
OUTPUT_REVIEW = DATASET_DIR / "training_candidates_for_review.csv"


def read_csv(path):
    if not path.is_file():
        raise FileNotFoundError(
            f"Required file not found: {path}\n"
            "Run the earlier audit, download, and validation scripts first."
        )

    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def to_float(value):
    try:
        if value is None or str(value).strip() == "":
            return None
        number = float(value)
        return number if number >= 0 else None
    except (TypeError, ValueError):
        return None


def is_true(value):
    return str(value).strip().lower() in {"true", "1", "yes"}


def main():
    quotes = read_csv(QUOTE_AUDIT)
    manifest = read_csv(IMAGE_MANIFEST)
    validation = read_csv(IMAGE_VALIDATION)

    quote_by_id = {
        str(row["session_id"]).strip(): row
        for row in quotes
    }

    valid_image_ids = {
        str(row["image_id"]).strip()
        for row in validation
        if row.get("validation_status") == "valid"
    }

    output_rows = []
    review_rows = []
    reasons = Counter()

    for image in manifest:
        image_id = str(image.get("image_id", "")).strip()
        session_id = str(image.get("session_id", "")).strip()

        quote = quote_by_id.get(session_id)

        if quote is None:
            reasons["missing_quote_session"] += 1
            continue

        category = (quote.get("detected_category") or "").strip()
        hours = to_float(quote.get("estimated_hours"))
        price = to_float(quote.get("estimated_price"))

        status = (quote.get("status") or "").strip().lower()
        review_group = quote.get("review_group", "")

        image_is_valid = (
            image_id in valid_image_ids
            and image.get("disk") == "s3"
            and image.get("status") in {
                "downloaded",
                "already_downloaded",
            }
        )

        # Statuses are a preliminary filter, not proof of quote accuracy.
        status_candidate = review_group == "potentially_completed"

        has_category = bool(category)
        has_hours = hours is not None
        has_price = price is not None

        # Require all labels for the full quote-estimation candidate set.
        full_candidate = (
            image_is_valid
            and status_candidate
            and has_category
            and has_hours
            and has_price
        )

        if not image_is_valid:
            reasons["image_not_validated"] += 1

        if not status_candidate:
            reasons["status_not_in_potentially_completed_group"] += 1

        if not has_category:
            reasons["missing_category"] += 1

        if not has_hours:
            reasons["missing_hours"] += 1

        if not has_price:
            reasons["missing_price"] += 1

        row = {
            "image_id": image_id,
            "session_id": session_id,
            "image_path": image.get("local_path", ""),
            "s3_key": image.get("s3_key", ""),
            "image_validation_status": (
                "valid" if image_is_valid else "not_validated"
            ),
            "quote_status": status,
            "review_group": review_group,
            "detected_category": category,
            "task_level": quote.get("task_level", ""),
            "estimated_hours": hours if hours is not None else "",
            "estimated_price": price if price is not None else "",
            "estimated_price_min": quote.get("estimated_price_min", ""),
            "estimated_price_max": quote.get("estimated_price_max", ""),
            "estimated_total": quote.get("estimated_total", ""),
            "final_quote_valid": quote.get("final_quote_valid", ""),
            "final_quote_has_hours": quote.get("final_quote_has_hours", ""),
            "final_quote_has_projects": quote.get(
                "final_quote_has_projects", ""
            ),
            "candidate_for_full_quote_training": full_candidate,
            "requires_human_review": True,
        }

        output_rows.append(row)

        if full_candidate:
            review_rows.append(row)

    columns = [
        "image_id",
        "session_id",
        "image_path",
        "s3_key",
        "image_validation_status",
        "quote_status",
        "review_group",
        "detected_category",
        "task_level",
        "estimated_hours",
        "estimated_price",
        "estimated_price_min",
        "estimated_price_max",
        "estimated_total",
        "final_quote_valid",
        "final_quote_has_hours",
        "final_quote_has_projects",
        "candidate_for_full_quote_training",
        "requires_human_review",
    ]

    for path, rows in (
        (OUTPUT_ALL, output_rows),
        (OUTPUT_REVIEW, review_rows),
    ):
        with path.open("w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)

    print("\nTRAINING DATASET PREPARATION")
    print("=" * 40)
    print("S3 manifest records:", len(manifest))
    print("Rows matched to quote sessions:", len(output_rows))
    print("Full quote candidates for manual review:", len(review_rows))

    print("\nCandidate counts by category:")
    category_counts = Counter(
        row["detected_category"] for row in review_rows
    )

    for category, count in sorted(category_counts.items()):
        print(f"  {category}: {count}")

    print("\nReview flags:")
    for reason, count in sorted(reasons.items()):
        print(f"  {reason}: {count}")

    print("\nAll matched image records:", OUTPUT_ALL)
    print("Full quote review candidates:", OUTPUT_REVIEW)
    print("\nNo database records were modified.")
    print("Candidates still require human verification.")


if __name__ == "__main__":
    main()
