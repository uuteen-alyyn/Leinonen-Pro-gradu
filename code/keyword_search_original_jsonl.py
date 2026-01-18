import json
import re
from collections import defaultdict
from pathlib import Path

# ======= EDIT THESE PATHS IF NEEDED =======
ARTICLES_JSONL = "articles_flat.jsonl"  # original reformatted file
OUT_JSON = "out/manual_keyword_hits.json"
OUT_CSV = "out/manual_keyword_hits.csv"
# =========================================

def safe_get_title_abstract(obj: dict) -> tuple[str, str]:
    """
    Tries several likely layouts:
    - flat: obj["title"], obj["abstract"]
    - nested: obj["metadata"]["article"]["title"], obj["metadata"]["article"]["abstract"]
    - fallback: empty strings
    """
    title = obj.get("title", "")
    abstract = obj.get("abstract", "")

    if not title or not abstract:
        md = obj.get("metadata", {})
        art = md.get("article", {}) if isinstance(md, dict) else {}
        title = title or art.get("title", "")
        abstract = abstract or art.get("abstract", "")

    return title or "", abstract or ""

def compile_patterns(variants: list[str]) -> list[re.Pattern]:
    """
    Compile regex patterns for each variant.
    - Case-insensitive for Latin text
    - Simple substring match with escaping (safe)
    """
    pats = []
    for v in variants:
        v = v.strip()
        if not v:
            continue
        pats.append(re.compile(v, flags=re.IGNORECASE))
    return pats

def main():
    # Concepts -> variants to search (Chinese + English variants)
    CONCEPTS = {
        "BRI_Belt_and_Road": [
            "一带一路倡议", "一带一路", "BRI", "Belt and Road Initiative", "Belt and Road",
        ],
        "BRICS": [
            "金砖国家", "金砖", "BRICS", "BRICS countries",
        ],
        "SCO_Shanghai_Cooperation_Organization": [
            "上海合作组织", "上合组织", "SCO", "Shanghai Cooperation Organization",
        ],
        "NATO": [
            "北约", "北大西洋公约组织", "NATO",
        ],
        "Ukraine": [
            "乌克兰", "Ukraine",
        ],
        "Artificial_Intelligence": [
            "人工智能",
            r"\bAI\b",
            "artificial intelligence",
        ],
        "Finland": [
            "芬兰", "Finland", "Finnish",
        ],
    }

    compiled = {k: compile_patterns(vs) for k, vs in CONCEPTS.items()}
    hits = defaultdict(list)

    total = 0
    with open(ARTICLES_JSONL, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            doc_id = obj.get("id")
            if not doc_id:
                continue

            title, abstract = safe_get_title_abstract(obj)
            text = f"{title}\n{abstract}"
            total += 1

            for concept, patterns in compiled.items():
                if any(p.search(text) for p in patterns):
                    hits[concept].append(doc_id)

    # Build summary output
    out = {
        "source_file": ARTICLES_JSONL,
        "num_articles_scanned": total,
        "results": {
            concept: {"count": len(ids), "ids": ids}
            for concept, ids in hits.items()
        }
    }

    Path(OUT_JSON).parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # Optional: write long CSV for easy analysis
    with open(OUT_CSV, "w", encoding="utf-8") as f:
        f.write("concept,id\n")
        for concept, ids in hits.items():
            for doc_id in ids:
                f.write(f"{concept},{doc_id}\n")

    print("✅ Done.")
    print("Scanned:", total)
    for concept in CONCEPTS:
        print(f"{concept}: {len(hits.get(concept, []))}")
    print("Wrote:", OUT_JSON)
    print("Wrote:", OUT_CSV)

if __name__ == "__main__":
    main()

