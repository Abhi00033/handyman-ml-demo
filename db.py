import os

import pymysql
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    """Create a connection to the local Star Handyman MySQL database."""

    return pymysql.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "starhandyman"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=10,
        read_timeout=30,
        write_timeout=30,
    )


if __name__ == "__main__":
    try:
        connection = get_connection()

        with connection.cursor() as cursor:
            cursor.execute("SELECT DATABASE() AS database_name, VERSION() AS mysql_version")
            result = cursor.fetchone()

            print("MySQL connection successful!")
            print("Database:", result["database_name"])
            print("MySQL version:", result["mysql_version"])

        connection.close()

    except Exception as exc:
        print("MySQL connection failed.")
        print("Error:", str(exc))