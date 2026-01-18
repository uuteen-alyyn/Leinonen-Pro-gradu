import json

ARTICLES_PATH = "articles_flat.jsonl"
CLUSTERS_PATH = "out/cluster_labels_leaf_epsilon 0.5.json"

# CHANGE THIS to the cluster you want to inspect
CLUSTER_ID = 7   # example: the cluster with ~187 articles


def load_articles():
    articles = {}
    with open(ARTICLES_PATH, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            articles[obj["id"]] = obj["metadata"]["article"]["title"]
    return articles


def load_clusters():
    with open(CLUSTERS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    articles = load_articles()
    clusters = load_clusters()

    titles = [
        articles[item["id"]]
        for item in clusters
        if item["cluster"] == CLUSTER_ID and item["id"] in articles
    ]

    print(f"\nCluster {CLUSTER_ID} — {len(titles)} articles\n")
    for i, title in enumerate(titles[:50], 1):  # show first 50 only
        print(f"{i:02d}. {title}")


if __name__ == "__main__":
    main()


