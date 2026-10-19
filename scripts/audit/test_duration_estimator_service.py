from scripts.data.duration_estimator_service import estimate_duration


def check(condition, message):
    if not condition:
        raise AssertionError(message)

    print(f"PASS: {message}")


def main():
    # Test 1: Supported Plumbing category
    plumbing = estimate_duration("1", "Replace a leaking faucet")

    check(
        plumbing["estimated_hours"] is not None
        and plumbing["estimated_hours"] > 0,
        "known category returns positive hours",
    )

    check(
        plumbing["category"] == "Plumbing",
        "known category resolves to Plumbing",
    )

    check(
        plumbing["support_count"] >= 5,
        "Plumbing has sufficient historical support",
    )

    check(
        plumbing["estimate_method"] == "category_median",
        "supported category uses category median",
    )

    check(
        plumbing["needs_scope_review"] is False,
        "ordinary faucet task does not trigger complexity review",
    )

    # Test 2: Complex electrical work
    electrical = estimate_duration(
        "4",
        "Replace a 200 amp electrical panel",
    )

    check(
        electrical["needs_scope_review"] is True,
        "electrical panel triggers scope review",
    )

    check(
        bool(electrical["warning"]),
        "scope review includes a warning",
    )

    # Test 3: HVAC has insufficient historical support
    hvac = estimate_duration("7", "Inspect HVAC system")

    check(
        hvac["estimated_hours"] is None,
        "low-support category does not return a numeric estimate",
    )

    check(
        hvac["estimate_method"] == "insufficient_category_history",
        "low-support category requires historical-data review",
    )

    check(
        hvac["needs_scope_review"] is True,
        "low-support category requires scope review",
    )

    # Test 4: Unknown category
    unknown = estimate_duration("999", "General repair")

    check(
        unknown["estimated_hours"] is None,
        "unknown category does not return a numeric estimate",
    )

    check(
        unknown["estimate_method"] == "no_category_baseline",
        "unknown category has no category-specific baseline",
    )

    check(
        unknown["needs_scope_review"] is True,
        "unknown category requires review",
    )

    # Test 5: Missing category
    missing = estimate_duration(None, "Repair an unknown issue")

    check(
        missing["estimated_hours"] is None,
        "missing category does not return a numeric estimate",
    )

    check(
        missing["needs_scope_review"] is True,
        "missing category requires review",
    )

    # Test 6: Estimates must not be marked production-ready
    for result in (plumbing, electrical, hvac, unknown, missing):
        check(
            result["is_production_ready"] is False,
            "prototype estimate is not marked production-ready",
        )

    print("\nAll duration estimator tests passed.")


if __name__ == "__main__":
    main()