from db import get_connection

EXPECTED_TABLES = [
    "quote_sessions",
    "quote_session_images",
]

SESSION_FIELDS = [
    "id",
    "status",
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
    "created_at",
]

IMAGE_FIELDS = [
    "id",
    "quote_session_id",
    "path",
    "disk",
]


def inspect_table(cursor, table_name):
    cursor.execute(
        """
        SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION
        """,
        (table_name,),
    )

    columns = cursor.fetchall()

    if not columns:
        print(f"\nTable not found: {table_name}")
        return []

    print(f"\n{'=' * 65}")
    print(f"TABLE: {table_name}")
    print(f"{'=' * 65}")

    for column in columns:
        print(
            f"{column['COLUMN_NAME']:<35} "
            f"{column['DATA_TYPE']:<18} "
            f"Nullable: {column['IS_NULLABLE']}"
        )

    cursor.execute(f"SELECT COUNT(*) AS total FROM `{table_name}`")
    print("Total records:", cursor.fetchone()["total"])

    return [column["COLUMN_NAME"] for column in columns]


def preview_records(cursor, table_name, available_columns, fields):
    selected = [field for field in fields if field in available_columns]

    if not selected:
        print(f"No preview fields available for {table_name}.")
        return

    # Column names come only from the inspected database schema
    select_columns = ", ".join(f"`{field}`" for field in selected)

    cursor.execute(
        f"SELECT {select_columns} FROM `{table_name}` LIMIT 5"
    )

    print(f"\nSample records from {table_name}:")

    for row in cursor.fetchall():
        print(row)


def main():
    connection = None

    try:
        connection = get_connection()

        with connection.cursor() as cursor:
            print("Connected to:", connection.db.decode()
                  if isinstance(connection.db, bytes)
                  else connection.db)

            existing_tables = {}

            for table in EXPECTED_TABLES:
                existing_tables[table] = inspect_table(cursor, table)

            if existing_tables.get("quote_sessions"):
                preview_records(
                    cursor,
                    "quote_sessions",
                    existing_tables["quote_sessions"],
                    SESSION_FIELDS,
                )

            if existing_tables.get("quote_session_images"):
                preview_records(
                    cursor,
                    "quote_session_images",
                    existing_tables["quote_session_images"],
                    IMAGE_FIELDS,
                )

    except Exception as exc:
        print("\nDatabase inspection failed:", str(exc))

    finally:
        if connection:
            connection.close()


if __name__ == "__main__":
    main()