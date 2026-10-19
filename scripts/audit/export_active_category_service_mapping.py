
from pathlib import Path

import pandas as pd
from db import get_connection

ROOT = Path(__file__).resolve().parents[2]

OUTPUT = (
    ROOT
    / "datasets"
    / "reports"
    / "active_category_service_mapping.csv"
)


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            # 1. Read all categories
            cursor.execute("""
                SELECT
                    id,
                    name,
                    slug,
                    description,
                    is_active,
                    deleted_at
                FROM categories
                ORDER BY id
            """)

            categories = cursor.fetchall()

            # 2. Read all services
            cursor.execute("""
                SELECT
                    id,
                    name,
                    slug,
                    category_id,
                    price,
                    duration_minutes,
                    description,
                    service_type,
                    min_charge,
                    visit_charge,
                    included_items,
                    exclusions
                FROM services
                ORDER BY id
            """)

            services = cursor.fetchall()

            # 3. Inspect raw category_id values
            cursor.execute("""
                SELECT
                    category_id,
                    COUNT(*) AS total
                FROM services
                GROUP BY category_id
                ORDER BY total DESC
            """)

            category_counts = cursor.fetchall()

            # 4. Inspect a sample of service records
            cursor.execute("""
                SELECT
                    id,
                    name,
                    category_id,
                    category_id IS NULL AS is_null
                FROM services
                ORDER BY id
                LIMIT 30
            """)

            sample_services = cursor.fetchall()

            # 5. Inspect the services table schema
            cursor.execute("SHOW COLUMNS FROM services")
            service_columns = cursor.fetchall()

    finally:
        connection.close()

    # Convert database results to DataFrames
    category_df = pd.DataFrame(categories)
    service_df = pd.DataFrame(services)

    print("\n" + "=" * 70)
    print("CATEGORIES")
    print("=" * 70)

    if not category_df.empty:
        print(
            category_df[
                ["id", "name", "slug", "is_active", "deleted_at"]
            ].to_string(index=False)
        )
    else:
        print("No categories found.")

    print("\n" + "=" * 70)
    print("RAW SERVICE CATEGORY ID COUNTS")
    print("=" * 70)

    for row in category_counts:
        print(row)

    print("\n" + "=" * 70)
    print("FIRST 30 SERVICES")
    print("=" * 70)

    for row in sample_services:
        print(row)

    print("\n" + "=" * 70)
    print("SERVICES TABLE COLUMNS")
    print("=" * 70)

    for column in service_columns:
        print(
            f"Field: {column.get('Field')}, "
            f"Type: {column.get('Type')}, "
            f"Null: {column.get('Null')}, "
            f"Key: {column.get('Key')}"
        )

    # Preserve original values for the CSV.
    # Convert IDs to strings only in copies used for joining.
    if not category_df.empty and not service_df.empty:
        category_df["category_join_id"] = (
            category_df["id"].astype("string")
        )

        service_df["category_join_id"] = (
            service_df["category_id"].astype("string")
        )

        mapping = service_df.merge(
            category_df,
            left_on="category_join_id",
            right_on="category_join_id",
            how="left",
            suffixes=("_service", "_category"),
            indicator=True,
        )

        mapping["category_mapping_status"] = mapping["_merge"].map({
            "both": "matched_category",
            "left_only": "unmatched_or_missing_category",
            "right_only": "category_without_service",
        })

        mapping.drop(columns=["_merge"], inplace=True)

    elif not service_df.empty:
        mapping = service_df.copy()
        mapping["category_mapping_status"] = (
            "categories_table_empty"
        )

    else:
        mapping = pd.DataFrame()

    mapping.to_csv(
        OUTPUT,
        index=False,
        encoding="utf-8-sig",
    )

    print("\n" + "=" * 70)
    print("MAPPING SUMMARY")
    print("=" * 70)

    print(f"Categories found: {len(categories)}")
    print(f"Services found: {len(services)}")

    if not mapping.empty:
        print("\nMapping status:")
        print(
            mapping["category_mapping_status"]
            .value_counts(dropna=False)
            .to_string()
        )

    print(f"\nCSV report saved to:\n{OUTPUT}")


if __name__ == "__main__":
    main()
