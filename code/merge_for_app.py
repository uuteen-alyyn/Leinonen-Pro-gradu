import json
import os
from typing import Dict, Any, List, Set, Tuple

ARTICLES_JSONL = "articles_flat.jsonl"

TRANSLATED_JSONL = "articles_translated_en.jsonl"  # adjust if needed
FINTO_TAGS_JSONL = "out/finto_tags_en.jsonl"

# CLUSTERS_JSON = "out/cluster_labels_leaf_epsilon 0.55.json"  # your main run
CLUSTER_RUNS = {
    "eom":       "out/cluster_labels_eom.json",
    "leaf":      "out/cluster_labels_leaf.json",
    "leaf_0.5":  "out/cluster_labels_leaf_epsilon 0.5.json",
    "leaf_0.55": "out/cluster_labels_leaf_epsilon 0.55.json",
    "leaf_0.6":  "out/cluster_labels_leaf_epsilon 0.6.json",
}
MANUAL_HITS_JSON = "out/manual_keyword_hits.json"

OUT_JSONL = "out/merged_for_app.jsonl"


def safe_jsonl_iter(path: str):
    """Yield parsed JSON objects from a JSONL file, skipping blank/broken lines."""
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # Sometimes a file may contain stray "{" lines etc.
                # Skip them safely instead of crashing.
                continue


def load_translation_by_id(path: str) -> Dict[str, Dict[str, Any]]:
    if not os.path.exists(path):
        return {}

    out = {}
    for obj in safe_jsonl_iter(path):
        doc_id = obj.get("id")
        if not doc_id:
            continue
        out[doc_id] = obj
    return out


def load_finto_tags_by_id(path: str) -> Dict[str, List[Dict[str, Any]]]:
    if not os.path.exists(path):
        return {}

    out: Dict[str, List[Dict[str, Any]]] = {}
    for obj in safe_jsonl_iter(path):
        doc_id = obj.get("id")
        if not doc_id:
            continue
        tags = obj.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        out[doc_id] = tags
    return out


def load_clusters_by_id(path: str) -> Dict[str, int]:
    """
    Your cluster files are JSON arrays like:
    [{"id":"art_000001","cluster":-1}, ...]
    """
    if not os.path.exists(path):
        return {}

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    out: Dict[str, int] = {}
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and "id" in item and "cluster" in item:
                out[item["id"]] = int(item["cluster"])
    elif isinstance(data, dict):
        # fallback: {id: cluster}
        for k, v in data.items():
            try:
                out[str(k)] = int(v)
            except Exception:
                pass
    return out


def load_manual_hits(path: str) -> Dict[str, Set[str]]:
    """
    Supports:
    A) {"BRICS":[ids], "NATO":[ids], ...}
    B) {"source_file":..., "num_articles_scanned":..., "results": {"BRICS":[ids], ...}}
    C) [{"keyword":"BRICS","ids":[...]}, ...]  (fallback)
    Returns: {keyword: set(ids)}
    """
    if not os.path.exists(path):
        return {}

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Case B: wrapper object with "results"
    if isinstance(data, dict) and "results" in data and isinstance(data["results"], dict):
        data = data["results"]

    out: Dict[str, Set[str]] = {}

    # Case A: dict(keyword -> list_of_ids)
    # Case A: dict(keyword -> list_of_ids) OR dict(keyword -> {"count":..,"ids":[..]})
    if isinstance(data, dict):
        for kw, val in data.items():
            if isinstance(val, list):
                ids_list = val
            elif isinstance(val, dict) and isinstance(val.get("ids"), list):
                ids_list = val["ids"]
            else:
                ids_list = []
            out[str(kw)] = set(str(x) for x in ids_list)
        return out


    # Case C: list of {"keyword": "...", "ids":[...]}
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            kw = item.get("keyword") or item.get("name")
            ids = item.get("ids") or item.get("hits")
            if kw and isinstance(ids, list):
                out[str(kw)] = set(str(x) for x in ids)
        return out

    return out



def cluster_name(label: int) -> str:
    if label == -1:
        return "Noise / Unclustered"
    return f"Cluster {label}"


def main():
    translations = load_translation_by_id(TRANSLATED_JSONL)
    finto = load_finto_tags_by_id(FINTO_TAGS_JSONL)
    clusters_by_run = {run: load_clusters_by_id(path) for run, path in CLUSTER_RUNS.items()}
    manual = load_manual_hits(MANUAL_HITS_JSON)

    print("Manual keywords loaded:", len(manual))
    print("Top 10 manual keyword sizes:", sorted([(k, len(v)) for k, v in manual.items()], key=lambda x: -x[1])[:10])

    os.makedirs(os.path.dirname(OUT_JSONL), exist_ok=True)

    written = 0
    missing_cluster = 0

    with open(OUT_JSONL, "w", encoding="utf-8") as out_f:
        for art in safe_jsonl_iter(ARTICLES_JSONL):
            doc_id = art.get("id")
            if not doc_id:
                continue

            # Cluster
            clusters_payload = {}
            for run, cmap in clusters_by_run.items():
                label = cmap.get(doc_id, -1)
                clusters_payload[run] = {
                    "label": label,
                    "name": cluster_name(label),
                }


            # Manual keyword flags
            hit_keywords = []
            for kw, idset in manual.items():
                if doc_id in idset:
                    hit_keywords.append(kw)

            merged = {
                # Core identity
                "id": doc_id,

                # Original content
                "title": art.get("title", ""),
                "abstract": art.get("abstract", ""),
                "text_for_embedding": art.get("text_for_embedding", ""),

                # Original metadata (keep as-is)
                "metadata": art.get("metadata", {}),

                # English translation (whatever your translation JSONL stored)
                "translation_en": translations.get(doc_id, {}),

                # Finto tags
                "finto_tags_en": finto.get(doc_id, []),

                # Manual keyword hits
                "manual_keyword_hits": hit_keywords,

                # Cluster info (easy to rename later)
                "clusters": clusters_payload,
            }

            out_f.write(json.dumps(merged, ensure_ascii=False) + "\n")
            written += 1

    print("✅ Merge complete.")
    print(f"Wrote: {written} records -> {OUT_JSONL}")


if __name__ == "__main__":
    main()


