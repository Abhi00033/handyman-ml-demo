
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

BASELINE_FILE = (
    ROOT / "datasets" / "prepared"
    / "clean_duration_baseline_by_category.csv"
)

MIN_CATEGORY_SAMPLES = 5


def normalize_text(value):
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def normalize_category_id(value):
    if value is None:
        return ""
    value = str(value).strip()
    if value.endswith(".0"):
        value = value[:-2]
    return value


def load_baseline():
    if not BASELINE_FILE.exists():
        raise FileNotFoundError(
            f"Clean duration baseline not found: {BASELINE_FILE}\n"
            "Run: python -m scripts.data.build_clean_duration_baseline"
        )

    df = pd.read_csv(BASELINE_FILE)

    required = {
        "category_id",
        "category",
        "sample_count",
        "median_hours",
        "p75_hours",
        "data_quality",
    }

    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Baseline is missing required columns: {sorted(missing)}"
        )

    df["category_id_key"] = df["category_id"].apply(
        normalize_category_id
    )
    df["category_name_key"] = df["category"].apply(normalize_text)

    return df


def estimate_duration(category_id, category_name, task_title=None):
    """
    Estimate historical quoted hours for a category.

    This does not predict verified actual labour duration.
    task_title is accepted for future task-level improvements,
    but this category-only version does not use it.
    """
    category_id_key = normalize_category_id(category_id)
    category_name_key = normalize_text(category_name)

    if not category_id_key or not category_name_key:
        return {
            "status": "manual_review",
            "message": "Category ID and category name are required.",
            "category_id": category_id_key or None,
            "category": category_name or None,
            "task_title": task_title,
            "estimated_hours": None,
            "conservative_hours": None,
            "sample_count": 0,
            "estimate_source": None,
        }

    baseline = load_baseline()

    matches = baseline[
        (baseline["category_id_key"] == category_id_key)
        & (baseline["category_name_key"] == category_name_key)
    ]

    if matches.empty:
        same_id = baseline[
            baseline["category_id_key"] == category_id_key
        ]

        if not same_id.empty:
            message = (
                "The category ID exists, but its name does not match "
                "the baseline. Verify the category mapping."
            )
            status = "category_mapping_review"
        else:
            message = (
                "No historical baseline exists for this category. "
                "Collect more examples or estimate manually."
            )
            status = "no_baseline"

        return {
            "status": status,
            "message": message,
            "category_id": category_id_key,
            "category": category_name,
            "task_title": task_title,
            "estimated_hours": None,
            "conservative_hours": None,
            "sample_count": 0,
            "estimate_source": None,
        }

    row = matches.iloc[0]
    sample_count = int(row["sample_count"])

    if (
        sample_count < MIN_CATEGORY_SAMPLES
        or str(row["data_quality"]) == "low_data_manual_review"
    ):
        return {
            "status": "low_data",
            "message": (
                "Too few historical examples for a dependable "
                "category estimate. Use manual review."
            ),
            "category_id": category_id_key,
            "category": category_name,
            "task_title": task_title,
            "estimated_hours": None,
            "conservative_hours": None,
            "sample_count": sample_count,
            "estimate_source": "category_baseline_insufficient_data",
        }

    median = pd.to_numeric(row["median_hours"], errors="coerce")
    p75 = pd.to_numeric(row["p75_hours"], errors="coerce")

    if pd.isna(median) or pd.isna(p75) or median <= 0 or p75 <= 0:
        return {
            "status": "manual_review",
            "message": "Baseline values are missing or invalid.",
            "category_id": category_id_key,
            "category": category_name,
            "task_title": task_title,
            "estimated_hours": None,
            "conservative_hours": None,
            "sample_count": sample_count,
            "estimate_source": "invalid_category_baseline",
        }

    return {
        "status": "preliminary_estimate",
        "message": (
            "Based on historical quoted hours for this category. "
            "Job complexity may differ; verify before using in a quote."
        ),
        "category_id": category_id_key,
        "category": category_name,
        "task_title": task_title,
        "estimated_hours": round(float(median), 2),
        "conservative_hours": round(float(p75), 2),
        "sample_count": sample_count,
        "estimate_source": "clean_category_median_and_p75",
    }


if __name__ == "__main__":
    examples = [
        ("1", "Plumbing"),
        ("3", "Home Repairs"),
        ("17", "Home Service"),
        ("17", "Home Improvement"),
        ("2", "Home Improving"),
        ("7", "HVAC"),
        ("6", "Appliance Services"),
        ("999", "Unknown Category"),
        ("17", "Incorrect Category Name"),
    ]

    for category_id, category_name in examples:
        print(
            estimate_duration(
                category_id=category_id,
                category_name=category_name,
            )
        )
