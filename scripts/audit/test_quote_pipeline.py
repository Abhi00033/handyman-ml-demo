from scripts.data.duration_estimator_service import estimate_duration
from scripts.data.quote_readiness import assess_quote_readiness


def run_case(category_id, description, category_confirmed=True):
    estimate = estimate_duration(category_id, description)

    readiness = assess_quote_readiness(
        estimate,
        description,
        category_confirmed=category_confirmed,
    )

    return {
        "description": description,
        "estimated_hours": estimate["estimated_hours"],
        "estimate_method": estimate["estimate_method"],
        "decision": readiness["decision"],
        "can_show_preliminary_duration": readiness[
            "can_show_preliminary_duration"
        ],
        "can_show_customer_quote": readiness[
            "can_show_customer_quote"
        ],
        "questions": readiness["questions_to_ask"],
        "warnings": readiness["warning"],
    }


def main():
    cases = [
        {
            "category_id": "1",
            "description": "Replace a leaking faucet",
            "category_confirmed": True,
            "expected_decision": "estimate_available",
            "expected_numeric_estimate": True,
        },
        {
            "category_id": "4",
            "description": "Replace a 200 amp electrical panel",
            "category_confirmed": True,
            "expected_decision": "ask_for_more_details",
            "expected_numeric_estimate": False,
        },
        {
            "category_id": "7",
            "description": "Inspect HVAC system",
            "category_confirmed": True,
            "expected_decision": "manual_review_required",
            "expected_numeric_estimate": False,
        },
        {
            "category_id": "999",
            "description": "General repair",
            "category_confirmed": False,
            "expected_decision": "manual_review_required",
            "expected_numeric_estimate": False,
        },
    ]

    for case in cases:
        result = run_case(
            category_id=case["category_id"],
            description=case["description"],
            category_confirmed=case["category_confirmed"],
        )

        print("\n" + "=" * 60)

        for key, value in result.items():
            print(f"{key}: {value}")

        # Never allow this prototype to produce a customer quote.
        assert result["can_show_customer_quote"] is False, (
            f"Customer quote unexpectedly enabled for: "
            f"{case['description']}"
        )

        # Check the readiness decision.
        assert result["decision"] == case["expected_decision"], (
            f"Unexpected decision for: {case['description']}. "
            f"Expected {case['expected_decision']}, "
            f"got {result['decision']}"
        )

        # Verify whether a numeric duration should be returned.
        has_numeric_estimate = result["estimated_hours"] is not None

        assert has_numeric_estimate == case["expected_numeric_estimate"], (
            f"Unexpected estimated_hours for: {case['description']}. "
            f"Expected numeric estimate: "
            f"{case['expected_numeric_estimate']}, "
            f"got: {result['estimated_hours']}"
        )

        # Confirm the estimate is never shown when readiness blocks it.
        if result["decision"] != "estimate_available":
            assert result["can_show_preliminary_duration"] is False, (
                f"Preliminary duration should be blocked for: "
                f"{case['description']}"
            )

    print("\nPipeline integration smoke test passed.")


if __name__ == "__main__":
    main()