
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

SESSION_FILE = (
    ROOT / "datasets" / "prepared"
    / "historical_conversation_records.csv"
)

STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "i", "we",
    "you", "your", "my", "me", "it", "to", "of", "for", "and",
    "or", "in", "on", "at", "with", "do", "does", "did", "can",
    "could", "would", "should", "want", "need", "please", "help",
    "some", "something", "this", "that", "there", "have", "has",
    "from", "about", "into", "then", "than", "just", "like",
    "job", "work", "task", "service", "home", "please",
}

# Simple normalization for common word forms. This is not a full stemmer.
NORMALIZE_WORDS = {
    "leaking": "leak",
    "leaked": "leak",
    "leaks": "leak",
    "replacing": "replace",
    "replaced": "replace",
    "replacement": "replace",
    "mounting": "mount",
    "mounted": "mount",
    "mounts": "mount",
    "pipes": "pipe",
    "joints": "joint",
    "cables": "cable",
    "panels": "panel",
    "televisions": "television",
    "tv": "television",
    "electrical": "electric",
}


def tokenize(text: Any) -> set[str]:
    words = re.findall(r"[a-z0-9]+", str(text).lower())

    return {
        NORMALIZE_WORDS.get(word, word)
        for word in words
        if len(word) > 1 and word not in STOP_WORDS
    }


def parse_json(value: Any, default: Any = None) -> Any:
    if not isinstance(value, str):
        return value if value is not None else default

    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return default


def parse_conversation(value: Any) -> list[dict]:
    result = parse_json(value, [])

    if not isinstance(result, list):
        return []

    return [message for message in result if isinstance(message, dict)]


def readable_text(value: Any) -> str:
    """Convert JSON-like scopes into readable searchable text."""
    parsed = parse_json(value, None)

    if isinstance(parsed, (dict, list)):
        return json.dumps(parsed, ensure_ascii=False)

    if parsed is not None:
        return str(parsed)

    return str(value or "")


def load_historical_sessions() -> pd.DataFrame:
    if not SESSION_FILE.exists():
        raise FileNotFoundError(
            f"Historical dataset not found: {SESSION_FILE}\n"
            "Run: python -m scripts.data.extract_historical_knowledge"
        )

    df = pd.read_csv(SESSION_FILE).fillna("")

    required = {
        "session_id",
        "status",
        "task_title",
        "detected_category",
        "estimated_hours",
        "conversation_json",
        "final_scope",
        "review_status",
    }

    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Historical dataset is missing columns: {sorted(missing)}"
        )

    return df


def conversation_text(messages: list[dict]) -> str:
    parts = []

    for message in messages:
        # Support both extractor output ("text") and raw JSON ("content").
        text = message.get("text", message.get("content", ""))

        if isinstance(text, (dict, list)):
            text = json.dumps(text, ensure_ascii=False)

        if text:
            parts.append(str(text))

    return " ".join(parts)


def extract_title(row: pd.Series, messages: list[dict]) -> str:
    title = str(row.get("task_title", "")).strip()

    if title:
        return title

    # Some exports may contain the title only in final_quote.
    final_quote = parse_json(row.get("final_quote", ""), {})
    if isinstance(final_quote, dict):
        title = str(final_quote.get("task_title", "")).strip()
        if title:
            return title

    # Last fallback: look for a title field in conversation messages.
    for message in messages:
        for key in ("task_title", "taskTitle", "title"):
            value = message.get(key)

            if isinstance(value, str) and value.strip():
                return value.strip()

    return ""


def score_field(
    query_tokens: set[str],
    field_text: str,
    field_weight: float,
) -> tuple[float, set[str]]:
    field_tokens = tokenize(field_text)

    if not field_tokens:
        return 0.0, set()

    overlap = query_tokens & field_tokens
    if not overlap:
        return 0.0, set()

    # Query coverage matters more than the length of the full conversation.
    coverage = len(overlap) / len(query_tokens)

    # A small precision component discourages matches in very broad fields.
    precision = len(overlap) / len(field_tokens)

    score = field_weight * (0.8 * coverage + 0.2 * precision)

    return score, overlap


def retrieve_historical_cases(
    query: str,
    limit: int = 5,
) -> list[dict]:
    """
    Retrieve historical cases for review.

    This is a weighted lexical baseline, not trained ML or semantic search.
    Historical scope and hours are evidence only and are not guaranteed truth.
    """
    query_tokens = tokenize(query)

    if not query_tokens:
        return []

    df = load_historical_sessions()
    matches = []

    for _, row in df.iterrows():
        messages = parse_conversation(row.get("conversation_json", ""))
        title = extract_title(row, messages)
        category = str(row.get("detected_category", "")).strip()
        scope = readable_text(row.get("final_scope", ""))
        convo = conversation_text(messages)

        # Separate fields prevent a long conversation from dominating ranking.
        fields = [
            (title, 4.0),
            (scope, 3.0),
            (category, 1.5),
            (convo, 0.75),
        ]

        raw_score = 0.0
        all_matched_terms: set[str] = set()

        for field_text, weight in fields:
            field_score, field_matches = score_field(
                query_tokens,
                field_text,
                weight,
            )
            raw_score += field_score
            all_matched_terms.update(field_matches)

        if not all_matched_terms:
            continue

        # Explicitly reward matching the more informative query terms.
        # Generic action words alone should not make a strong match.
        strong_terms = query_tokens - {
            "repair", "install", "fix", "replace", "change",
            "work", "service",
        }
        strong_matches = all_matched_terms & strong_terms

        if strong_terms:
            strong_coverage = len(strong_matches) / len(strong_terms)
        else:
            strong_coverage = 0.0

        raw_score += 0.5 * strong_coverage

        try:
            hours = float(row.get("estimated_hours"))
            if hours <= 0:
                hours = None
        except (TypeError, ValueError):
            hours = None

        status = str(row.get("status", "")).strip()
        review_status = str(
            row.get("review_status", "unverified")
        ).strip() or "unverified"

        # Prefer records with both a usable scope and recorded hours.
        has_scope = bool(tokenize(scope))
        has_hours = hours is not None

        if has_scope and has_hours:
            quality_multiplier = 1.0
        elif has_scope or has_hours:
            quality_multiplier = 0.75
        else:
            quality_multiplier = 0.4

        # Incomplete questioning sessions may help discover questions,
        # but should not outrank usable quote examples without strong evidence.
        if status.lower() in {"questioning", "draft", "deleted"}:
            quality_multiplier *= 0.7

        final_score = raw_score * quality_multiplier

        matches.append({
            "session_id": str(row.get("session_id", "")),
            "status": status,
            "task_title": title,
            "category": category,
            "estimated_hours": hours,
            "similarity_score": round(final_score, 4),
            "matched_terms": ", ".join(sorted(all_matched_terms)),
            "review_status": review_status,
            "has_scope": has_scope,
            "has_recorded_hours": has_hours,
            "conversation": messages,
            "final_scope": scope,
        })

    matches.sort(
        key=lambda item: (
            -item["similarity_score"],
            not item["has_scope"],
            not item["has_recorded_hours"],
            item["session_id"],
        )
    )

    safe_limit = max(1, min(int(limit), 20))
    return matches[:safe_limit]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search historical Star Handyman quote sessions."
    )
    parser.add_argument(
        "--query",
        required=True,
        help="Example: water leaking from hot water pipe joint",
    )
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    results = retrieve_historical_cases(args.query, args.limit)

    print("\nHISTORICAL RETRIEVAL RESULTS")
    print("Query:", args.query)
    print("Matches:", len(results))
    print("Ranking: weighted lexical retrieval; not a trained model")
    print("Historical records are unverified evidence.\n")

    for index, item in enumerate(results, start=1):
        print(f"--- Match {index} ---")
        print("Session:", item["session_id"])
        print("Status:", item["status"])
        print("Task:", item["task_title"] or "(missing)")
        print("Category:", item["category"] or "(missing)")
        print("Recorded hours:", item["estimated_hours"])
        print("Similarity:", item["similarity_score"])
        print("Matched terms:", item["matched_terms"])
        print("Has scope:", item["has_scope"])
        print("Has recorded hours:", item["has_recorded_hours"])
        print("Review status:", item["review_status"])
        print("Scope:", item["final_scope"][:500])
        print()


if __name__ == "__main__":
    main()
