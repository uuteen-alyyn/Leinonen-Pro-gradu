import json
from pathlib import Path
import statistics

PATH = Path("merged_for_app.jsonl")  # adjust path if needed

downloads = []
missing = 0
total = 0

with PATH.open("r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue

        total += 1
        row = json.loads(line)

        d = (
            (row.get("metadata") or {})
            .get("article", {})
            .get("downloads")
        )

        if isinstance(d, (int, float)):
            downloads.append(d)
        else:
            missing += 1

n = len(downloads)

print(f"Total articles in dataset: {total}")
print(f"Articles with valid downloads: {n}")
print(f"Articles ignored (missing downloads): {missing}")

if n > 0:
    mean_downloads = sum(downloads) / n
    median_downloads = statistics.median(downloads)

    print(f"Mean downloads: {mean_downloads:.2f}")
    print(f"Median downloads: {median_downloads}")
else:
    print("No valid download data found.")
