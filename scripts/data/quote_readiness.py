"""
Rule-based quote readiness assessment for Star Handyman.

This module decides whether a duration estimate can be shown as a preliminary
historical reference, more details should be requested, or manual review is
required. It does not calculate prices and does not create a customer quote.

Run smoke tests from the project root:
    python -m scripts.audit.test_quote_readiness
"""
import re
from typing import Any, Dict, Optional

COMPLEX_SCOPE_PATTERNS = [
    r"\b(200 amp|100 amp|150 amp|electrical panel|breaker panel|service panel)\b",
    r"\b(deck|balcony)\b.*\b(board|sq ft|square feet|pressure wash|powerwash|seal)\b",
    r"\b(multi visit|multiple visits|second visit|return visit|after it cures|cure time)\b",
    r"\b(whole house|entire house|multiple rooms|all bedroom walls|entire wall)\b",
    r"\b(structural|joists|framing|underlying structure)\b",
    r"\b(water heater|hot water tank)\b",
]

MISSING_SCOPE_PATTERNS = [
    r"\b(fix it|repair it|help me|not working|broken|problem|issue)\b",
]

def _normalise(value: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())).strip()

def _matches_any(text: str, patterns) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)

def assess_quote_readiness(
    estimate: Dict[str, Any],
    job_description: str,
    category_confirmed: bool = True,
    scope_details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Assess readiness using estimator output and available scope details.

    `scope_details` may contain keys such as:
      - size_or_quantity
      - access_confirmed
      - materials_known
      - multi_visit_known

    Values may be True/False/None. Missing values are treated as unknown,
    not as a confirmed problem. This function does not infer actual safety,
    trade licensing, or final price.
    """
    scope_details = scope_details or {}
    description = _normalise(job_description)
    category = estimate.get("category")
    support_count = int(estimate.get("support_count") or 0)
    estimator_review = bool(estimate.get("needs_scope_review"))
    estimate_method = str(estimate.get("estimate_method") or "")
    warning = estimate.get("warning")

    reasons = []
    missing_details = []

    if not category_confirmed or not category:
        reasons.append("category_unconfirmed")
        return {
            "decision": "manual_review_required",
            "can_show_preliminary_duration": False,
            "can_show_customer_quote": False,
            "reasons": reasons,
            "questions_to_ask": [
                "Which type of work best describes the job?",
                "What exactly needs to be repaired, installed, or replaced?",
            ],
            "duration_estimate_hours": estimate.get("estimated_hours"),
            "warning": "Confirm the job category and scope before presenting an estimate.",
        }

    if support_count < 5 or estimate_method == "global_median_fallback":
        reasons.append("insufficient_category_history")
        decision = "manual_review_required"
    else:
        decision = "estimate_available"

    if not description:
        reasons.append("job_description_missing")
        missing_details.append("job_description")
        decision = "ask_for_more_details"

    if _matches_any(description, COMPLEX_SCOPE_PATTERNS):
        reasons.append("possible_complex_scope")
        decision = "ask_for_more_details"

    if _matches_any(description, MISSING_SCOPE_PATTERNS):
        reasons.append("description_may_be_too_vague")
        missing_details.append("specific_problem_and_requested_work")
        decision = "ask_for_more_details"

    question_map = {
        "job_description": "What exactly needs to be repaired, installed, or replaced?",
        "specific_problem_and_requested_work": "What is happening now, and what outcome do you want?",
        "size_or_quantity": "What are the approximate dimensions or how many items are involved?",
        "access_confirmed": "Are there any access constraints, height concerns, or difficult-to-reach areas?",
        "materials_known": "Are the required materials supplied by you, or should the tasker supply them?",
        "multi_visit_known": "Does the work need more than one visit, for example for curing, drying, or follow-up work?",
    }

    # Ask targeted questions only when relevant or explicitly unknown.
    if "possible_complex_scope" in reasons:
        for key in ("size_or_quantity", "access_confirmed", "materials_known", "multi_visit_known"):
            if scope_details.get(key) is not True:
                missing_details.append(key)

    questions = []
    for key in missing_details:
        question = question_map.get(key)
        if question and question not in questions:
            questions.append(question)

    if estimator_review and decision == "estimate_available":
        reasons.append("estimator_requested_scope_review")
        decision = "ask_for_more_details"

    if decision == "manual_review_required":
        customer_warning = (
            "There is not enough category-specific history to support an automatic estimate. "
            "Review the scope or use an approved business fallback."
        )
    elif decision == "ask_for_more_details":
        customer_warning = (
            "The duration is only a preliminary historical reference. Confirm the job scope "
            "before using it to prepare a quote."
        )
    else:
        customer_warning = (
            "This is a preliminary duration reference based on historical quoted hours, "
            "not a guaranteed completion time or a final price."
        )

    return {
        "decision": decision,
        "can_show_preliminary_duration": decision == "estimate_available",
        "can_show_customer_quote": False,
        "reasons": list(dict.fromkeys(reasons)),
        "questions_to_ask": questions,
        "missing_scope_details": list(dict.fromkeys(missing_details)),
        "duration_estimate_hours": estimate.get("estimated_hours"),
        "support_count": support_count,
        "support_level": estimate.get("support_level"),
        "warning": customer_warning,
        "estimator_warning": warning,
    }
