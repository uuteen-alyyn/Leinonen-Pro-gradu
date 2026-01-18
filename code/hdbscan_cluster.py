
import json
import numpy as np
from pathlib import Path
import hdbscan
from collections import Counter

# Paths
PCA_EMB_PATH = "out/embeddings_pca_50.npy"
IDS_PATH = "out/ids.json"
OUT_PATH = "out/cluster_labels_leaf_epsilon 0.55.json"

# HDBSCAN parameters
MIN_CLUSTER_SIZE = 5     # reasonable starting point for 830 docs
MIN_SAMPLES = None        # None = same as min_cluster_size
METRIC = "euclidean"


def main():
    # Load data
    X = np.load(PCA_EMB_PATH)
    ids = json.load(open(IDS_PATH, "r", encoding="utf-8"))

    assert X.shape[0] == len(ids), "Mismatch between embeddings and ids"

    print("Data shape:", X.shape)

    # Run HDBSCAN
    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=MIN_CLUSTER_SIZE,
        min_samples=MIN_SAMPLES,
        metric=METRIC,
        cluster_selection_method="leaf",
        cluster_selection_epsilon = 0.55
    )

    labels = clusterer.fit_predict(X)

    # Basic diagnostics
    counts = Counter(labels)
    n_noise = counts.get(-1, 0)
    n_clusters = len([c for c in counts if c != -1])

    print("Number of clusters:", n_clusters)
    print("Noise points (-1):", n_noise)
    print("Cluster sizes (label: count):")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")

    # Save results (id -> cluster)
    out = [
        {"id": aid, "cluster": int(label)}
        for aid, label in zip(ids, labels)
    ]

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print("Saved cluster labels to:", OUT_PATH)


if __name__ == "__main__":
    main()
