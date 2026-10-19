
import os
import csv
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

from db import get_connection

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

BUCKET = os.getenv("AWS_BUCKET")
REGION = os.getenv("AWS_DEFAULT_REGION")

if not BUCKET or not REGION:
    raise RuntimeError(
        "AWS_BUCKET or AWS_DEFAULT_REGION is missing from .env"
    )

s3 = boto3.client("s3", region_name=REGION)


OUTPUT_DIR = PROJECT_ROOT / "datasets" / "s3_verified_images"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MANIFEST_PATH = PROJECT_ROOT / "datasets" / "s3_verification_manifest.csv"
MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_image_records():
    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT id, disk, path
                FROM quote_session_images
                ORDER BY id
            """)
            return cursor.fetchall()
    finally:
        connection.close()


def check_s3_key(key):
    """Check whether an exact object key exists in the bucket."""
    try:
        response = s3.head_object(Bucket=BUCKET, Key=key)
        return True, response.get("ContentLength"), response.get("ContentType")

    except ClientError as exc:
        status = exc.response.get("ResponseMetadata", {}).get(
            "HTTPStatusCode"
        )
        code = exc.response.get("Error", {}).get("Code", "")

        if status == 404 or code in ("404", "NoSuchKey", "NotFound"):
            return False, None, None

        raise


records = get_image_records()

if not records:
    print("No image records found.")
    raise SystemExit(0)

# Support both dictionary cursors and tuple rows.
if not isinstance(records[0], dict):
    raise RuntimeError(
        "db.py must return dictionary rows for this script. "
        "Check its cursor configuration."
    )

print(f"Database image records: {len(records)}")
print(f"AWS bucket: {BUCKET}")
print(f"AWS region: {REGION}")
print("-" * 70)

manifest_rows = []
found_count = 0
missing_count = 0
downloaded_count = 0

for record in records:
    image_id = record.get("id")
    disk = record.get("disk")
    db_path = record.get("path")

    if not db_path:
        print(f"ID {image_id}: missing database path")
        manifest_rows.append({
            "image_id": image_id,
            "disk": disk,
            "database_path": "",
            "s3_key": "",
            "exists_in_s3": False,
            "size_bytes": "",
            "content_type": "",
            "downloaded_file": "",
            "error": "Missing database path",
        })
        missing_count += 1
        continue

    # Test the exact path stored in the database.
    # Do not prepend "public/" or guess other prefixes.
    key = str(db_path).lstrip("/")

    try:
        exists, size, content_type = check_s3_key(key)

        local_file = ""

        if exists:
            found_count += 1
            print(
                f"[FOUND] ID={image_id} | disk={disk} | "
                f"key={key} | size={size} bytes"
            )

            # Download confirmed S3-disk images for visual inspection.
            if disk == "s3":
                extension = Path(key).suffix or ".img"
                destination = OUTPUT_DIR / f"image_{image_id}{extension}"

                s3.download_file(BUCKET, key, str(destination))
                local_file = str(destination)
                downloaded_count += 1
        else:
            missing_count += 1
            print(
                f"[NOT FOUND] ID={image_id} | disk={disk} | key={key}"
            )

        manifest_rows.append({
            "image_id": image_id,
            "disk": disk,
            "database_path": db_path,
            "s3_key": key,
            "exists_in_s3": exists,
            "size_bytes": size or "",
            "content_type": content_type or "",
            "downloaded_file": local_file,
            "error": "",
        })

    except Exception as exc:
        print(f"[ERROR] ID={image_id} | {type(exc).__name__}: {exc}")
        manifest_rows.append({
            "image_id": image_id,
            "disk": disk,
            "database_path": db_path,
            "s3_key": key,
            "exists_in_s3": "",
            "size_bytes": "",
            "content_type": "",
            "downloaded_file": "",
            "error": str(exc),
        })

with MANIFEST_PATH.open("w", newline="", encoding="utf-8-sig") as file:
    writer = csv.DictWriter(file, fieldnames=[
        "image_id",
        "disk",
        "database_path",
        "s3_key",
        "exists_in_s3",
        "size_bytes",
        "content_type",
        "downloaded_file",
        "error",
    ])
    writer.writeheader()
    writer.writerows(manifest_rows)

print("\n" + "=" * 70)
print("VERIFICATION SUMMARY")
print(f"Total database records: {len(records)}")
print(f"Found in S3: {found_count}")
print(f"Not found in S3: {missing_count}")
print(f"S3 images downloaded: {downloaded_count}")
print(f"Manifest: {MANIFEST_PATH.resolve()}")
print(f"Downloaded images: {OUTPUT_DIR.resolve()}")
