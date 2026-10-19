"""Smoke tests for quote_readiness.py.
Run from project root: python -m scripts.audit.test_quote_readiness
"""
from scripts.data.duration_estimator_service import estimate_duration
from scripts.data.quote_readiness import assess_quote_readiness

def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print(f"PASS: {message}")

def main():
    plumbing = estimate_duration("1", "Replace a leaking faucet")
    result = assess_quote_readiness(plumbing, "Replace a leaking faucet")
    check(result["decision"] == "estimate_available", "ordinary supported plumbing job allows preliminary duration")
    check(result["can_show_preliminary_duration"] is True, "preliminary duration flag is true")
    check(result["can_show_customer_quote"] is False, "module never approves a final customer quote")

    panel = estimate_duration("4", "Replace a 200 amp electrical panel")
    result = assess_quote_readiness(panel, "Replace a 200 amp electrical panel")
    check(result["decision"] == "ask_for_more_details", "complex panel work asks for more details")
    check(len(result["questions_to_ask"]) > 0, "complex scope returns follow-up questions")

    hvac = estimate_duration("7", "Inspect HVAC system")
    result = assess_quote_readiness(hvac, "Inspect HVAC system")
    check(result["decision"] == "manual_review_required", "insufficient category history requires review")

    unknown = estimate_duration("999", "General repair")
    result = assess_quote_readiness(unknown, "General repair", category_confirmed=False)
    check(result["decision"] == "manual_review_required", "unknown category requires manual review")
    check(result["can_show_preliminary_duration"] is False, "unknown category cannot show preliminary duration")

    vague = assess_quote_readiness(plumbing, "It is broken and not working")
    check(vague["decision"] == "ask_for_more_details", "vague description requests clarification")
    check(len(vague["questions_to_ask"]) > 0, "vague description provides a follow-up question")

    print("\nAll quote readiness tests passed.")

if __name__ == "__main__":
    main()
