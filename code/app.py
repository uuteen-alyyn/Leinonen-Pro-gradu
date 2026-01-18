import json
from pathlib import Path

import pandas as pd
import streamlit as st

# ---- Settings ----
DATA_PATH = Path("out/merged_for_app.jsonl")  # adjust if needed

st.set_page_config(page_title="Article Explorer", layout="wide")

@st.cache_data(show_spinner=False)
def load_jsonl(path: Path) -> pd.DataFrame:
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return pd.json_normalize(rows)

def safe_int(x, default=None):
    try:
        return int(x)
    except Exception:
        return default

def extract_tag_labels(tag_list):
    if not isinstance(tag_list, list):
        return []
    labels = []
    for t in tag_list:
        if isinstance(t, dict) and "label" in t:
            labels.append(str(t["label"]))
    return labels

def extract_tag_map(tag_list):
    # label -> score
    m = {}
    if not isinstance(tag_list, list):
        return m
    for t in tag_list:
        if isinstance(t, dict) and "label" in t:
            m[str(t["label"])] = float(t.get("score", 0.0) or 0.0)
    return m

# ---- Load ----
st.title("Article Explorer (offline)")
if not DATA_PATH.exists():
    st.error(f"Cannot find: {DATA_PATH.resolve()}")
    st.stop()

df = load_jsonl(DATA_PATH)

# Expected fields (best-effort)
# id, title, abstract, metadata.*, cluster.*
if "id" not in df.columns:
    st.error("No 'id' field found in the merged file.")
    st.stop()

# Year: try multiple possible locations
year_col_candidates = [
    "metadata.article.year",
    "metadata.article.Year",
    "year",
]
year_series = None
for c in year_col_candidates:
    if c in df.columns:
        year_series = df[c]
        break
df["year"] = year_series.apply(safe_int) if year_series is not None else None

# Cluster label/name (handle both dict and flattened)
# If your merge stored as {"cluster": {"label":..., "name":...}} it becomes columns:
# "cluster.label", "cluster.name"
if "cluster.label" in df.columns:
    df["cluster_label"] = df["cluster.label"].apply(safe_int)
else:
    df["cluster_label"] = -999

if "cluster.name" in df.columns:
    df["cluster_name"] = df["cluster.name"].fillna("").astype(str)
else:
    df["cluster_name"] = df["cluster_label"].apply(lambda x: "Noise / Unclustered" if x == -1 else f"Cluster {x}")

# Tags: if stored under "tags" in each record, json_normalize keeps it as a column "tags"
if "tags" in df.columns:
    df["tag_labels"] = df["tags"].apply(extract_tag_labels)
    df["tag_scores"] = df["tags"].apply(extract_tag_map)
else:
    df["tag_labels"] = [[] for _ in range(len(df))]
    df["tag_scores"] = [{} for _ in range(len(df))]

# Searchable text (best-effort; uses whatever exists)
title_col = "title" if "title" in df.columns else "metadata.article.title" if "metadata.article.title" in df.columns else None
abstract_col = "abstract" if "abstract" in df.columns else "metadata.article.abstract" if "metadata.article.abstract" in df.columns else None

df["title_text"] = df[title_col].fillna("").astype(str) if title_col else ""
df["abstract_text"] = df[abstract_col].fillna("").astype(str) if abstract_col else ""

# optional translated fields if present
df["title_en"] = df["title_en"].fillna("").astype(str) if "title_en" in df.columns else ""
df["abstract_en"] = df["abstract_en"].fillna("").astype(str) if "abstract_en" in df.columns else ""

df["search_blob"] = (
    df["title_text"] + "\n" + df["abstract_text"] + "\n" + df["title_en"] + "\n" + df["abstract_en"]
).str.lower()

# ---- Sidebar filters ----
st.sidebar.header("Filters")

# Cluster filter
cluster_options = ["(All)"] + sorted(df["cluster_name"].dropna().unique().tolist())
cluster_choice = st.sidebar.selectbox("Cluster", cluster_options, index=0)

# Year range
years = sorted([y for y in df["year"].dropna().unique().tolist() if isinstance(y, int)])
if years:
    yr_min, yr_max = min(years), max(years)
    year_range = st.sidebar.slider("Year range", yr_min, yr_max, (yr_min, yr_max))
else:
    year_range = None
    st.sidebar.info("No usable year field found.")

# Tags filter
all_tags = sorted({t for tags in df["tag_labels"] for t in (tags or [])})
tag_mode = st.sidebar.radio("Tag match mode", ["AND (must include all)", "OR (any)"], index=0)
selected_tags = st.sidebar.multiselect("Tags", all_tags)

# Text search
q = st.sidebar.text_input("Search (title/abstract, zh+en)", value="").strip().lower()

# ---- Apply filters ----
mask = pd.Series(True, index=df.index)

if cluster_choice != "(All)":
    mask &= (df["cluster_name"] == cluster_choice)

if year_range and "year" in df.columns:
    mask &= df["year"].between(year_range[0], year_range[1], inclusive="both") | df["year"].isna()

if selected_tags:
    if tag_mode.startswith("AND"):
        mask &= df["tag_labels"].apply(lambda lst: all(t in (lst or []) for t in selected_tags))
    else:
        mask &= df["tag_labels"].apply(lambda lst: any(t in (lst or []) for t in selected_tags))

if q:
    mask &= df["search_blob"].str.contains(q, na=False)

fdf = df[mask].copy()

# ---- Main layout ----
left, right = st.columns([1.2, 1])

with left:
    st.subheader("Results")
    st.caption(f"Showing {len(fdf)} / {len(df)} articles")

    # Simple list with expandable details
    # Sort newest first if year exists
    if "year" in fdf.columns and fdf["year"].notna().any():
        fdf = fdf.sort_values(["year"], ascending=False)
    else:
        fdf = fdf.sort_values(["id"])

    # Limit initial rendering for speed
    max_show = st.slider("Max results to render", 50, 1000, 200, step=50)
    shown = fdf.head(max_show)

    for _, row in shown.iterrows():
        title = row.get("title_text", "") or "(no title)"
        year = row.get("year", "")
        cluster = row.get("cluster_name", "")
        header = f"{title}  —  {year}  —  {cluster}  —  {row['id']}"
        with st.expander(header, expanded=False):
            st.write("**Abstract (original):**")
            st.write(row.get("abstract_text", "") or "_(empty)_")

            if row.get("title_en", "") or row.get("abstract_en", ""):
                st.write("**English translation:**")
                if row.get("title_en", ""):
                    st.write(f"**Title (EN):** {row.get('title_en','')}")
                if row.get("abstract_en", ""):
                    st.write(row.get("abstract_en",""))

            tags = row.get("tags", []) if isinstance(row.get("tags", None), list) else []
            if tags:
                st.write("**Tags (Finto AI):**")
                # show sorted by score
                tags_sorted = sorted(tags, key=lambda t: float(t.get("score", 0.0) or 0.0), reverse=True)
                st.table([{"label": t.get("label"), "score": t.get("score"), "uri": t.get("uri")} for t in tags_sorted])

            # Metadata dump (collapsible)
            meta = row.get("metadata", None)
            if isinstance(meta, dict):
                st.write("**Metadata:**")
                st.json(meta)

with right:
    st.subheader("Quick visuals (filtered set)")

    # Articles per year
    if "year" in fdf.columns and fdf["year"].notna().any():
        year_counts = fdf.dropna(subset=["year"]).groupby("year").size().reset_index(name="count")
        year_counts = year_counts.sort_values("year")
        st.line_chart(year_counts.set_index("year")["count"])
    else:
        st.info("No year info available for plotting.")

    # Top tags in filtered set
    tag_counter = {}
    for tags in fdf["tag_labels"]:
        for t in (tags or []):
            tag_counter[t] = tag_counter.get(t, 0) + 1
    if tag_counter:
        topn = st.slider("Top tags to show", 5, 50, 20)
        top_tags = sorted(tag_counter.items(), key=lambda x: x[1], reverse=True)[:topn]
        st.bar_chart(pd.DataFrame(top_tags, columns=["tag", "count"]).set_index("tag"))
    else:
        st.info("No tags found in filtered set.")
