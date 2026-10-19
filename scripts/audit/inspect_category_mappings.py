
from db import get_connection

def main():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            print("\n=== ALL CATEGORIES ===")
            cursor.execute("""
                SELECT
                    id,
                    name,
                    slug,
                    is_active,
                    deleted_at
                FROM categories
                ORDER BY id
            """)

            for row in cursor.fetchall():
                print(row)

            print("\n=== HISTORICAL QUOTE CATEGORY MAPPINGS ===")
            cursor.execute("""
                SELECT
                    detected_category,
                    category_id,
                    COUNT(*) AS session_count,
                    SUM(
                        CASE
                            WHEN estimated_hours IS NOT NULL
                             AND estimated_price IS NOT NULL
                            THEN 1 ELSE 0
                        END
                    ) AS sessions_with_hours_and_price
                FROM quote_sessions
                WHERE deleted_at IS NULL
                GROUP BY detected_category, category_id
                ORDER BY detected_category, category_id
            """)

            for row in cursor.fetchall():
                print(row)

    finally:
        connection.close()


if __name__ == "__main__":
    main()
