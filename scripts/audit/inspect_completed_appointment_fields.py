
from db import get_connection


def main():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW COLUMNS FROM appointments")
            columns = cursor.fetchall()

        print("\nAPPOINTMENTS TABLE COLUMNS")
        print("=" * 70)

        for column in columns:
            name = column["Field"]
            column_type = column["Type"]
            nullable = column["Null"]

            print(
                f"{name:<40} "
                f"{column_type:<25} "
                f"Nullable: {nullable}"
            )

        print("\nPOTENTIAL OUTCOME FIELDS")
        print("=" * 70)

        keywords = [
            "price",
            "amount",
            "total",
            "hour",
            "duration",
            "start",
            "end",
            "complete",
            "payment",
            "fee",
            "tax",
            "hst",
            "visit",
            "status",
        ]

        for column in columns:
            name = column["Field"].lower()

            if any(keyword in name for keyword in keywords):
                print(f"{column['Field']} ({column['Type']})")

    finally:
        connection.close()


if __name__ == "__main__":
    main()
