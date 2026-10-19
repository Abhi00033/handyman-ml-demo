import csv
import re
from pathlib import Path

# Categories with fewer than this many historical records require review.
MIN_CATEGORY_SAMPLES = 5

# This prototype is not approved for production customer estimates.
PRODUCTION_READY = False


def _project_root():
    """Return the project root directory."""
    return Path(__file__).resolve().parents[2]


def load_duration_baseline():
    """Read the automatically generated historical duration baseline."""
    baseline_path = (
        _project_root()
        / "datasets"
        / "prepared"
        / "automatically_clean_duration_baseline.csv"
    )

    if not baseline_path.exists():
        raise FileNotFoundError(
            f"Duration baseline not found: {baseline_path}\n"
            "Run the automatic duration pipeline first."
        )

    with baseline_path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))

    if not rows:
        raise ValueError(f"The duration baseline is empty: {baseline_path}")

    return rows


def _get_value(row, *possible_names):
    """Return the first non-empty value matching a column alias."""
    normalized_row = {
        str(key).strip().lower(): value
        for key, value in row.items()
        if key is not None
    }
    for name in possible_names:
        value = normalized_row.get(name.lower())
        if value is not None and str(value).strip() != "":
            return value
    return None


def _normalize_category_id(value):
    """Normalize IDs such as 1, '1', and '1.0' consistently."""
    if value is None:
        return None
    value = str(value).strip()
    if not value:
        return None
    try:
        numeric_value = float(value)
        if numeric_value.is_integer():
            return str(int(numeric_value))
    except (ValueError, TypeError):
        pass
    return value


def _to_float(value):
    """Convert a valid finite numeric value to float; otherwise return None."""
    if value is None:
        return None
    try:
        number = float(str(value).strip())
        if number != number or number in (float("inf"), float("-inf")):
            return None
        return number
    except (ValueError, TypeError):
        return None


def _to_int(value):
    """Convert a valid non-negative count to int; otherwise return zero."""
    number = _to_float(value)
    if number is None or number < 0:
        return 0
    return int(number)


def _complex_scope_reasons(description):
    """Return conservative text flags that require scope clarification.

    These keyword rules are static heuristics, not a technical or safety
    assessment of the work. They deliberately favour manual review over a
    potentially misleading automatic duration estimate.
    """
    patterns = {
        "electrical_panel": (
            r"\b(?:electrical|breaker|circuit)\s+panel\b"
            r"|\b200\s*[- ]?amp\b"
            r"|\bpanel\s+(?:upgrade|replacement|replace)\b"
        ),
        "large_or_extensive_work": (
            r"\bwhole\s+house\b"
            r"|\bmultiple\s+rooms?\b"
            r"|\bextensive\b"
            r"|\bmajor\s+repair\b"
            r"|\bstructural\b"
        ),
        "deck_or_large_outdoor_work": r"\bdeck\b|\bporch\b|\bbalcony\b",
        "multiple_visits": (
            r"\bmulti[- ]visit\b"
            r"|\bmore\s+than\s+one\s+visit\b"
            r"|\bmultiple\s+visits\b"
            r"|\bcuring\b"
            r"|\bdrying\s+time\b"
        ),
    }
    return [
        reason
        for reason, pattern in patterns.items()
        if re.search(pattern, description, re.IGNORECASE)
    ]


def _review_result(
    category_id,
    category,
    support_count,
    support_level,
    method,
    reasons,
    warning,
):
    """Build a consistent non-automatic result that requires review."""
    return {
        "estimated_hours": None,
        "category_id": category_id,
        "category": category,
        "support_count": support_count,
        "support_level": support_level,
        "estimate_method": method,
        "needs_scope_review": True,
        "scope_review_reasons": reasons,
        "warning": warning,
        "is_production_ready": PRODUCTION_READY,
    }


def estimate_duration(category_id, job_description="", use_conservative_p75=False):
    """Estimate duration from the refreshed category baseline.

    Returns a numeric preliminary estimate only when the category has enough
    historical support and the description does not match a complex-scope
    review rule. This prototype never calculates prices or final quotes.
    """
    normalized_id = _normalize_category_id(category_id)
    description = str(job_description or "").strip()

    if normalized_id is None:
        return _review_result(
            None, None, 0, "unknown", "no_category_baseline", ["category_missing"],
            "The job category is missing. Confirm the category and review the "
            "job scope before estimating duration.",
        )

    baseline_rows = load_duration_baseline()
    matching_row = None
    for row in baseline_rows:
        row_id = _normalize_category_id(
            _get_value(row, "category_id", "detected_category_id")
        )
        if row_id == normalized_id:
            matching_row = row
            break

    if matching_row is None:
        return _review_result(
            normalized_id, None, 0, "unknown", "no_category_baseline",
            ["category_baseline_missing"],
            "No category-specific duration baseline is available. Confirm the "
            "category and review the job scope.",
        )

    category_name = _get_value(
        matching_row, "category", "detected_category", "category_name"
    )
    support_count = _to_int(
        _get_value(matching_row, "count", "sample_count", "support_count", "n")
    )
    median_hours = _to_float(
        _get_value(matching_row, "median_hours", "median", "median_estimated_hours")
    )
    p75_hours = _to_float(
        _get_value(matching_row, "p75_hours", "p75", "p75_estimated_hours")
    )
    scope_reasons = _complex_scope_reasons(description)

    if support_count < MIN_CATEGORY_SAMPLES or median_hours is None or median_hours <= 0:
        return _review_result(
            normalized_id, category_name, support_count, "insufficient",
            "insufficient_category_history",
            scope_reasons or ["insufficient_category_history"],
            "There is not enough valid category-specific history to support an "
            "automatic duration estimate. Review the job scope.",
        )

    if support_count >= 30:
        support_level = "higher_support"
    elif support_count >= 10:
        support_level = "moderate_support"
    else:
        support_level = "limited_support"

    # Important: don't return a broad category median for flagged complex work.
    if scope_reasons:
        return _review_result(
            normalized_id, category_name, support_count, support_level,
            "scope_review_required", scope_reasons,
            "The job description matches a complex-scope rule. A broad category "
            "median may be misleading. Review the specific work and comparable "
            "historical jobs before estimating duration.",
        )

    if use_conservative_p75 and p75_hours is not None and p75_hours > 0:
        estimated_hours = p75_hours
        estimate_method = "category_p75"
    else:
        estimated_hours = median_hours
        estimate_method = "category_median"

    return {
        "estimated_hours": round(estimated_hours, 2),
        "category_id": normalized_id,
        "category": category_name,
        "support_count": support_count,
        "support_level": support_level,
        "estimate_method": estimate_method,
        "needs_scope_review": False,
        "scope_review_reasons": [],
        "warning": (
            "This is a preliminary reference based on historical quoted hours, "
            "not a guaranteed completion time or final price."
        ),
        "is_production_ready": PRODUCTION_READY,
    }


def main():
    """Run basic smoke tests against the current baseline."""
    test_cases = [
        ("1", "Replace a leaking faucet"),
        ("4", "Replace a 200 amp electrical panel"),
        ("7", "Inspect HVAC system"),
        ("999", "General repair"),
        (None, "Repair an unknown issue"),
    ]
    for category_id, description in test_cases:
        result = estimate_duration(category_id, description)
        print("\n" + "=" * 60)
        print(f"Description: {description}")
        for key, value in result.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
