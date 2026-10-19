
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

INPUT = ROOT / "datasets" / "prepared" / "job_level_dataset.csv"
REPORTS = ROOT / "datasets" / "reports"
PREPARED = ROOT / "datasets" / "prepared"

MIN_TASK_SAMPLES = 5


def prepare_data():
    if not INPUT.exists():
        raise FileNotFoundError(
            f"Dataset not found: {INPUT}"
        )

    df = pd.read_csv(INPUT)

    required = [
        "session_id",
        "status",
        "category_id",
        "detected_category",
        "task_title",
        "estimated_hours",
    ]

    missing = [column for column in required if column not in df.columns]

    if missing:
        raise ValueError(
            f"Required columns missing from dataset: {missing}"
        )

    df["estimated_hours"] = pd.to_numeric(
        df["estimated_hours"],
        errors="coerce",
    )

    df["status"] = (
        df["status"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.lower()
    )

    df["detected_category"] = (
        df["detected_category"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    df["task_title"] = (
        df["task_title"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    df["category_id"] = (
        df["category_id"]
        .astype("string")
        .fillna("")
        .str.strip()
    )

    # Preserve source data; filter only the working copy.
    excluded_statuses = {"deleted", "rejected"}

    valid = df[
        ~df["status"].isin(excluded_statuses)
        & df["detected_category"].ne("")
        & df["category_id"].ne("")
        & df["estimated_hours"].notna()
        & df["estimated_hours"].gt(0)
        & df["estimated_hours"].le(100)
    ].copy()

    return df, valid


def summarize(grouped, keys):
    summary = (
        grouped["estimated_hours"]
        .agg(
            sample_count="count",
            average_hours="mean",
            median_hours="median",
            minimum_hours="min",
            maximum_hours="max",
            standard_deviation_hours="std",
        )
        .reset_index()
    )

    quantiles = (
        grouped["estimated_hours"]
        .quantile([0.10, 0.25, 0.75, 0.90])
        .unstack()
        .reset_index()
    )

    quantiles = quantiles.rename(
        columns={
            0.10: "p10_hours",
            0.25: "p25_hours",
            0.75: "p75_hours",
            0.90: "p90_hours",
        }
    )

    summary = summary.merge(
        quantiles,
        on=keys,
        how="left",
    )

    # Preliminary planning estimate:
    # use the median as the normal estimate and P75
    # as the more conservative estimate.
    summary["recommended_hours"] = summary["median_hours"]
    summary["conservative_hours"] = summary["p75_hours"]

    summary["variation"] = (
        summary["standard_deviation_hours"]
        / summary["average_hours"].replace(0, pd.NA)
    )

    summary["data_quality_note"] = summary["sample_count"].apply(
        lambda count: (
            "Very limited sample"
            if count < 5
            else "Preliminary estimate; verify labels"
        )
    )

    return summary.sort_values(
        ["sample_count", "median_hours"],
        ascending=[False, True],
    )


def main():
    REPORTS.mkdir(parents=True, exist_ok=True)
    PREPARED.mkdir(parents=True, exist_ok=True)

    original, valid = prepare_data()

    print("\nDURATION BASELINE BUILD")
    print("=" * 65)
    print(f"Source sessions: {len(original)}")
    print(f"Usable duration records: {len(valid)}")
    print(
        "Excluded records: "
        f"{len(original) - len(valid)}"
    )

    if valid.empty:
        print("No usable historical duration estimates found.")
        return

    # Category-level baseline.
    category_keys = [
        "category_id",
        "detected_category",
    ]

    category_summary = summarize(
        valid.groupby(category_keys, dropna=False),
        category_keys,
    )

    category_path = (
        PREPARED / "duration_baseline_by_category.csv"
    )

    category_summary.to_csv(
        category_path,
        index=False,
        encoding="utf-8-sig",
    )

    # Task-level baseline. Require enough examples before
    # recommending a task-specific estimate.
    task_data = valid[valid["task_title"].ne("")].copy()

    task_keys = [
        "category_id",
        "detected_category",
        "task_title",
    ]

    if not task_data.empty:
        task_summary = summarize(
            task_data.groupby(task_keys, dropna=False),
            task_keys,
        )

        task_summary["task_estimate_usable"] = (
            task_summary["sample_count"] >= MIN_TASK_SAMPLES
        )

        task_path = (
            PREPARED / "duration_baseline_by_task.csv"
        )

        task_summary.to_csv(
            task_path,
            index=False,
            encoding="utf-8-sig",
        )

        usable_tasks = task_summary[
            task_summary["task_estimate_usable"]
        ]

    else:
        task_summary = pd.DataFrame()
        usable_tasks = pd.DataFrame()
        task_path = PREPARED / "duration_baseline_by_task.csv"

        task_summary.to_csv(
            task_path,
            index=False,
            encoding="utf-8-sig",
        )

    print("\nCATEGORY BASELINE")
    print("-" * 65)

    preview_columns = [
        "category_id",
        "detected_category",
        "sample_count",
        "average_hours",
        "median_hours",
        "p75_hours",
        "p10_hours",
        "p90_hours",
    ]

    print(
        category_summary[preview_columns].round(2).to_string(
            index=False
        )
    )

    print("\nTASK-LEVEL SUMMARY")
    print("-" * 65)
    print(f"Tasks with titles: {len(task_summary)}")
    print(
        "Task groups with at least "
        f"{MIN_TASK_SAMPLES} examples: {len(usable_tasks)}"
    )

    print("\nReports created:")
    print(f"Category baseline: {category_path}")
    print(f"Task baseline: {task_path}")


if __name__ == "__main__":
    main()
