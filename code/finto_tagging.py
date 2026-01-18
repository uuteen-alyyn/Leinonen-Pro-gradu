import json
import requests
from tqdm import tqdm
from pathlib import Path

# -------- CONFIG --------
INPUT_PATH = "articles_translated_en.jsonl"
OUTPUT_PATH = "out/finto_tags_en.jsonl"

FINTO_PROJECT = "yso-en"
API_URL = f"https://ai.finto.fi/v1/projects/{FINTO_PROJECT}/suggest"

TOP_K = 8
THRESHOLD = 0.1
LANGUAGE = "en"

# Be polite to the API
REQUEST_DELAY_SEC = 0.2
# ------------------------


def load_articles(path):
    articles = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            articles.append(json.loads(line))
    return articles


def suggest_tags(text):
    response = requests.post(
        API_URL,
        data={
            "text": text,
            "limit": TOP_K,
            "threshold": THRESHOLD,
            "language": LANGUAGE,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json().get("results", [])


def main():
    Path(OUTPUT_PATH).parent.mkdir(parents=True, exist_ok=True)

    articles = load_articles(INPUT_PATH)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as out:
        for art in tqdm(articles, desc="Finto tagging"):
            article_id = art["id"]

            # Combine title + abstract (this matters!)
            text = (
                (art.get("title_en") or "")
                + "\n\n"
                + (art.get("abstract_en") or "")
            ).strip()

            if not text:
                continue

            try:
                tags = suggest_tags(text)
            except Exception as e:
                print(f"Error on {article_id}: {e}")
                continue

            record = {
                "id": article_id,
                "tags": [
                    {
                        "label": t["label"],
                        "uri": t["uri"],
                        "score": round(float(t["score"]), 4),
                    }
                    for t in tags
                ],
            }

            out.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"\nSaved Finto tags to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()


