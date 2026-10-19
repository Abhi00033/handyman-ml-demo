import json
from collections import Counter

from db import get_connection


def parse_json(value):
    """Parse JSON safely without assuming its structure."""
    if value is None:
        return None

    if isinstance(value, (dict, list)):
        return value

    if not isinstance(value, str) or not value.strip():
        return None

    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def describe_structure(value):
    """Describe JSON structure without displaying customer content."""
    if isinstance(value, dict):
        return {
            "type": "object",
            "keys": list(value.keys())[:40],
        }

    if isinstance(value, list):
        first_item = value[0] if value else None

        return {
            "type": "array",
            "length": len(value),
            "first_item_type": type(first_item).__name__
            if first_item is not None
            else None,
            "first_item_keys": list(first_item.keys())[:30]
            if isinstance(first_item, dict)
            else [],
        }

    return {
        "type": type(value).__name__ if value is not None else "null"
    }


def count_message_roles(value):
    """Count message roles only when the structure is recognizable."""
    counts = Counter()

    def walk(item):
        if isinstance(item, list):
            for child in item:
                walk(child)

        elif isinstance(item, dict):
            role = item.get("role") or item.get("sender")

            if isinstance(role, str):
                counts[role] += 1

            # Support common nested conversation containers.
            for key in ("messages", "conversation", "history"):
                if key in item:
                    walk(item[key])

    walk(value)
    return counts


def print_counter(title, counter):
    print(f"\n{title}")

    if not counter:
        print("  No records found.")
        return

    for name, count in counter.most_common():
        print(f"  {str(name):<35} {count}")


def main():
    connection = None

    try:
        connection = get_connection()

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    status,
                    openai_messages,
                    final_quote,
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
                    created_at
                FROM quote_sessions
                ORDER BY id
                """
            )

            sessions = cursor.fetchall()

            cursor.execute(
                """
                SELECT quote_session_id, path, disk
                FROM quote_session_images
                ORDER BY quote_session_id, id
                """
            )

            images = cursor.fetchall()

        print("=" * 65)
        print("STAR HANDYMAN TRAINING DATA AUDIT")
        print("=" * 65)

        print("\nTotal sessions:", len(sessions))
        print("Total image records:", len(images))

        # Count images per session.
        images_per_session = Counter(
            image["quote_session_id"] for image in images
        )

        sessions_with_images = sum(
            1 for session in sessions
            if images_per_session[session["id"]] > 0
        )

        print("Sessions with images:", sessions_with_images)
        print(
            "Sessions without images:",
            len(sessions) - sessions_with_images,
        )

        print_counter(
            "Session statuses:",
            Counter(session["status"] for session in sessions),
        )

        print_counter(
            "Detected categories:",
            Counter(
                session["detected_category"] or "(missing)"
                for session in sessions
            ),
        )

        print_counter(
            "Image storage disks:",
            Counter(image["disk"] or "(missing)" for image in images),
        )

        print_counter(
            "Images per session:",
            Counter(images_per_session.values()),
        )

        # Check availability of structured fields.
        fields = [
            "detected_category",
            "category_id",
            "task_level",
            "task_level_id",
            "estimated_hours",
            "estimated_price",
            "estimated_price_min",
            "estimated_price_max",
            "estimated_total",
            "estimated_total_min",
            "estimated_total_max",
            "service_fee",
            "hst",
        ]

        print("\nField availability:")
        print("(Non-null values out of all sessions)")

        for field in fields:
            available = sum(
                1 for session in sessions
                if session.get(field) is not None
            )

            print(
                f"  {field:<30} "
                f"{available}/{len(sessions)}"
            )

        # Inspect JSON validity and structure.
        message_valid = 0
        message_invalid = 0
        quote_valid = 0
        quote_invalid = 0

        message_roles = Counter()
        message_structures = Counter()
        quote_structures = Counter()
        quote_keys = Counter()

        for session in sessions:
            messages_raw = session.get("openai_messages")
            quote_raw = session.get("final_quote")

            messages = parse_json(messages_raw)
            quote = parse_json(quote_raw)

            if messages is not None:
                message_valid += 1
                description = describe_structure(messages)
                message_structures[description["type"]] += 1
                message_roles.update(count_message_roles(messages))
            elif messages_raw:
                message_invalid += 1

            if quote is not None:
                quote_valid += 1
                description = describe_structure(quote)
                quote_structures[description["type"]] += 1

                if isinstance(quote, dict):
                    quote_keys.update(quote.keys())
            elif quote_raw:
                quote_invalid += 1

        print("\nJSON parsing results:")
        print("Valid openai_messages:", message_valid)
        print("Non-empty invalid openai_messages:", message_invalid)
        print("Valid final_quote:", quote_valid)
        print("Non-empty invalid final_quote:", quote_invalid)

        print_counter("openai_messages structures:", message_structures)
        print_counter("final_quote structures:", quote_structures)
        print_counter("Recognized message roles:", message_roles)
        print_counter("Top-level final_quote keys:", quote_keys)

        # Print one structural example without customer text.
        for session in sessions:
            messages = parse_json(session.get("openai_messages"))
            quote = parse_json(session.get("final_quote"))

            if messages is not None or quote is not None:
                print("\nExample session ID:", session["id"])

                print(
                    "openai_messages structure:",
                    json.dumps(
                        describe_structure(messages),
                        ensure_ascii=False,
                    ),
                )

                print(
                    "final_quote structure:",
                    json.dumps(
                        describe_structure(quote),
                        ensure_ascii=False,
                    ),
                )

                break

        print("\nAudit complete. No database records were modified.")

    except Exception as exc:
        print("\nAudit failed:", str(exc))

    finally:
        if connection:
            connection.close()


if __name__ == "__main__":
    main()