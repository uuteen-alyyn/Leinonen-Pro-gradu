import json
from collections import defaultdict
from sklearn.feature_extraction.text import TfidfVectorizer

ARTICLES_PATH = "articles_flat.jsonl"
CLUSTERS_PATH = "out/cluster_labels_eom.json"  # change per run
OUT_PATH = "out/tfidf/tfidf_eom non stop.json"                # change per run

TOP_K = 15

import re

BOILERPLATE_PATTERNS = [
    r"\babstract\b",
    r"\btitle\b",
    r"ａｂｓｔｒａｃｔ",
    r"经国家教育部.*?批准",
    r"沪新出报.*",
]

EN_STOP = {
    "the","and","of","in","to","is","are","was","were","for","on","with","as","by",
    "that","this","it","its","their","has","have","had"
}

ZH_STOP = {
    "的","是","在","和","与","但","但是","然而","以及","对","中","下","上","后",
    "以来","近年来","目前","当前"
}

STOPWORDS = EN_STOP | ZH_STOP


def clean_text(text):
    text = text.lower()
    for pat in BOILERPLATE_PATTERNS:
        text = re.sub(pat, " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def load_articles():
    ids = []
    texts = []
    with open(ARTICLES_PATH, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            ids.append(obj["id"])
            texts.append(clean_text(obj["text_for_embedding"]))
    return ids, texts

def load_clusters():
    with open(CLUSTERS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)  # list of dicts
    # build id -> cluster label dict
    return {item["id"]: item["cluster"] for item in data}



def main():
    ids, texts = load_articles()
    id_to_label = load_clusters()

    cluster_docs = defaultdict(list)

    for doc_id, text in zip(ids, texts):
        label = id_to_label.get(doc_id, -1)
        if label == -1:
            continue
        cluster_docs[int(label)].append(text)


    results = {}

    all_texts = texts

    for label, docs in cluster_docs.items():
        CHINESE_STOPWORDS = {
            "的", "是", "在", "和", "与", "但", "但是", "以及", "对", "中"
        }

        vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            max_df=0.85,
            min_df=5,
            stop_words=list(STOPWORDS),
            token_pattern=r"(?u)\b\w\w+\b"
        )



        tfidf = vectorizer.fit_transform(docs + all_texts)
        features = vectorizer.get_feature_names_out()

        cluster_vec = tfidf[:len(docs)].mean(axis=0).A1
        rest_vec = tfidf[len(docs):].mean(axis=0).A1

        scores = cluster_vec - rest_vec
        top_idx = scores.argsort()[::-1][:TOP_K]

        results[f"cluster_{label}"] = {
            "size": len(docs),
            "top_terms": [
                [features[i], float(scores[i])]
                for i in top_idx
            ]
        }

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Saved TF-IDF keywords to {OUT_PATH}")


if __name__ == "__main__":
    main()
