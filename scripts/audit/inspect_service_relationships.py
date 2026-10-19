
from pathlib import Path

from db import get_connection

ROOT = Path(__file__).resolve().parents[2]


def main():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            # Find tables that may contain service/category mappings.
            cursor.execute("""
                SELECT
                    TABLE_NAME,
                    COLUMN_NAME,
                    COLUMN_TYPE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                  AND (
                      COLUMN_NAME LIKE '%categor%'
                      OR COLUMN_NAME LIKE '%service%'
                      OR COLUMN_NAME LIKE '%task%'
                  )
                ORDER BY TABLE_NAME, ORDINAL_POSITION
            """)

            columns = cursor.fetchall()

            # Find declared foreign-key relationships.
            cursor.execute("""
                SELECT
                    TABLE_NAME,
                    COLUMN_NAME,
                    CONSTRAINT_NAME,
                    REFERENCED_TABLE_NAME,
                    REFERENCED_COLUMN_NAME
                FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA = DATABASE()
                  AND REFERENCED_TABLE_NAME IS NOT NULL
                ORDER BY TABLE_NAME, COLUMN_NAME
            """)

            foreign_keys = cursor.fetchall()

            # Find tables whose names suggest mapping relationships.
            cursor.execute("""
                SELECT TABLE_NAME
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = DATABASE()
                  AND TABLE_TYPE = 'BASE TABLE'
                  AND (
                      TABLE_NAME LIKE '%categor%'
                      OR TABLE_NAME LIKE '%service%'
                      OR TABLE_NAME LIKE '%task%'
                      OR TABLE_NAME LIKE '%pivot%'
                  )
                ORDER BY TABLE_NAME
            """)

            tables = cursor.fetchall()

    finally:
        connection.close()

    print("\n" + "=" * 70)
    print("POSSIBLE CATEGORY / SERVICE / TASK COLUMNS")
    print("=" * 70)

    for row in columns:
        print(
            f"{row['TABLE_NAME']}.{row['COLUMN_NAME']} "
            f"({row['COLUMN_TYPE']})"
        )

    print("\n" + "=" * 70)
    print("FOREIGN KEY RELATIONSHIPS")
    print("=" * 70)

    if foreign_keys:
        for row in foreign_keys:
            print(
                f"{row['TABLE_NAME']}.{row['COLUMN_NAME']} -> "
                f"{row['REFERENCED_TABLE_NAME']}."
                f"{row['REFERENCED_COLUMN_NAME']}"
            )
    else:
        print("No declared foreign keys found.")

    print("\n" + "=" * 70)
    print("POSSIBLE RELATED TABLES")
    print("=" * 70)

    for row in tables:
        print(row["TABLE_NAME"])


if __name__ == "__main__":
    main()
