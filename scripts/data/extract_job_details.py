import csv
import json
import re
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]

INPUT_FILE = (
    BASE_DIR
    / "datasets"
    / "prepared"
    / "job_scope_records.csv"
)

OUTPUT_DIR = BASE_DIR / "datasets" / "prepared"
REPORT_DIR = BASE_DIR / "datasets" / "reports"

OUTPUT_FILE = OUTPUT_DIR / "structured_job_details.csv"
SUMMARY_FILE = REPORT_DIR / "job_detail_extraction_summary.csv"


PLACEHOLDER_VALUES = {
    "",
    "*",
    "**",
    "n/a",
    "na",
    "none",
    "null",
    "unknown",
    "not specified",
    "not available",
}


def parse_json(value):
    if not isinstance(value, str) or not value.strip():
        return None

    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def clean_text(value):
    """Remove empty values and obvious placeholder-only strings."""
    if value is None:
        return None

    text = str(value).strip()

    if text.lower() in PLACEHOLDER_VALUES:
        return None

    return text or None


def normalize_text(value):
    text = clean_text(value)

    if text is None:
        return ""

    text = re.sub(r"\s+", " ", text)
    return text.strip()


def valid_scope(value):
    """
    Return a scope only when it contains usable text.

    JSON arrays and objects are retained as readable text, but a scope
    made entirely of placeholder values is considered unavailable.
    """
    text = clean_text(value)

    if text is None:
        return None

    parsed = parse_json(text)

    if isinstance(parsed, list):
        valid_items = [
            normalize_text(item)
            for item in parsed
            if normalize_text(item)
        ]

        if not valid_items:
            return None

        return " | ".join(valid_items)

    if isinstance(parsed, dict):
        valid_items = []

        for key, item in parsed.items():
            cleaned_item = normalize_text(item)

            if cleaned_item:
                valid_items.append(f"{key}: {cleaned_item}")

        return " | ".join(valid_items) if valid_items else None

    return normalize_text(text) or None


def parse_message_list(value):
    parsed = parse_json(value)

    if not isinstance(parsed, list):
        return []

    return [
        normalize_text(item)
        for item in parsed
        if normalize_text(item)
    ]


def contains_pattern(text, pattern):
    return bool(re.search(pattern, text, re.IGNORECASE))


def extract_explicit_details(text):
    """
    Extract only details explicitly stated in the available text.

    This is rule-based extraction, not an LLM prediction. Unknown
    details remain unknown.
    """
    text = normalize_text(text)

    details = {
        "mentions_dimensions": False,
        "dimensions_text": None,
        "mentions_quantity": False,
        "quantity_text": None,
        "mentions_access_constraint": False,
        "access_notes": None,
        "mentions_materials": False,
        "materials_notes": None,
        "mentions_multiple_visits": False,
        "multi_visit_evidence": None,
        "mentions_urgency": False,
        "urgency_evidence": None,
        "mentions_water_shutoff": False,
        "water_shutoff_evidence": None,
        "mentions_electrical_panel": False,
        "mentions_wall_mounting": False,
        "mentions_leak": False,
    }

    if not text:
        return details

    # Dimensions: capture explicit measurements, not inferred sizes.
    dimension_pattern = (
        r"\b\d+(?:\.\d+)?\s*"
        r"(?:mm|cm|metres?|meters?|m|inches?|inch|in|ft|feet)\b"
    )

    dimensions = re.findall(
        dimension_pattern,
        text,
        flags=re.IGNORECASE,
    )

    if dimensions:
        details["mentions_dimensions"] = True
        details["dimensions_text"] = ", ".join(dimensions)

    # Quantity: only recognize explicit numeric quantities.
    quantity_pattern = (
        r"\b(?:replace|install|mount|repair|assemble|paint)\s+"
        r"(\d+)\s+"
        r"(?:items?|doors?|windows?|lights?|fixtures?|"
        r"shelves|cabinets|faucets|outlets|rooms?|panels?)\b"
    )

    quantity_match = re.search(
        quantity_pattern,
        text,
        flags=re.IGNORECASE,
    )

    if quantity_match:
        details["mentions_quantity"] = True
        details["quantity_text"] = quantity_match.group(0)

    # Access details: capture explicit access-related phrases.
    access_patterns = [
        r"\beasily accessible\b",
        r"\bhard to reach\b",
        r"\bdifficult to reach\b",
        r"\bhigh ceiling\b",
        r"\bladder\b",
        r"\bbehind the drywall\b",
        r"\binside the wall\b",
        r"\bunder the sink\b",
    ]

    access_matches = [
        re.search(pattern, text, re.IGNORECASE).group(0)
        for pattern in access_patterns
        if re.search(pattern, text, re.IGNORECASE)
    ]

    if access_matches:
        details["mentions_access_constraint"] = True
        details["access_notes"] = ", ".join(access_matches)

    # Materials: retain explicit supply statements.
    material_patterns = [
        r"\b(?:I|we)\s+(?:already\s+)?(?:have|purchased|bought)\s+"
        r"[^.!?\n]{1,100}",
        r"\btasker\s+(?:should|needs to|must)\s+bring\s+"
        r"[^.!?\n]{1,100}",
        r"\bmaterials?\s+(?:are|is)\s+"
        r"(?:provided|supplied|included)\b",
    ]

    material_matches = [
        match.group(0)
        for pattern in material_patterns
        for match in re.finditer(pattern, text, re.IGNORECASE)
    ]

    if material_matches:
        details["mentions_materials"] = True
        details["materials_notes"] = " | ".join(material_matches)

    multi_visit_pattern = (
        r"\bmultiple visits?\b"
        r"|\bmore than one visit\b"
        r"|\bmulti[- ]visit\b"
        r"|\breturn visit\b"
        r"|\bcome back\b"
        r"|\bcuring time\b"
        r"|\bdrying time\b"
    )

    if contains_pattern(text, multi_visit_pattern):
        details["mentions_multiple_visits"] = True
        details["multi_visit_evidence"] = "Explicit phrase found"

    urgency_pattern = (
        r"\bemergency\b"
        r"|\burgent\b"
        r"|\bas soon as possible\b"
        r"|\bimmediately\b"
        r"|\btoday\b"
    )

    urgency_match = re.search(
        urgency_pattern,
        text,
        flags=re.IGNORECASE,
    )

    if urgency_match:
        details["mentions_urgency"] = True
        details["urgency_evidence"] = urgency_match.group(0)

    shutoff_pattern = (
        r"\bshut(?:ting)?\s+off\b"
        r"|\bwater\s+(?:is\s+)?shut\s+off\b"
        r"|\bturn(?:ed|ing)?\s+off\s+(?:the\s+)?water\b"
    )

    shutoff_match = re.search(
        shutoff_pattern,
        text,
        flags=re.IGNORECASE,
    )

    if shutoff_match:
        details["mentions_water_shutoff"] = True
        details["water_shutoff_evidence"] = shutoff_match.group(0)

    details["mentions_electrical_panel"] = contains_pattern(
        text,
        r"\belectrical\s+panel\b|\b200\s*[- ]?amp\b",
    )

    details["mentions_wall_mounting"] = contains_pattern(
        text,
        r"\bmount(?:ing)?\b|\bwall[- ]mounted\b",
    )

    details["mentions_leak"] = contains_pattern(
        text,
        r"\bleak(?:ing)?\b|\bwater\s+leak\b",
    )

    return details


def extract_category_evidence(text):
    """
    Identify possible category evidence from text.

    This does not override the database category or confirm a category.
    """
    rules = {
        "Plumbing": (
            r"\bleak(?:ing)?\b|\bfaucet\b|\bpipe\b|\bsink\b"
            r"|\btoilet\b|\bdrain\b|\bshower\b|\bplumb(?:ing)?\b"
        ),
        "Electrical": (
            r"\belectrical\b|\bwiring\b|\bcircuit\b"
            r"|\bbreaker\b|\boutlet\b|\blight fixture\b"
            r"|\belectrical panel\b"
        ),
        "Mounting": (
            r"\bmount(?:ing)?\b|\btv\b|\bmirror\b"
            r"|\bwall bracket\b"
        ),
        "Assembly": (
            r"\bassemble\b|\bassembly\b|\bfurniture assembly\b"
        ),
        "Carpentry": (
            r"\bdeck\b|\bdoor frame\b|\bwooden\b|\bcarpentry\b"
            r"|\bbaseboard\b"
        ),
        "Home Improvement": (
            r"\bdrywall\b|\bpaint(?:ing)?\b|\bgrout\b"
            r"|\bwall patch\b"
        ),
        "HVAC": (
            r"\bhvac\b|\bfurnace\b|\bair conditioner\b"
            r"|\bthermostat\b"
        ),
    }

    matches = [
        category
        for category, pattern in rules.items()
        if contains_pattern(text, pattern)
    ]

    if len(matches) == 1:
        return matches[0], "single_rule_match"

    if len(matches) > 1:
        return None, "multiple_category_matches"

    return None, "no_category_rule_match"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    if not INPUT_FILE.exists():
        raise FileNotFoundError(
            f"Input file not found: {INPUT_FILE}. "
            "Run prepare_conversation_dataset.py first."
        )

    output_rows = []
    counts = {
        "records_read": 0,
        "records_with_initial_request": 0,
        "records_with_usable_final_scope": 0,
        "records_with_customer_followups": 0,
        "records_with_category_evidence": 0,
        "records_with_multiple_category_matches": 0,
        "records_with_explicit_dimensions": 0,
        "records_with_explicit_quantity": 0,
        "records_with_material_evidence": 0,
        "records_flagged_for_scope_review": 0,
        "records_with_image_references": 0,
    }

    with INPUT_FILE.open(
        "r",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        reader = csv.DictReader(file)

        for row in reader:
            counts["records_read"] += 1

            initial_request = normalize_text(
                row.get("initial_customer_request")
            )

            customer_messages = parse_message_list(
                row.get("all_customer_messages")
            )

            followups = parse_message_list(
                row.get("customer_followup_answers")
            )

            final_scope = valid_scope(
                row.get("final_quote_scope")
            )

            final_notes = valid_scope(
                row.get("final_quote_notes")
            )

            image_paths = parse_message_list(
                row.get("session_image_paths")
            )

            # Use customer-provided text and stored scope as separate
            # evidence sources. Assistant messages are not used as
            # ground truth for these fields.
            evidence_text = " ".join(
                item
                for item in [
                    initial_request,
                    " ".join(customer_messages),
                    " ".join(followups),
                    final_scope or "",
                    final_notes or "",
                ]
                if item
            )

            details = extract_explicit_details(evidence_text)

            possible_category, category_rule_status = (
                extract_category_evidence(evidence_text)
            )

            stored_category = normalize_text(
                row.get("detected_category")
            ) or None

            stored_category_id = normalize_text(
                row.get("category_id")
            ) or None

            if initial_request:
                counts["records_with_initial_request"] += 1

            if final_scope:
                counts["records_with_usable_final_scope"] += 1

            if followups:
                counts["records_with_customer_followups"] += 1

            if possible_category:
                counts["records_with_category_evidence"] += 1

            if category_rule_status == "multiple_category_matches":
                counts["records_with_multiple_category_matches"] += 1

            if details["mentions_dimensions"]:
                counts["records_with_explicit_dimensions"] += 1

            if details["mentions_quantity"]:
                counts["records_with_explicit_quantity"] += 1

            if details["mentions_materials"]:
                counts["records_with_material_evidence"] += 1

            if image_paths:
                counts["records_with_image_references"] += 1

            review_reasons = []

            if not initial_request:
                review_reasons.append("missing_initial_request")

            if not final_scope:
                review_reasons.append("missing_usable_final_scope")

            if not stored_category_id and not stored_category:
                review_reasons.append("missing_stored_category")

            if category_rule_status == "multiple_category_matches":
                review_reasons.append("ambiguous_text_category_evidence")

            if not followups:
                review_reasons.append("no_customer_followup_answers")

            if not image_paths:
                review_reasons.append("no_downloaded_image_references")

            if review_reasons:
                counts["records_flagged_for_scope_review"] += 1

            output_rows.append({
                "session_id": row.get("session_id"),
                "status": row.get("status"),
                "initial_customer_request": initial_request,
                "customer_followup_answers": json.dumps(
                    followups,
                    ensure_ascii=False,
                ),
                "usable_final_scope": final_scope or "",
                "usable_final_notes": final_notes or "",
                "stored_category": stored_category or "",
                "stored_category_id": stored_category_id or "",
                "text_category_evidence": possible_category or "",
                "category_rule_status": category_rule_status,
                "category_confirmed": False,
                "mentions_dimensions": details["mentions_dimensions"],
                "dimensions_text": details["dimensions_text"] or "",
                "mentions_quantity": details["mentions_quantity"],
                "quantity_text": details["quantity_text"] or "",
                "mentions_access_constraint": (
                    details["mentions_access_constraint"]
                ),
                "access_notes": details["access_notes"] or "",
                "mentions_materials": details["mentions_materials"],
                "materials_notes": details["materials_notes"] or "",
                "mentions_multiple_visits": (
                    details["mentions_multiple_visits"]
                ),
                "multi_visit_evidence": (
                    details["multi_visit_evidence"] or ""
                ),
                "mentions_urgency": details["mentions_urgency"],
                "urgency_evidence": details["urgency_evidence"] or "",
                "mentions_water_shutoff": (
                    details["mentions_water_shutoff"]
                ),
                "water_shutoff_evidence": (
                    details["water_shutoff_evidence"] or ""
                ),
                "mentions_electrical_panel": (
                    details["mentions_electrical_panel"]
                ),
                "mentions_wall_mounting": (
                    details["mentions_wall_mounting"]
                ),
                "mentions_leak": details["mentions_leak"],
                "estimated_hours": row.get("estimated_hours"),
                "estimated_price": row.get("estimated_price"),
                "estimated_total": row.get("estimated_total"),
                "session_image_paths": json.dumps(
                    image_paths,
                    ensure_ascii=False,
                ),
                "session_image_count": len(image_paths),
                "needs_scope_review": bool(review_reasons),
                "scope_review_reasons": json.dumps(
                    review_reasons,
                    ensure_ascii=False,
                ),
                "is_verified_training_label": False,
            })

    fieldnames = list(output_rows[0].keys()) if output_rows else [
        "session_id",
        "status",
        "initial_customer_request",
        "customer_followup_answers",
        "usable_final_scope",
        "usable_final_notes",
        "stored_category",
        "stored_category_id",
        "text_category_evidence",
        "category_rule_status",
        "category_confirmed",
        "needs_scope_review",
        "scope_review_reasons",
        "is_verified_training_label",
    ]

    with OUTPUT_FILE.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(output_rows)

    with SUMMARY_FILE.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["metric", "value"],
        )
        writer.writeheader()

        for metric, value in counts.items():
            writer.writerow({
                "metric": metric,
                "value": value,
            })

    print("\nStructured job-detail extraction completed.")
    print("Records processed:", counts["records_read"])

    for metric, value in counts.items():
        if metric != "records_read":
            print(f"{metric}: {value}")

    print("\nOutput files:")
    print("Structured details:", OUTPUT_FILE)
    print("Extraction summary:", SUMMARY_FILE)

    print(
        "\nImportant: extracted fields are rule-based evidence, not "
        "verified facts. Category evidence does not override the stored "
        "category, and all records remain unverified training labels."
    )


if __name__ == "__main__":
    main()