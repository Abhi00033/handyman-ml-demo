
from db import get_connection

TABLES = ["quote_sessions", "quote_session_images"]

def main():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            for table in TABLES:
                print(f"\n{'=' * 60}")
                print(f"TABLE: {table}")
                print("=" * 60)

                cursor.execute(f"SHOW COLUMNS FROM `{table}`")

                for column in cursor.fetchall():
                    print(
                        f"{column['Field']:<35} "
                        f"{column['Type']}"
                    )
    finally:
        connection.close()

if __name__ == "__main__":
    main()
