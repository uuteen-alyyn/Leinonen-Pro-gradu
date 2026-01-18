import json
from collections import Counter, defaultdict
from pathlib import Path

# ---------- CONFIG ----------
TAGS_JSONL = "out/finto_tags_en.jsonl"  # your Finto output
OUT_DIR = "out/tag_analysis"

# Use URIs as stable identifiers (recommended)
USE_URI = True

# Your existing cluster label files (edit names if needed)
CLUSTER_FILES = {
    "eom": "out/cluster_labels_eom.json",
    "leaf_eps_0_5": "out/cluster_labels_leaf_epsilon 0.5.json",
    "leaf_eps_0_6": "out/cluster_labels_leaf_epsilon 0.6.json",
}

# Whether to include noise cluster (-1) in cluster summaries
INCLUDE_NOISE = True

TOP_N_GLOBAL = 30
TOP_N_PER_CLUSTER = 15
# ---------------------------


def load_tags_jsonl(path: str):
    """
    Returns:
      tags_by_id: dict[id] -> list of {"label","uri","score"}
    """
    tags_by_id = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            tags_by_id[obj["id"]] = obj.get("tags", [])
    return tags_by_id


def load_clusters(path: str):
    """
    cluster_labels files are list of dicts: [{"id": "...", "cluster": 2}, ...]
    Returns:
      id_to_cluster: dict[id] -> int cluster
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {row["id"]: int(row["cluster"]) for row in data}


def tag_key(tag_obj):
    return tag_obj["uri"] if USE_URI else tag_obj["label"]


def ensure_outdir():
    Path(OUT_DIR).mkdir(parents=True, exist_ok=True)


def main():
    ensure_outdir()

    tags_by_id = load_tags_jsonl(TAGS_JSONL)

    # ------------------------------------------------------------
    # (1) Distribution: how many tags per article?
    # ------------------------------------------------------------
    tags_per_article = Counter()
    for doc_id, tags in tags_by_id.items():
        tags_per_article[len(tags)] += 1

    dist_path = Path(OUT_DIR) / "tag_count_distribution.json"
    with open(dist_path, "w", encoding="utf-8") as f:
        json.dump(
            {"tags_per_article_distribution": dict(sorted(tags_per_article.items()))},
            f,
            ensure_ascii=False,
            indent=2,
        )

    # ------------------------------------------------------------
    # (2) Global most common tags (document frequency)
    # ------------------------------------------------------------
    global_df = Counter()
    uri_to_label = {}  # keep a label for each uri for readability

    for doc_id, tags in tags_by_id.items():
        # count each tag at most once per document
        seen = set()
        for t in tags:
            k = tag_key(t)
            if k in seen:
                continue
            seen.add(k)
            global_df[k] += 1
            if "uri" in t and "label" in t:
                uri_to_label[t["uri"]] = t["label"]

    top_global = []
    for k, c in global_df.most_common(TOP_N_GLOBAL):
        if USE_URI:
            top_global.append({"uri": k, "label": uri_to_label.get(k, ""), "doc_count": c})
        else:
            top_global.append({"label": k, "doc_count": c})

    global_path = Path(OUT_DIR) / "top_tags_global.json"
    with open(global_path, "w", encoding="utf-8") as f:
        json.dump({"top_tags_global": top_global}, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------
    # (3) Tag prevalence per cluster (for each clustering run)
    # ------------------------------------------------------------
    cluster_summary_all_runs = {}

    for run_name, cluster_path in CLUSTER_FILES.items():
        id_to_cluster = load_clusters(cluster_path)

        # cluster -> Counter(tag -> docs with tag)
        cluster_tag_df = defaultdict(Counter)
        cluster_sizes = Counter()

        for doc_id, tags in tags_by_id.items():
            if doc_id not in id_to_cluster:
                continue
            cl = id_to_cluster[doc_id]
            if cl == -1 and not INCLUDE_NOISE:
                continue

            cluster_sizes[cl] += 1

            # doc-frequency within cluster
            seen = set()
            for t in tags:
                k = tag_key(t)
                if k in seen:
                    continue
                seen.add(k)
                cluster_tag_df[cl][k] += 1

        # Build readable output: for each cluster, top tags with counts + % prevalence
        clusters_out = {}
        for cl, size in sorted(cluster_sizes.items(), key=lambda x: (-x[1], x[0])):
            top = []
            for k, cnt in cluster_tag_df[cl].most_common(TOP_N_PER_CLUSTER):
                prevalence = cnt / size if size else 0.0
                if USE_URI:
                    top.append({
                        "uri": k,
                        "label": uri_to_label.get(k, ""),
                        "doc_count": cnt,
                        "prevalence": round(prevalence, 4),
                    })
                else:
                    top.append({
                        "label": k,
                        "doc_count": cnt,
                        "prevalence": round(prevalence, 4),
                    })

            clusters_out[str(cl)] = {
                "cluster_size": int(size),
                "top_tags": top,
            }

        cluster_summary_all_runs[run_name] = {
            "source_cluster_file": cluster_path,
            "include_noise": INCLUDE_NOISE,
            "clusters": clusters_out,
        }

    cluster_path_out = Path(OUT_DIR) / "tags_by_cluster_all_runs.json"
    with open(cluster_path_out, "w", encoding="utf-8") as f:
        json.dump(cluster_summary_all_runs, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------
    # Print a quick terminal summary (so you see it immediately)
    # ------------------------------------------------------------
    total_docs = len(tags_by_id)
    print("\n=== DONE ===")
    print("Docs with tags:", total_docs)
    print("Saved:")
    print("-", dist_path)
    print("-", global_path)
    print("-", cluster_path_out)

    print("\nTags-per-article distribution (first 10 bins):")
    for n, c in sorted(tags_per_article.items())[:10]:
        print(f"  {n} tags: {c} articles")

    print("\nTop 10 tags globally (by doc frequency):")
    for item in top_global[:10]:
        if USE_URI:
            print(f"  {item['doc_count']:>4}  {item['label']}  ({item['uri']})")
        else:
            print(f"  {item['doc_count']:>4}  {item['label']}")

if __name__ == "__main__":
    main()

