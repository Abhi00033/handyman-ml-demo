
from db import get_connection

TABLES = ["categories", "category_levels", "services"]

def main():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            for table in TABLES:
                print("\n" + "=" * 60)
                print(f"TABLE: {table}")
                print("=" * 60)

                cursor.execute(f"DESCRIBE `{table}`")
                columns = cursor.fetchall()

                print("\nCOLUMNS:")
                for column in columns:
                    print(f"  {column['Field']}: {column['Type']}")

                cursor.execute(f"SELECT * FROM `{table}` LIMIT 10")
                rows = cursor.fetchall()

                print("\nSAMPLE DATA:")
                for row in rows:
                    print(row)

    finally:
        connection.close()


if __name__ == "__main__":
    main()
