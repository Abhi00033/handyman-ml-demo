
import os
import csv
import hashlib
from pathlib import Path
from urllib.parse import unquote

import boto3
from botocore.exceptions import ClientError, BotoCoreError
from dotenv import load_dotenv

from db import get_connection


# --------------------------------------------------
# 1. CONFIGURATION
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")

REGION = os.getenv("AWS_DEFAULT_REGION", "ca-central-1").strip()
BUCKET = os.getenv("AWS_BUCKET", "").strip()

ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
SESSION_TOKEN = os.getenv("AWS_SESSION_TOKEN", "").strip()

if not BUCKET:
    raise SystemExit("AWS_BUCKET is missing from .env.")

if bool(ACCESS_KEY) != bool(SECRET_KEY):
    raise SystemExit(
        "Configure both AWS_ACCESS_KEY_ID and "
        "AWS_SECRET_ACCESS_KEY, or use your AWS profile."
    )

client_options = {"region_name": REGION}

if ACCESS_KEY and SECRET_KEY:
    client_options["aws_access_key_id"] = ACCESS_KEY
    client_options["aws_secret_access_key"] = SECRET_KEY

    if SESSION_TOKEN:
        client_options["aws_session_token"] = SESSION_TOKEN

s3 = boto3.client("s3", **client_options)

DATASET_DIR = BASE_DIR / "datasets"
IMAGE_DIR = DATASET_DIR / "images"
MANIFEST_FILE = DATASET_DIR / "image_download_manifest.csv"

DATASET_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------
# 2. HELPERS
# --------------------------------------------------

def sha256_file(file_path):
    digest = hashlib.sha256()

    with open(file_path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def download_one(image):
    image_id = image["id"]
    session_id = image["quote_session_id"]
    key = unquote(str(image.get("path") or "")).lstrip("/")

    result = {
        "image_id": image_id,
        "session_id": session_id,
        "disk": image.get("disk"),
        "bucket": BUCKET,
        "s3_key": key,
        "local_path": "",
        "size_bytes": "",
        "sha256": "",
        "status": "",
        "error": "",
    }

    try:
        # Only exact S3 object keys are accepted.
        if not key or ".." in Path(key).parts:
            raise ValueError("Invalid S3 object key.")

        # Confirm that the exact object exists.
        metadata = s3.head_object(
            Bucket=BUCKET,
            Key=key,
        )

        filename = Path(key).name
        destination_dir = IMAGE_DIR / f"session_{session_id}"
        destination_dir.mkdir(parents=True, exist_ok=True)

        destination = destination_dir / f"image_{image_id}_{filename}"
        temporary = destination.with_name(destination.name + ".part")

        # Reuse only when the file size matches S3 metadata.
        if (
            destination.exists()
            and destination.stat().st_size == metadata["ContentLength"]
        ):
            status = "already_downloaded"
        else:
            destination.unlink(missing_ok=True)

            try:
                s3.download_file(BUCKET, key, str(temporary))

                if temporary.stat().st_size != metadata["ContentLength"]:
                    raise IOError("Downloaded size differs from S3 metadata.")

                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)

            status = "downloaded"

        result.update({
            "local_path": str(destination.relative_to(BASE_DIR)),
            "size_bytes": destination.stat().st_size,
            "sha256": sha256_file(destination),
            "status": status,
        })

    except (ClientError, BotoCoreError, OSError, ValueError) as exc:
        result["status"] = "failed"
        result["error"] = str(exc)

    return result


# --------------------------------------------------
# 3. DOWNLOAD VERIFIED-DISK CANDIDATES ONLY
# --------------------------------------------------

def main():
    connection = None

    try:
        print("Star Handyman — S3 image downloader")
        print("Region:", REGION)
        print("Bucket:", BUCKET)
        print("Output:", IMAGE_DIR)

        # Check bucket access before processing records.
        s3.head_bucket(Bucket=BUCKET)
        print("S3 bucket access verified.")

        connection = get_connection()

        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, quote_session_id, path, disk
                FROM quote_session_images
                WHERE disk = 's3'
                ORDER BY quote_session_id, id
            """)
            images = cursor.fetchall()

        print("Database records with disk='s3':", len(images))

        results = []

        for index, image in enumerate(images, start=1):
            result = download_one(image)
            results.append(result)

            print(
                f"[{index}/{len(images)}] "
                f"Image {image['id']} | "
                f"Session {image['quote_session_id']} | "
                f"{result['status']}"
            )

            if result["status"] == "failed":
                print("  Error:", result["error"])

        columns = [
            "image_id",
            "session_id",
            "disk",
            "bucket",
            "s3_key",
            "local_path",
            "size_bytes",
            "sha256",
            "status",
            "error",
        ]

        with MANIFEST_FILE.open(
            "w", newline="", encoding="utf-8-sig"
        ) as file:
            writer = csv.DictWriter(file, fieldnames=columns)
            writer.writeheader()
            writer.writerows(results)

        print("\nDownload summary:")
        statuses = {}

        for result in results:
            status = result["status"]
            statuses[status] = statuses.get(status, 0) + 1

        for status, count in sorted(statuses.items()):
            print(f"  {status}: {count}")

        print("\nManifest:", MANIFEST_FILE)
        print("Finished. Database and S3 objects were not modified.")

    except (ClientError, BotoCoreError) as exc:
        print("AWS error:", str(exc))
    except Exception as exc:
        print("Process failed:", str(exc))
    finally:
        if connection:
            connection.close()


if __name__ == "__main__":
    main()
