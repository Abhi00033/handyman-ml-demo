
import csv
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


# --------------------------------------------------
# PROJECT PATHS
# --------------------------------------------------

ROOT = Path(__file__).resolve().parent

PIPELINE = (
    ROOT
    / "scripts"
    / "data"
    / "rebuild_duration_pipeline.py"
)

OUTPUTS = [
    ROOT / "datasets" / "reports" / "automatic_category_mapping_report.csv",
    ROOT / "datasets" / "prepared" / "automatically_clean_duration_dataset.csv",
    ROOT / "datasets" / "prepared" / "automatically_clean_duration_baseline.csv",
    ROOT / "datasets" / "reports" / "automatic_duration_exclusions.csv",
    ROOT / "datasets" / "reports" / "automatic_duration_pipeline_summary.csv",
]

BASELINE_PATH = (
    ROOT
    / "datasets"
    / "prepared"
    / "automatically_clean_duration_baseline.csv"
)

BASELINE_REQUIRED_COLUMNS = {
    "category_id",
    "sample_count",
    "median_hours",
    "p75_hours",
}


# --------------------------------------------------
# CSV HELPERS
# --------------------------------------------------

def read_csv(path):
    """Read a CSV and return its columns and rows."""

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        reader = csv.DictReader(file)

        if not reader.fieldnames:
            raise ValueError(
                f"CSV has no header: {path}"
            )

        return reader.fieldnames, list(reader)


# --------------------------------------------------
# VALIDATE GENERATED OUTPUTS
# --------------------------------------------------

def validate_outputs():
    """Validate the refreshed files before accepting them."""

    print("\nValidating generated files...")

    for path in OUTPUTS:
        if not path.is_file():
            raise ValueError(
                f"Expected output file was not generated: {path}"
            )

        if path.stat().st_size == 0:
            raise ValueError(
                f"Generated output is empty: {path}"
            )

    baseline_columns, baseline_rows = read_csv(
        BASELINE_PATH
    )

    missing_columns = (
        BASELINE_REQUIRED_COLUMNS
        - set(baseline_columns)
    )

    if missing_columns:
        raise ValueError(
            "Duration baseline is missing required columns: "
            f"{sorted(missing_columns)}"
        )

    if not baseline_rows:
        raise ValueError(
            "The refreshed duration baseline contains no categories."
        )

    # Validate every category's numerical values.
    usable_categories = 0

    for row in baseline_rows:
        category_id = row.get("category_id")

        try:
            sample_count_value = float(
                row["sample_count"]
            )
            sample_count = int(sample_count_value)

            median_hours = float(
                row["median_hours"]
            )

            p75_hours = float(
                row["p75_hours"]
            )

        except (TypeError, ValueError, KeyError):
            raise ValueError(
                "Invalid numeric baseline values for category "
                f"{category_id}: {row}"
            )

        if (
            sample_count_value != sample_count
            or sample_count < 1
        ):
            raise ValueError(
                f"Invalid sample count for category {category_id}."
            )

        if not (
            0 < median_hours <= 100
            and 0 < p75_hours <= 100
        ):
            raise ValueError(
                f"Invalid duration values for category {category_id}: "
                f"median={median_hours}, p75={p75_hours}"
            )

        if p75_hours < median_hours:
            raise ValueError(
                f"P75 is below the median for category {category_id}."
            )

        if sample_count >= 5:
            usable_categories += 1

    if usable_categories == 0:
        raise ValueError(
            "No category has at least five historical samples. "
            "The refreshed baseline will not be accepted."
        )

    # Confirm that the pipeline produced one summary row.
    _, summary_rows = read_csv(
        OUTPUTS[4]
    )

    if len(summary_rows) != 1:
        raise ValueError(
            "Expected exactly one pipeline summary row."
        )

    print(
        f"Baseline categories: {len(baseline_rows)}"
    )

    print(
        "Categories with at least five samples: "
        f"{usable_categories}"
    )

    print("All output validation checks passed.")


# --------------------------------------------------
# BACKUP HELPERS
# --------------------------------------------------

def create_backup():
    """Back up existing outputs before running the pipeline."""

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup_dir = (
        ROOT
        / "datasets"
        / "backups"
        / f"duration_refresh_{timestamp}"
    )

    backup_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    previous_files = {}

    for path in OUTPUTS:
        previous_files[path] = path.exists()

        if path.exists():
            shutil.copy2(
                path,
                backup_dir / path.name,
            )

    return backup_dir, previous_files


def restore_backup(backup_dir, previous_files):
    """Restore the original output files after a failed refresh."""

    for path in OUTPUTS:
        backup_path = backup_dir / path.name

        if previous_files[path]:
            if not backup_path.is_file():
                raise RuntimeError(
                    f"Cannot restore missing backup: {backup_path}"
                )

            shutil.copy2(
                backup_path,
                path,
            )

        elif path.exists():
            path.unlink()


# --------------------------------------------------
# RUN THE PIPELINE
# --------------------------------------------------

def main():
    if not PIPELINE.is_file():
        raise FileNotFoundError(
            f"Duration pipeline not found: {PIPELINE}"
        )

    print("=" * 60)
    print("STAR HANDYMAN - DURATION DATA REFRESH")
    print("=" * 60)

    # Create backups before running anything that generates outputs.
    backup_dir, previous_files = create_backup()

    print("\nPrevious outputs backed up to:")
    print(backup_dir)

    try:
        print("\nRunning the duration pipeline...")
        print("Reading the current database through db.py.")

        # Ensure the child process can import db.py from the
        # project root, even though the pipeline is in scripts/data.
        env = os.environ.copy()

        existing_pythonpath = env.get(
            "PYTHONPATH",
            "",
        )

        env["PYTHONPATH"] = (
            str(ROOT)
            if not existing_pythonpath
            else str(ROOT)
            + os.pathsep
            + existing_pythonpath
        )

        result = subprocess.run(
            [
                sys.executable,
                str(PIPELINE),
            ],
            cwd=str(ROOT),
            env=env,
            check=False,
        )

        if result.returncode != 0:
            raise RuntimeError(
                "Duration pipeline failed with exit code "
                f"{result.returncode}."
            )

        # Only accept outputs after the validation succeeds.
        validate_outputs()

        print("\n" + "=" * 60)
        print("DURATION DATA REFRESH SUCCESSFUL")
        print("=" * 60)

        print("\nUpdated baseline:")
        print(BASELINE_PATH)

        print("\nBackup retained at:")
        print(backup_dir)

        print(
            "\nNote: this refresh rebuilds duration datasets. "
            "It does not train an ML model."
        )

    except Exception as error:
        print("\n" + "=" * 60)
        print("DURATION DATA REFRESH FAILED")
        print("=" * 60)

        print(f"\nReason: {error}")
        print("\nRestoring previous output files...")

        try:
            restore_backup(
                backup_dir,
                previous_files,
            )

            print(
                "Rollback completed. Previous outputs were restored."
            )

        except Exception as rollback_error:
            print(
                "CRITICAL: automatic rollback was incomplete."
            )
            print(
                f"Rollback error: {rollback_error}"
            )
            print(
                f"Check the backup folder manually: {backup_dir}"
            )

        print(f"\nBackup location: {backup_dir}")

        raise SystemExit(1)


if __name__ == "__main__":
    main()
