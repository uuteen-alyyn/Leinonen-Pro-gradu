import json
import os
from pathlib import Path

import numpy as np
from sklearn.decomposition import PCA


# ---- CONFIG (safe defaults for 8 GB RAM) ----
INPUT_JSONL = "articles_flat.jsonl"

# Try EmbeddingGemma first; fall back to a strong CPU-friendly multilingual model if not available
PRIMARY_MODEL = "google/embeddinggemma-300m"
FALLBACK_MODEL = "Alibaba-NLP/gte-multilingual-base"

BATCH_SIZE = 8          # keep small for 8 GB RAM
NORMALIZE = True        # recommended for stable similarity + clustering

PCA_DIMS_FOR_CLUSTERING = 50
RANDOM_STATE = 42

OUT_DIR = "out"
# --------------------------------------------


def load_records(jsonl_path: str):
    ids = []
    texts = []
    skipped = 0

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            _id = obj.get("id")
            text = (obj.get("text_for_embedding") or "").strip()

            # Keep a strict guard: do not embed empty texts
            if not text:
                skipped += 1
                continue

            ids.append(_id)
            texts.append(text)

    return ids, texts, skipped


def load_model():
    from sentence_transformers import SentenceTransformer

    try:
        print(f"Loading embedding model: {PRIMARY_MODEL}")
        return SentenceTransformer(PRIMARY_MODEL)
    except Exception as e:
        print(f"Could not load {PRIMARY_MODEL}. Reason: {e}")
        print(f"Falling back to: {FALLBACK_MODEL}")
        return SentenceTransformer(FALLBACK_MODEL)


def main():
    Path(OUT_DIR).mkdir(parents=True, exist_ok=True)

    ids, texts, skipped = load_records(INPUT_JSONL)
    print(f"Loaded {len(texts)} texts for embedding. Skipped empty: {skipped}")

    model = load_model()

    print("Embedding… (CPU-safe batch size)")
    # encode returns np.ndarray; we force float32 for smaller files and faster PCA
    embeddings = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=NORMALIZE,
    ).astype(np.float32)

    # Save embeddings + ids (so you can join back to metadata later)
    emb_path = Path(OUT_DIR) / "embeddings.npy"
    ids_path = Path(OUT_DIR) / "ids.json"
    np.save(emb_path, embeddings)
    with open(ids_path, "w", encoding="utf-8") as f:
        json.dump(ids, f, ensure_ascii=False, indent=2)

    print(f"Saved: {emb_path}")
    print(f"Saved: {ids_path}")
    print(f"Embeddings shape: {embeddings.shape}")

    # PCA for clustering (reproducible)
    # PCA centers data; we don't standardize because embeddings are already comparable in scale.
    print(f"Running PCA to {PCA_DIMS_FOR_CLUSTERING} dims (random_state={RANDOM_STATE})…")
    pca = PCA(n_components=PCA_DIMS_FOR_CLUSTERING, random_state=RANDOM_STATE)
    Xp = pca.fit_transform(embeddings).astype(np.float32)

    pca_path = Path(OUT_DIR) / f"pca_{PCA_DIMS_FOR_CLUSTERING}.npy"
    np.save(pca_path, Xp)
    print(f"Saved: {pca_path}")
    print(f"Explained variance ratio (sum): {pca.explained_variance_ratio_.sum():.4f}")

    # Also save 2D PCA for quick plotting/inspection later
    pca2 = PCA(n_components=2, random_state=RANDOM_STATE)
    X2 = pca2.fit_transform(embeddings).astype(np.float32)
    pca2_path = Path(OUT_DIR) / "pca_2d.csv"
    with open(pca2_path, "w", encoding="utf-8") as f:
        f.write("id,pc1,pc2\n")
        for _id, (a, b) in zip(ids, X2):
            f.write(f"{_id},{a},{b}\n")
    print(f"Saved: {pca2_path}")

    print("Done.")


if __name__ == "__main__":
    main()
