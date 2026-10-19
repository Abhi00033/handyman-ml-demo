
from db import get_connection

tables = [
    "categories",
    "services",
    "category_levels",
    "quote_sessions",
    "quote_session_images",
    "quote_enquiries",
]

connection = get_connection()

try:
    with connection.cursor() as cursor:
        for table in tables:
            print(f"\n--- {table} ---")

            try:
                cursor.execute(f"SHOW COLUMNS FROM `{table}`")

                for row in cursor.fetchall():
                    if isinstance(row, dict):
                        print(row)
                    else:
                        print(
                            f"{row[0]} | {row[1]} | "
                            f"nullable={row[2]}"
                        )

            except Exception as error:
                print(f"Could not inspect table: {error}")
finally:
    connection.close()
