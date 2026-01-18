import json
from pathlib import Path
import numpy as np

INPUT_JSONL = "articles_flat.jsonl"
OUT_DIR = "out"

MODEL_NAME = "google/embeddinggemma-300m"
BATCH_SIZE = 8          # safe for CPU
NORMALIZE = True


def load_records(path):
    ids = []
    texts = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            text = (obj.get("text_for_embedding") or "").strip()
            if not text:
                continue
            ids.append(obj["id"])
            texts.append(text)
    return ids, texts


def main():
    from sentence_transformers import SentenceTransformer

    Path(OUT_DIR).mkdir(exist_ok=True)

    ids, texts = load_records(INPUT_JSONL)
    print(f"Loaded {len(texts)} texts")

    # Force CPU to avoid CUDA incompatibility issues
    device = "cpu"
    print("Using device:", device)

    model = SentenceTransformer(MODEL_NAME, device=device)

    embeddings = model.encode(
        texts,
        batch_size=BATCH_SIZE,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=NORMALIZE,
    ).astype(np.float32)

    np.save(Path(OUT_DIR) / "embeddings.npy", embeddings)

    with open(Path(OUT_DIR) / "ids.json", "w", encoding="utf-8") as f:
        json.dump(ids, f, ensure_ascii=False, indent=2)

    print("Saved embeddings:", embeddings.shape)
    print("Done.")


if __name__ == "__main__":
    main()

