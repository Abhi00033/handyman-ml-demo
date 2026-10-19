
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE_DIR))

from db import get_connection


def main():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW TABLES")
            rows = cursor.fetchall()

        print("Tables in the connected database:\n")

        for row in rows:
            print(next(iter(row.values())))

    finally:
        connection.close()


if __name__ == "__main__":
    main()
