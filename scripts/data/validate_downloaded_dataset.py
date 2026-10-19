
import csv
import hashlib
from pathlib import Path
from collections import Counter
from PIL import Image, UnidentifiedImageError


BASE_DIR = Path(__file__).resolve().parents[2]
DATASET_DIR = BASE_DIR / "datasets"

MANIFEST_FILE = DATASET_DIR / "image_download_manifest.csv"
REPORT_FILE = DATASET_DIR / "image_validation_report.csv"


def sha256_file(path):
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def validate_image(row):
    relative_path = row.get("local_path", "").strip()
    expected_size = row.get("size_bytes", "").strip()
    expected_hash = row.get("sha256", "").strip()

    result = {
        "image_id": row.get("image_id", ""),
        "session_id": row.get("session_id", ""),
        "disk": row.get("disk", ""),
        "local_path": relative_path,
        "download_status": row.get("status", ""),
        "validation_status": "",
        "actual_size_bytes": "",
        "actual_sha256": "",
        "error": "",
    }

    try:
        if row.get("disk") != "s3":
            raise ValueError("Record is not marked as S3 storage.")

        if row.get("status") not in {
            "downloaded",
            "already_downloaded",
        }:
            raise ValueError(
                f"Download status is {row.get('status')!r}."
            )

        if not relative_path:
            raise ValueError("Local image path is empty.")

        path = (BASE_DIR / relative_path).resolve()

        # Prevent paths outside the project directory.
        if not path.is_relative_to(BASE_DIR.resolve()):
            raise ValueError("Image path points outside the project.")

        if not path.is_file():
            raise FileNotFoundError("Local image file does not exist.")

        actual_size = path.stat().st_size

        if actual_size <= 0:
            raise ValueError("Image file is empty.")

        if expected_size and actual_size != int(expected_size):
            raise ValueError(
                f"File size mismatch: expected {expected_size}, "
                f"found {actual_size}."
            )

        actual_hash = sha256_file(path)

        if expected_hash and actual_hash.lower() != expected_hash.lower():
            raise ValueError("SHA-256 does not match the manifest.")

        # Verify that the file contains a readable image.
        with Image.open(path) as img:
            img.verify()

        result.update({
            "validation_status": "valid",
            "actual_size_bytes": actual_size,
            "actual_sha256": actual_hash,
        })

    except (
        OSError,
        ValueError,
        UnidentifiedImageError,
    ) as exc:
        result["validation_status"] = "invalid"
        result["error"] = str(exc)

    return result


def main():
    if not MANIFEST_FILE.is_file():
        raise SystemExit(
            f"Manifest not found: {MANIFEST_FILE}\n"
            "Run python download_s3_images.py first."
        )

    with MANIFEST_FILE.open(
        "r", newline="", encoding="utf-8-sig"
    ) as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    if not rows:
        raise SystemExit("Manifest contains no image records.")

    # Duplicate database IDs should be investigated.
    image_ids = [
        row.get("image_id", "").strip()
        for row in rows
    ]
    duplicate_ids = [
        image_id
        for image_id, count in Counter(image_ids).items()
        if image_id and count > 1
    ]

    results = [validate_image(row) for row in rows]

    columns = [
        "image_id",
        "session_id",
        "disk",
        "local_path",
        "download_status",
        "validation_status",
        "actual_size_bytes",
        "actual_sha256",
        "error",
    ]

    with REPORT_FILE.open(
        "w", newline="", encoding="utf-8-sig"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(results)

    statuses = Counter(
        result["validation_status"] for result in results
    )

    print("\nImage validation summary")
    print("------------------------")
    print("Manifest records:", len(rows))
    print("Valid images:", statuses.get("valid", 0))
    print("Invalid images:", statuses.get("invalid", 0))
    print("Duplicate image IDs:", len(duplicate_ids))

    if duplicate_ids:
        print("Duplicate IDs:", ", ".join(duplicate_ids[:20]))

    print("\nValidation report:", REPORT_FILE)

    if statuses.get("invalid", 0) == 0 and not duplicate_ids:
        print("Result: All manifest records passed validation.")
    else:
        print("Result: Review the validation report before proceeding.")


if __name__ == "__main__":
    main()
