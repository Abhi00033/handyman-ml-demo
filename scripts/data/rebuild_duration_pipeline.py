from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

# Read-only pipeline: reads the current Laravel/MariaDB tables and writes CSV reports.
# It never updates or deletes database records.
ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "datasets" / "reports"
PREPARED = ROOT / "datasets" / "prepared"

MAPPING_REPORT = REPORTS / "automatic_category_mapping_report.csv"
CLEAN_DATASET = PREPARED / "automatically_clean_duration_dataset.csv"
BASELINE_FILE = PREPARED / "automatically_clean_duration_baseline.csv"
EXCLUSION_REPORT = REPORTS / "automatic_duration_exclusions.csv"
SUMMARY_REPORT = REPORTS / "automatic_duration_pipeline_summary.csv"

EXCLUDED_STATUSES = {
    "deleted", "rejected", "draft", "questioning", "address_required"
}
MAX_VALID_HOURS = 100
MIN_BASELINE_SAMPLES = 5

# Category IDs from the currently audited categories table.
# These are candidate destinations, validated against the live DB on each run.
CAT_PLUMBING = 1
CAT_HOME_REPAIRS = 3
CAT_ELECTRICAL = 4
CAT_CARPENTRY = 5
CAT_APPLIANCE = 6
CAT_HVAC = 7
CAT_HOME_IMPROVEMENT = 17
CAT_ASSEMBLY = 18
CAT_MOUNTING = 19


def parse_jsonish(value: Any) -> Any:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, (dict, list)):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return value


def normalize_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip().lower()


def extract_text(value: Any) -> str:
    """Extract text from a JSON value, including Laravel/OpenAI message shapes."""
    parsed = parse_jsonish(value)
    chunks: list[str] = []

    def walk(obj: Any) -> None:
        if isinstance(obj, str):
            if obj.strip():
                chunks.append(obj.strip())
        elif isinstance(obj, list):
            for item in obj:
                walk(item)
        elif isinstance(obj, dict):
            # Message content may be a string or list of {type: text, text: ...}.
            if isinstance(obj.get("text"), str):
                walk(obj["text"])
            elif isinstance(obj.get("content"), (str, list, dict)):
                walk(obj["content"])
            elif isinstance(obj.get("parts"), list):
                walk(obj["parts"])
            # Deliberately ignore image URLs/base64 payloads.
    walk(parsed)
    return " ".join(chunks)


def extract_customer_messages(value: Any) -> str:
    """Only include user/customer message text, excluding assistant instructions."""
    parsed = parse_jsonish(value)
    messages = parsed if isinstance(parsed, list) else []
    collected: list[str] = []

    for item in messages:
        if not isinstance(item, dict):
            continue
        role = normalize_text(item.get("role") or item.get("sender") or "")
        if role not in {"user", "customer", "client"}:
            continue
        text = extract_text(item.get("content", item.get("message", "")))
        if text:
            collected.append(text)
    return " | ".join(collected)


def parse_final_quote(value: Any) -> dict:
    parsed = parse_jsonish(value)
    if isinstance(parsed, dict):
        return parsed
    # Some historical records may store a JSON list or a plain string.
    return {}


def scope_text(final_quote: dict) -> str:
    for key in ("scope", "projects", "raw"):
        value = final_quote.get(key)
        if value:
            return extract_text(value)
    return ""


def has_usable_scope(value: Any) -> bool:
    text = extract_text(value)
    return bool(text and normalize_text(text) not in {"[]", "{}", "null", "none"})


def category_lookup(categories: pd.DataFrame) -> dict[int, dict]:
    result = {}
    for _, row in categories.iterrows():
        result[int(row["id"])] = {
            "id": int(row["id"]),
            "name": str(row["name"]),
            "slug": str(row.get("slug") or ""),
            "is_active": bool(row.get("is_active")),
            "deleted_at": row.get("deleted_at"),
        }
    return result


def category_is_usable(category: dict | None) -> bool:
    if not category:
        return False
    deleted = category.get("deleted_at")
    deleted_present = not (pd.isna(deleted) or str(deleted).strip() in {"", "None", "NaT"})
    return bool(category.get("is_active")) and not deleted_present


def classify_by_scope(
    text: str,
    categories_by_id: dict[int, dict],
) -> tuple[int | None, str, str, float, str]:
    """Classify a single job scope with conservative, auditable rules.

    This function does not force mixed-trade or multi-project quotes into one
    category. Incidental context (such as drywall being the TV mounting
    surface) is not treated as a separate trade unless repair work is stated.
    """
    t = normalize_text(text)
    if not t:
        return None, "", "unresolved", 0.0, "No usable customer/scope text"

    # A quote containing multiple numbered projects is not one job scope.
    # Leave it for review rather than using whichever trade keyword wins.
    numbered_projects = re.findall(r"\bproject\s*\d+\s*[-:\u2013\u2014]", t)
    if len(set(numbered_projects)) >= 2 or len(numbered_projects) >= 2:
        return None, "", "unresolved", 0.0, (
            "Conflicting category rules matched: multi_project_scope"
        )

    detected_category_match = re.search(r"\bdetected_category\s*:\s*([^\n]+)", t)
    if detected_category_match:
        detected_value = detected_category_match.group(1)
        if len(re.findall(r"[,|]", detected_value)) >= 1:
            return None, "", "unresolved", 0.0, (
                "Conflicting category rules matched: multi_project_scope"
            )

    rules = [
        (
            CAT_MOUNTING, "Mounting", 0.94, "clear_mounting_scope",
            [
                r"\b(tv|television)\b.{0,60}\b(mount|mounted|mounting|remount|remounted|remounting|install|installation|relocat|relocate|reinstall)\b",
                r"\b(mount|mounted|mounting|remount|remounted|remounting|relocat|relocate|reinstall)\b.{0,60}\b(tv|television|modem|router)\b",
                r"\b(modem|router)\b.{0,45}\b(mount|mounted|remount|remounting|ceiling|relocat|relocate)\b",
                r"\b(mount|remount|remounting|relocat|relocate)\b.{0,45}\b(modem|router)\b",
                r"\bmirror\b.{0,35}\b(mount|hang|install|installation)\b",
                r"\b(mount|hang|install|installation)\b.{0,35}\bmirror\b",
            ],
        ),
        (
            CAT_ASSEMBLY, "Assembly", 0.92, "clear_assembly_scope",
            [
                r"\b(assemble|assembly|assembling)\b",
                r"\b(build|put together)\b.{0,30}\b(furniture|desk|bed|cabinet|shelf)\b",
            ],
        ),
        (
            CAT_PLUMBING, "Plumbing", 0.91, "clear_plumbing_scope",
            [
                r"\b(leak|plumb|faucet|tap|toilet|drain|pipe|shower valve|shower cartridge|diverter spout|water heater|hot water supply|supply line|showerhead arm)\b",
                r"\bsink\b.{0,35}\b(repair|install|replace|leak|clog)\b",
                r"\b(replace|repair|install|remove)\b.{0,45}\b(bathtub diverter|shower cartridge|showerhead arm)\b",
                r"\b(hot water)\b.{0,35}\b(outlet|pipe|line|connection)\b",
            ],
        ),
        (
            CAT_ELECTRICAL, "Electrical", 0.94, "clear_electrical_scope",
            [
                r"\b(amp|amperage)\b.{0,35}\b(panel|service)\b",
                r"\b(electrical panel|circuit breaker|rewire|electrician|electrical upgrade|electrical wiring|new circuit)\b",
                r"\b(new|install|installing|replace|replacing|repair|repairing|add|adding|move|moving|relocate|relocating)\b.{0,45}\b(electrical outlet|new outlet|outlet|socket|light fixture)\b",
                r"\b(outlet|socket)\b.{0,35}\b(damaged|nonfunctional|not working|replace|repair|install|installing|new)\b",
                r"\b(wiring|electrical wiring)\b",
            ],
        ),
        (
            CAT_HVAC, "HVAC", 0.92, "clear_hvac_scope",
            [
                r"\b(hvac|furnace|air conditioner|air conditioning|thermostat|heat pump|ductwork)\b",
            ],
        ),
        (
            CAT_APPLIANCE, "Appliance Services", 0.90, "clear_appliance_scope",
            [
                r"\b(repair|install|replace|service|remove|reattach|reconnect)\b.{0,35}\b(refrigerator|dishwasher|washer|dryer|oven|stove|microwave)\b",
                r"\b(refrigerator|dishwasher|washer|dryer|oven|stove|microwave)\b.{0,35}\b(repair|install|replace|service|reattach|reconnect)\b",
            ],
        ),
        (
            CAT_CARPENTRY, "Carpentry", 0.89, "clear_carpentry_scope",
            [
                r"\b(deck boards?|joists?|wood framing|wooden stairs|wood trim|baseboard|edge banding|laminate surface|tabletop|table surface|wooden trim)\b",
                r"\b(replace|repair|install|refinish|secure|tighten|sand)\b.{0,40}\b(deck boards?|wood trim|baseboard|edge banding|laminate surface|tabletop|table surface|wooden trim)\b",
            ],
        ),
        (
            CAT_HOME_IMPROVEMENT, "Home Improvement", 0.89, "clear_wall_finish_scope",
            [
                r"\b(patch|repair|replace|sand|paint|repaint|prime|spackle|plaster|joint compound|regrout|grout|tile sealing)\b.{0,45}\b(wall|drywall|sheetrock|ceiling|plaster|hole|crack|tile|grout|painted area)\b",
                r"\b(wall|drywall|sheetrock|ceiling|plaster|hole|crack)\b.{0,45}\b(patch|repair|replace|sand|paint|repaint|prime|spackle|joint compound|damaged)\b",
                r"\b(remove existing caulk|apply fresh caulk|recaulk|re-caulk|reglaze|bathtub refinishing|pressure wash|powerwash|power wash)\b",
            ],
        ),
    ]

    matches = []
    for category_id, expected_name, confidence, reason, patterns in rules:
        if any(re.search(pattern, t) for pattern in patterns):
            matches.append((category_id, expected_name, confidence, reason))

    if not matches:
        return None, "", "unresolved", 0.0, "No clear deterministic rule matched"

    mounting_present = any(m[0] == CAT_MOUNTING for m in matches)
    plumbing_present = any(m[0] == CAT_PLUMBING for m in matches)
    electrical_present = any(m[0] == CAT_ELECTRICAL for m in matches)
    carpentry_present = any(m[0] == CAT_CARPENTRY for m in matches)

    # Actual wall repair/finishing is different from merely mounting something
    # on drywall. Only suppress the wall-finish match when no repair is stated.
    actual_wall_repair = bool(re.search(
        r"\b(patch|repair|replace|sand|paint|repaint|prime|spackle|"
        r"joint compound|drywall damage|wall hole|crack|plaster repair|"
        r"remove existing caulk|apply fresh caulk|recaulk|re-caulk|reglaze|"
        r"pressure wash|powerwash|power wash)\b",
        t,
    ))
    if mounting_present and not actual_wall_repair:
        matches = [m for m in matches if m[0] != CAT_HOME_IMPROVEMENT]

    # Cable hiding/routing is incidental to mounting unless the text explicitly
    # asks for new electrical installation or electrical repair.
    incidental_cable_context = bool(re.search(
        r"\b(hide|conceal|route|routing)\b.{0,35}\b(tv )?(power )?(cables?|wires?)\b|"
        r"\b(cables?|wires?)\b.{0,35}\bbehind the wall\b",
        t,
    ))
    explicit_electrical_work = bool(re.search(
        r"\b(new electrical outlet|install(?:ing)?\s+(?:a\s+|an\s+|the\s+)?new\s+(?:electrical\s+)?outlet|"
        r"add\s+(?:a\s+)?new\s+outlet|new circuit|rewire|electrical panel|circuit breaker|"
        r"electrician|electrical wiring|replace (?:the )?(?:damaged )?outlet|repair (?:the )?outlet)\b",
        t,
    ))
    if mounting_present and incidental_cable_context and not explicit_electrical_work:
        matches = [m for m in matches if m[0] != CAT_ELECTRICAL]

    # "Hot water outlet" is a plumbing connection when the text describes a
    # water heater, pipe, or supply line; the word outlet alone is not electrical.
    hot_water_plumbing_context = bool(re.search(
        r"\b(hot water|water heater|pipe|plumbing|supply line)\b", t
    ))
    if hot_water_plumbing_context and not explicit_electrical_work:
        matches = [
            m for m in matches
            if not (
                m[0] == CAT_ELECTRICAL
                and re.search(r"\b(outlet|socket)\b", t)
                and not re.search(
                    r"\b(electrical panel|circuit breaker|rewire|electrician|electrical wiring|new circuit)\b",
                    t,
                )
            )
        ]

    # Plumbing pipe assembly is not furniture assembly.
    if plumbing_present:
        matches = [m for m in matches if m[0] != CAT_ASSEMBLY]

    # Wood trim/tabletop work is carpentry. A generic mention of finishing
    # edges must not trigger wall finishing unless actual wall repair is stated.
    if carpentry_present and not actual_wall_repair:
        matches = [m for m in matches if m[0] != CAT_HOME_IMPROVEMENT]

    # Re-deduplicate category matches after applying contextual rules.
    unique_matches = []
    seen_categories = set()
    for match in matches:
        if match[0] not in seen_categories:
            unique_matches.append(match)
            seen_categories.add(match[0])
    matches = unique_matches

    distinct_categories = {m[0] for m in matches}
    if len(distinct_categories) > 1:
        reasons = " vs ".join(m[3] for m in matches)
        return None, "", "unresolved", 0.0, (
            f"Conflicting category rules matched: {reasons}"
        )

    top = matches[0]
    category = categories_by_id.get(top[0])
    if not category_is_usable(category):
        return (
            top[0], top[1], "unresolved", top[2],
            f"Rule matched but destination category {top[0]} is inactive/missing/soft-deleted",
        )

    if normalize_text(category["name"]) != normalize_text(top[1]):
        return (
            top[0], category["name"], "unresolved", top[2],
            f"Rule destination name mismatch: expected {top[1]}, live DB says {category['name']}",
        )

    return top[0], category["name"], "auto_mapped", top[2], top[3]
def main():
    # Import existing project connection helper.
    from db import get_connection

    REPORTS.mkdir(parents=True, exist_ok=True)
    PREPARED.mkdir(parents=True, exist_ok=True)

    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, name, slug, is_active, deleted_at FROM categories"
            )
            category_rows = cursor.fetchall()

            # Select current rows from the live DB. No writes are performed.
            cursor.execute("SELECT * FROM quote_sessions")
            session_rows = cursor.fetchall()
    finally:
        conn.close()

    categories = pd.DataFrame(category_rows)
    sessions = pd.DataFrame(session_rows)
    if sessions.empty:
        raise RuntimeError("No quote_sessions rows were returned.")

    categories_by_id = category_lookup(categories)
    output_rows = []

    for _, row in sessions.iterrows():
        session_id = row.get("id")
        status = normalize_text(row.get("status"))
        historical_id = row.get("category_id")
        try:
            historical_id_int = int(float(historical_id)) if pd.notna(historical_id) else None
        except (TypeError, ValueError):
            historical_id_int = None

        historical_name_value = row.get("detected_category")
        historical_name = (
            "" if historical_name_value is None or pd.isna(historical_name_value)
            else str(historical_name_value).strip()
        )
        user_text = extract_customer_messages(row.get("openai_messages"))
        final_quote = parse_final_quote(row.get("final_quote"))
        final_scope = scope_text(final_quote)
        combined_text = " | ".join(x for x in [user_text, final_scope] if x)

        hours = pd.to_numeric(row.get("estimated_hours"), errors="coerce")
        status_excluded = status in EXCLUDED_STATUSES
        scope_ok = has_usable_scope(final_scope)

        current_historical_category = categories_by_id.get(historical_id_int)
        exact_match = (
            current_historical_category is not None
            and category_is_usable(current_historical_category)
            and normalize_text(current_historical_category["name"]) == normalize_text(historical_name)
        )

        # Always run semantic rules, including on historical labels that match
        # the live category table. A matching ID/name is not proof that the job
        # description belongs to that category.
        semantic_id, semantic_name, semantic_status, semantic_score, semantic_reason = (
            classify_by_scope(combined_text, categories_by_id)
        )

        category_consistency_status = "not_assessable_no_clear_rule"
        category_consistency_reason = (
            "No clear semantic rule; historical label retained only if live ID/name is valid"
        )

        # Narrow, auditable override: if the historical category is broad
        # Home Repairs but the complete scope unambiguously matches Mounting,
        # use Mounting for the proposed training/baseline category. The original
        # historical category remains in the report and database unchanged.
        mounting_category = categories_by_id.get(CAT_MOUNTING)
        override_home_repairs_to_mounting = (
            exact_match
            and normalize_text(current_historical_category["name"]) == "home repairs"
            and semantic_status == "auto_mapped"
            and semantic_id == CAT_MOUNTING
            and normalize_text(semantic_name) == "mounting"
            and category_is_usable(mounting_category)
            and normalize_text(mounting_category["name"]) == "mounting"
        )

        if override_home_repairs_to_mounting:
            proposed_id = CAT_MOUNTING
            proposed_name = mounting_category["name"]
            mapping_status = "auto_mapped"
            confidence = semantic_score
            mapping_reason = (
                "Clear Mounting scope overrides broad historical Home Repairs "
                "category; historical label retained for audit"
            )
            category_consistency_status = (
                "semantic_rule_overrode_broad_historical_category"
            )
            category_consistency_reason = semantic_reason

        elif exact_match:
            proposed_id = historical_id_int
            proposed_name = current_historical_category["name"]
            mapping_status = "exact_active_category_match"
            confidence = None  # exact DB match is not a calibrated confidence score
            mapping_reason = "Historical ID/name matches an active, non-deleted live category"

            if semantic_status == "auto_mapped":
                if semantic_id == historical_id_int:
                    category_consistency_status = "semantic_rule_agrees"
                    category_consistency_reason = semantic_reason
                else:
                    category_consistency_status = "semantic_mismatch_review"
                    category_consistency_reason = (
                        f"Live historical category is {proposed_name} (ID {proposed_id}), "
                        f"but text rules suggest {semantic_name} (ID {semantic_id}): {semantic_reason}"
                    )
            elif (
                semantic_status == "unresolved"
                and "Conflicting category rules matched" in semantic_reason
            ):
                category_consistency_status = "conflicting_rules_review"
                category_consistency_reason = semantic_reason
        else:
            proposed_id, proposed_name, mapping_status, confidence, mapping_reason = (
                semantic_id, semantic_name, semantic_status, semantic_score, semantic_reason
            )
            if mapping_status == "auto_mapped":
                mapping_reason = (
                    f"Historical label '{historical_name}' / ID {historical_id_int} "
                    f"did not match a current active category; {mapping_reason}"
                )
                category_consistency_status = "auto_mapped_by_semantic_rule"
                category_consistency_reason = semantic_reason
            elif "Conflicting category rules matched" in mapping_reason:
                category_consistency_status = "conflicting_rules_review"
                category_consistency_reason = mapping_reason
            else:
                category_consistency_status = "unresolved_no_clear_rule"
                category_consistency_reason = mapping_reason

        # Historical categories that are inactive/soft-deleted are never accepted
        # as destination categories. They must be mapped to a valid live category.
        if (
            current_historical_category is not None
            and not category_is_usable(current_historical_category)
            and mapping_status == "exact_active_category_match"
        ):
            mapping_status = "unresolved"
            category_consistency_status = "inactive_historical_category_review"
            category_consistency_reason = "Historical category is inactive or soft-deleted"
            mapping_reason = category_consistency_reason

        exclusion_reasons = []
        if status_excluded:
            exclusion_reasons.append(f"excluded_status:{status}")
        if pd.isna(hours):
            exclusion_reasons.append("missing_or_invalid_estimated_hours")
        elif hours <= 0 or hours > MAX_VALID_HOURS:
            exclusion_reasons.append("estimated_hours_outside_valid_range")
        if not scope_ok:
            exclusion_reasons.append("missing_or_unusable_final_scope")
        if mapping_status not in {"exact_active_category_match", "auto_mapped"}:
            exclusion_reasons.append("category_mapping_unresolved")
        if category_consistency_status in {"semantic_mismatch_review", "conflicting_rules_review", "inactive_historical_category_review"}:
            exclusion_reasons.append(f"category_consistency:{category_consistency_status}")

        eligible = not exclusion_reasons

        output_rows.append({
            "session_id": session_id,
            "status": row.get("status"),
            "historical_category_id": historical_id_int,
            "historical_category_name": historical_name,
            "proposed_category_id": proposed_id,
            "proposed_category_name": proposed_name,
            "mapping_status": mapping_status,
            "mapping_confidence": confidence,
            "mapping_reason": mapping_reason,
            "mapping_score_type": "rule_heuristic_not_probability" if pd.notna(confidence) else "not_scored",
            "semantic_suggested_category_id": semantic_id,
            "semantic_suggested_category_name": semantic_name,
            "semantic_rule_status": semantic_status,
            "semantic_rule_score": semantic_score,
            "category_consistency_status": category_consistency_status,
            "category_consistency_reason": category_consistency_reason,
            "estimated_hours": float(hours) if pd.notna(hours) else None,
            "customer_messages": user_text,
            "final_quote_scope": final_scope,
            "multi_visit": final_quote.get("multi_visit"),
            "scope_is_usable": scope_ok,
            "eligible_for_duration_baseline": eligible,
            "exclusion_reasons": "; ".join(exclusion_reasons),
        })

    report = pd.DataFrame(output_rows)
    report.to_csv(MAPPING_REPORT, index=False)

    excluded = report[~report["eligible_for_duration_baseline"]].copy()
    excluded.to_csv(EXCLUSION_REPORT, index=False)

    clean = report[report["eligible_for_duration_baseline"]].copy()
    clean = clean.rename(columns={
        "proposed_category_id": "category_id",
        "proposed_category_name": "detected_category",
    })
    clean.to_csv(CLEAN_DATASET, index=False)

    if not clean.empty:
        baseline = (
            clean.groupby(["category_id", "detected_category"], dropna=False)
            .agg(
                sample_count=("session_id", "nunique"),
                average_hours=("estimated_hours", "mean"),
                median_hours=("estimated_hours", "median"),
                p75_hours=("estimated_hours", lambda s: s.quantile(0.75)),
                p90_hours=("estimated_hours", lambda s: s.quantile(0.90)),
                minimum_hours=("estimated_hours", "min"),
                maximum_hours=("estimated_hours", "max"),
            )
            .reset_index()
        )
        baseline["data_quality"] = baseline["sample_count"].apply(
            lambda n: "preliminary_category_baseline"
            if n >= MIN_BASELINE_SAMPLES else "low_data_manual_review"
        )
        baseline["estimate_source"] = "live_db_historical_quoted_hours"
    else:
        baseline = pd.DataFrame(columns=[
            "category_id", "detected_category", "sample_count",
            "average_hours", "median_hours", "p75_hours", "p90_hours",
            "minimum_hours", "maximum_hours", "data_quality", "estimate_source"
        ])
    baseline.to_csv(BASELINE_FILE, index=False)

    summary = pd.DataFrame([{
        "live_quote_sessions_read": len(report),
        "eligible_duration_records": len(clean),
        "excluded_records": len(excluded),
        "exact_active_category_matches": int(
            report["mapping_status"].eq("exact_active_category_match").sum()
        ),
        "automatically_mapped_records": int(
            report["mapping_status"].eq("auto_mapped").sum()
        ),
        "unresolved_mapping_records": int(
            report["mapping_status"].eq("unresolved").sum()
            + report["mapping_status"].eq("no_rule").sum()
        ),
        "semantic_mismatch_records": int(report["category_consistency_status"].eq("semantic_mismatch_review").sum()),
        "conflicting_rule_records": int(report["category_consistency_status"].eq("conflicting_rules_review").sum()),
        "records_with_semantic_rule_agreement": int(report["category_consistency_status"].eq("semantic_rule_agrees").sum()),
        "excluded_status_records": int(
            report["exclusion_reasons"].str.contains("excluded_status:", na=False).sum()
        ),
        "large_estimates_over_8_hours_kept": int(
            (clean["estimated_hours"] > 8).sum()
        ) if not clean.empty else 0,
        "category_baseline_groups": len(baseline),
    }])
    summary.to_csv(SUMMARY_REPORT, index=False)

    print("\n=== AUTOMATIC DURATION PIPELINE SUMMARY ===")
    print(summary.to_string(index=False))
    print("\n=== Mapping status counts ===")
    print(report["mapping_status"].value_counts(dropna=False).to_string())
    print("\n=== Category consistency counts ===")
    print(report["category_consistency_status"].value_counts(dropna=False).to_string())
    print("\n=== Eligible category baselines ===")
    print(baseline.to_string(index=False))
    print("\nGenerated files:")
    print(MAPPING_REPORT)
    print(CLEAN_DATASET)
    print(BASELINE_FILE)
    print(EXCLUSION_REPORT)
    print(SUMMARY_REPORT)
    print("\nDatabase was read only; no DB records were modified.")


if __name__ == "__main__":
    main()
