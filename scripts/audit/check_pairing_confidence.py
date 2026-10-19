
import csv
from collections import Counter
from pathlib import Path

csv_path = Path("datasets/prepared/question_answer_pairs.csv")

with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
    rows = list(csv.DictReader(file))

print("Rows:", len(rows))
print("\nFirst 5 confidence values and comparisons:")

for row in rows[:5]:
    raw = row.get("pairing_confidence")
    confidence = str(raw or "").strip().lower()

    print("Raw:", repr(raw))
    print("Normalized:", repr(confidence))
    print(
        "Sequence match:",
        confidence == "sequence_based_not_verified",
    )
    print(
        "Ambiguous match:",
        confidence == "ambiguous_multiple_questions",
    )
    print("-" * 40)

print("\nConfidence counts:")

counts = Counter(
    str(row.get("pairing_confidence") or "").strip().lower()
    for row in rows
)

for value, count in counts.items():
    print(repr(value), count)
