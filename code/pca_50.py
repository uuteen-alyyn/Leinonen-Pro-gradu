import numpy as np
from pathlib import Path
from sklearn.decomposition import PCA

# Paths
EMBEDDINGS_PATH = "out/embeddings.npy"
OUT_DIR = Path("out")

# Parameters
N_COMPONENTS = 50
RANDOM_STATE = 42


def main():
    # Load embeddings
    X = np.load(EMBEDDINGS_PATH)
    print("Original shape:", X.shape)

    # Run PCA
    pca = PCA(n_components=N_COMPONENTS, random_state=RANDOM_STATE)
    X_pca = pca.fit_transform(X)

    print("PCA shape:", X_pca.shape)
    print("Explained variance ratio (sum):", pca.explained_variance_ratio_.sum())

    # Save reduced embeddings
    out_path = OUT_DIR / "embeddings_pca_50.npy"
    np.save(out_path, X_pca.astype(np.float32))

    print("Saved:", out_path)


if __name__ == "__main__":
    main()

