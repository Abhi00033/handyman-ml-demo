
import os
from pathlib import Path

import pymysql
import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def get_setting(key, default=None):
    """Read Streamlit Cloud Secrets first, then local .env variables."""
    try:
        value = st.secrets.get(key)
        if value is not None and str(value).strip():
            return value
    except Exception:
        pass

    return os.getenv(key, default)


def get_connection():
    """Connect to local MySQL or remote TiDB Cloud using TLS."""

    host = get_setting("DB_HOST", "127.0.0.1")
    port = int(get_setting("DB_PORT", "3306"))
    user = get_setting("DB_USER", "root")
    password = get_setting("DB_PASSWORD", "")
    database = get_setting("DB_NAME", "starhandyman")

    ssl_options = None

    # TiDB Cloud: use the CA certificate supplied in Streamlit Secrets.
    ca_content = get_setting("DB_SSL_CA")

    if ca_content:
        ca_path = Path("/tmp/tidb-ca.pem")
        ca_path.write_text(str(ca_content), encoding="utf-8")
        ssl_options = {
            "ca": str(ca_path),
            "check_hostname": True,
        }

    elif host != "127.0.0.1" and host != "localhost":
        raise RuntimeError(
            "Remote database requires DB_SSL_CA in Streamlit Secrets."
        )

    return pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=15,
        read_timeout=30,
        write_timeout=30,
        ssl=ssl_options,
    )


if __name__ == "__main__":
    connection = None
    try:
        connection = get_connection()
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT DATABASE() AS database_name, "
                "VERSION() AS database_version"
            )
            result = cursor.fetchone()

        print("Database connection successful!")
        print("Database:", result["database_name"])
        print("Version:", result["database_version"])

    except Exception as exc:
        print("Database connection failed:", str(exc))

    finally:
        if connection:
            connection.close()
