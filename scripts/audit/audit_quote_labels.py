
import csv
import json
from pathlib import Path
from collections import Counter

from db import get_connection


BASE_DIR = Path(__file__).resolve().parents[2]
DATASET_DIR = BASE_DIR / "datasets"
OUTPUT_FILE = DATASET_DIR / "quote_label_audit.csv"

# These are review groups, not automatic proof of correctness.
REVIEW_GROUPS = {
    "potentially_completed": {"confirmed", "approved", "appointed"},
    "quote_in_progress": {"quoted", "matched"},
    "needs_review": {
        "questioning",
        "draft",
        "address_required",
        "pending_schedule",
        "scope_review",
    },
    "exclude_deleted_or_rejected": {"deleted", "rejected"},
}


def to_number(value):
    if value is None or value == "":
        return None

    try:
        number = float(value)
        return number if number >= 0 else None
    except (TypeError, ValueError):
        return None


def review_group(status):
    status = (status or "").strip().lower()

    for group, statuses in REVIEW_GROUPS.items():
        if status in statuses:
            return group

    return "unknown_status"


def main():
    DATASET_DIR.mkdir(parents=True, exist_ok=True)
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
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
                    service_fee,
                    hst,
                    final_quote
                FROM quote_sessions
                ORDER BY id
            """)

            sessions = cursor.fetchall()

    finally:
        connection.close()

    output_rows = []
    group_counts = Counter()
    issue_counts = Counter()

    for session in sessions:
        status = session.get("status") or ""
        group = review_group(status)
        group_counts[group] += 1

        hours = to_number(session.get("estimated_hours"))
        price = to_number(session.get("estimated_price"))
        price_min = to_number(session.get("estimated_price_min"))
        price_max = to_number(session.get("estimated_price_max"))

        category = (
            session.get("detected_category") or ""
        ).strip()

        final_quote = session.get("final_quote")
        final_quote_valid = False
        final_quote_has_hours = False
        final_quote_has_projects = False

        if final_quote:
            try:
                parsed = (
                    final_quote
                    if isinstance(final_quote, dict)
                    else json.loads(final_quote)
                )

                if isinstance(parsed, dict):
                    final_quote_valid = True
                    final_quote_has_hours = (
                        to_number(parsed.get("total_hours")) is not None
                    )
                    final_quote_has_projects = bool(parsed.get("projects"))

            except (TypeError, ValueError, json.JSONDecodeError):
                pass

        issues = []

        if not category:
            issues.append("missing_category")

        if hours is None:
            issues.append("missing_or_invalid_hours")

        if price is None:
            issues.append("missing_or_invalid_price")

        if price_min is not None and price_max is not None:
            if price_min > price_max:
                issues.append("price_min_greater_than_max")

        if group == "exclude_deleted_or_rejected":
            issues.append("deleted_or_rejected_status")

        if group == "needs_review":
            issues.append("status_needs_review")

        if group == "unknown_status":
            issues.append("unknown_status")

        for issue in set(issues):
            issue_counts[issue] += 1

        output_rows.append({
            "session_id": session["id"],
            "status": status,
            "review_group": group,
            "detected_category": category,
            "category_id": session.get("category_id"),
            "task_level": session.get("task_level"),
            "task_level_id": session.get("task_level_id"),
            "estimated_hours": hours,
            "estimated_price": price,
            "estimated_price_min": price_min,
            "estimated_price_max": price_max,
            "estimated_total": to_number(session.get("estimated_total")),
            "estimated_total_min": to_number(session.get("estimated_total_min")),
            "estimated_total_max": to_number(session.get("estimated_total_max")),
            "service_fee": to_number(session.get("service_fee")),
            "hst": to_number(session.get("hst")),
            "final_quote_valid": final_quote_valid,
            "final_quote_has_hours": final_quote_has_hours,
            "final_quote_has_projects": final_quote_has_projects,
            "issues": ";".join(sorted(set(issues))),
        })

    columns = list(output_rows[0].keys()) if output_rows else []

    with OUTPUT_FILE.open(
        "w", newline="", encoding="utf-8-sig"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(output_rows)

    print("\nSTAR HANDYMAN QUOTE LABEL AUDIT")
    print("=" * 40)
    print("Total sessions:", len(sessions))

    print("\nReview groups:")
    for name, count in sorted(group_counts.items()):
        print(f"  {name}: {count}")

    print("\nPotential data issues:")
    for name, count in sorted(issue_counts.items()):
        print(f"  {name}: {count}")

    print("\nReport saved to:", OUTPUT_FILE)
    print("No database records were modified.")
    print(
        "\nNote: review groups are preliminary. "
        "They do not establish that a quote is accurate."
    )


if __name__ == "__main__":
    main()
