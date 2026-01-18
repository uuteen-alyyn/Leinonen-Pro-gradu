# app.py

import json
from pathlib import Path

import pandas as pd
import streamlit as st

# ---- Settings ----
DATA_PATH = Path("out/merged_for_app.jsonl")  # adjust if needed

st.set_page_config(page_title="Article Explorer", layout="wide")


@st.cache_data(show_spinner=False)
def load_jsonl_raw(path: Path) -> list[dict]:
    """Load JSONL into a list of dicts (keeps nested structures intact)."""
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


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


def tag_score_from_raw(raw_record: dict, tag_label: str) -> float:
    """
    Returns a score for a given tag label in an article.
    - Manual hits: 0.95 if the tag label is present in manual_keyword_hits
    - Otherwise: use finto tag score if present
    - Else: 0.0
    """
    if not isinstance(raw_record, dict):
        return 0.0

    manual = raw_record.get("manual_keyword_hits", [])
    if isinstance(manual, list) and tag_label in manual:
        return 0.95

    finto = raw_record.get("finto_tags_en", [])
    if isinstance(finto, list):
        for t in finto:
            if isinstance(t, dict) and t.get("label") == tag_label:
                try:
                    return float(t.get("score", 0.0) or 0.0)
                except Exception:
                    return 0.0

    return 0.0


def compute_match_score(doc_id: str, selected_tags: list[str]) -> float:
    """
    Score = sum of scores for selected tags found in the article.
    (Manual tag hit = 0.95; otherwise Finto score.)
    """
    if not selected_tags:
        return 0.0
    raw = raw_by_id.get(doc_id, {}) or {}
    return float(sum(tag_score_from_raw(raw, t) for t in selected_tags))


# ---- Load ----
st.title("Article Explorer (offline)")
if not DATA_PATH.exists():
    st.error(f"Cannot find: {DATA_PATH.resolve()}")
    st.stop()

# Load raw rows (for full metadata/tags display), and a normalized df (for filtering/search)
raw_rows = load_jsonl_raw(DATA_PATH)
df = pd.json_normalize(raw_rows)

# Expected fields (best-effort)
if "id" not in df.columns:
    st.error("No 'id' field found in the merged file.")
    st.stop()

# For fast lookup of the raw record by id (for full metadata + full tags display)
raw_by_id = {r.get("id"): r for r in raw_rows if isinstance(r, dict) and r.get("id")}

# ---- Year ----
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

# ---- Cluster mode + cluster label/name ----
# Supports BOTH old schema:
#   cluster.label, cluster.name
# and new multi-run schema:
#   clusters.<run>.label, clusters.<run>.name

CLUSTER_RUNS = [
    ("leaf_0.55", "Leaf ε=0.55 (optimal)"),
    ("leaf_0.5",  "Leaf ε=0.5"),
    ("leaf_0.6",  "Leaf ε=0.6"),
    ("leaf",      "Leaf (no ε)"),
    ("eom",       "EOM"),
]

# Pick default run based on what exists in the dataframe
def pick_default_cluster_run(dfcols: set[str]) -> str:
    for key, _label in CLUSTER_RUNS:
        if f"clusters.{key}.label" in dfcols:
            return key
    return "__single__"  # fallback to old schema

dfcols = set(df.columns)
default_run = pick_default_cluster_run(dfcols)

# We'll define cluster_run *later* in sidebar; here just prep placeholders
df["cluster_label"] = -999
df["cluster_name"] = "Unknown"


# ---- Tags (Finto AI + manual keyword hits) ----
# Finto tags are stored in your merged records under "finto_tags_en"
if "finto_tags_en" in df.columns:
    df["finto_tag_labels"] = df["finto_tags_en"].apply(extract_tag_labels)
else:
    df["finto_tag_labels"] = [[] for _ in range(len(df))]

# Manual keyword hits are stored under "manual_keyword_hits" (list of strings)
if "manual_keyword_hits" in df.columns:
    df["manual_tag_labels"] = df["manual_keyword_hits"].apply(lambda x: x if isinstance(x, list) else [])
else:
    df["manual_tag_labels"] = [[] for _ in range(len(df))]

# Combined tags for filtering UI
# Display labels for tag picker: manual tags get " (Man.)" suffix
df["manual_tag_labels_disp"] = df["manual_tag_labels"].apply(
    lambda xs: [f"{t} (Man.)" for t in (xs or [])]
)
df["tag_labels_disp"] = df["finto_tag_labels"] + df["manual_tag_labels_disp"]

# Internal/raw tag labels (no suffix) for matching/scoring
df["tag_labels"] = df["finto_tag_labels"] + df["manual_tag_labels"]


# ---- Titles/Abstracts (translated + original) ----
# Original (best-effort; your merged file has top-level title/abstract)
title_col = "title" if "title" in df.columns else "metadata.article.title" if "metadata.article.title" in df.columns else None
abstract_col = "abstract" if "abstract" in df.columns else "metadata.article.abstract" if "metadata.article.abstract" in df.columns else None

df["title_orig"] = df[title_col].fillna("").astype(str) if title_col else ""
df["abstract_orig"] = df[abstract_col].fillna("").astype(str) if abstract_col else ""

# Translated fields in merged data are nested under translation_en.title_en / translation_en.abstract_en
df["title_en"] = df["translation_en.title_en"].fillna("").astype(str) if "translation_en.title_en" in df.columns else ""
df["abstract_en"] = df["translation_en.abstract_en"].fillna("").astype(str) if "translation_en.abstract_en" in df.columns else ""

# Display title should be translated title when available
df["title_display"] = df["title_en"]
missing_title_en = df["title_display"].fillna("").astype(str).str.strip() == ""
df.loc[missing_title_en, "title_display"] = df.loc[missing_title_en, "title_orig"]

# Search blob: search both EN + original, plus tags
df["search_blob"] = (
    df["title_orig"] + "\n" + df["abstract_orig"] + "\n" +
    df["title_en"] + "\n" + df["abstract_en"] + "\n" +
    df["tag_labels"].apply(lambda xs: " ".join(xs or []))
).astype(str).str.lower()


# ---- Sidebar filters ----
st.sidebar.header("Filters")

# Cluster mode selector
available_runs = []
for key, label in CLUSTER_RUNS:
    if f"clusters.{key}.label" in df.columns:
        available_runs.append((key, label))

# If no multi-run columns exist, fall back to old single cluster columns
if available_runs:
    run_labels = [label for _key, label in available_runs]
    run_keys = [key for key, _label in available_runs]

    # choose default index
    default_idx = run_keys.index(default_run) if default_run in run_keys else 0

    cluster_run_label = st.sidebar.radio("Cluster mode", run_labels, index=default_idx)
    cluster_run = run_keys[run_labels.index(cluster_run_label)]

    label_col = f"clusters.{cluster_run}.label"
    name_col  = f"clusters.{cluster_run}.name"

    df["cluster_label"] = df[label_col].apply(safe_int) if label_col in df.columns else -999
    if name_col in df.columns:
        df["cluster_name"] = df[name_col].fillna("").astype(str)
    else:
        df["cluster_name"] = df["cluster_label"].apply(
            lambda x: "Noise / Unclustered" if x == -1 else f"Cluster {x}"
        )

else:
    # Old schema fallback
    if "cluster.label" in df.columns:
        df["cluster_label"] = df["cluster.label"].apply(safe_int)
    else:
        df["cluster_label"] = -999

    if "cluster.name" in df.columns:
        df["cluster_name"] = df["cluster.name"].fillna("").astype(str)
    else:
        df["cluster_name"] = df["cluster_label"].apply(
            lambda x: "Noise / Unclustered" if x == -1 else f"Cluster {x}"
        )


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

# Tags filter (combined Finto + manual hits)
all_tags = sorted({t for tags in df["tag_labels_disp"] for t in (tags or [])})
tag_mode = st.sidebar.radio("Tag match mode", ["AND (must include all)", "OR (any)"], index=0)
selected_tags_disp = st.sidebar.multiselect("Tags (Finto + manual)", all_tags)

def undisp(tag: str) -> str:
    return tag[:-7] if isinstance(tag, str) and tag.endswith(" (Man.)") else tag

selected_tags = [undisp(t) for t in selected_tags_disp]


# Order results (NOW USED)
sort_mode = st.sidebar.selectbox(
    "Order results",
    ["Date (newest first)", "Date (oldest first)", "Best match (selected tags)"],
    index=0
)

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

# ---- Sorting (UPDATED) ----
if sort_mode.startswith("Best match"):
    # Compute match score per row (only meaningful if selected_tags)
    fdf["match_score"] = fdf["id"].apply(lambda doc_id: compute_match_score(doc_id, selected_tags))
    # Sort by match_score desc, then year desc (if exists), then id
    if "year" in fdf.columns:
        fdf = fdf.sort_values(["match_score", "year", "id"], ascending=[False, False, True])
    else:
        fdf = fdf.sort_values(["match_score", "id"], ascending=[False, True])

elif sort_mode.startswith("Date (oldest"):
    if "year" in fdf.columns and fdf["year"].notna().any():
        fdf = fdf.sort_values(["year", "id"], ascending=[True, True])
    else:
        fdf = fdf.sort_values(["id"])

else:  # Date (newest first)
    if "year" in fdf.columns and fdf["year"].notna().any():
        fdf = fdf.sort_values(["year", "id"], ascending=[False, True])
    else:
        fdf = fdf.sort_values(["id"])


# ---- Main layout ----
left, right = st.columns([1.2, 1])

with left:
    st.subheader("Results")
    st.caption(f"Showing {len(fdf)} / {len(df)} articles")

    max_show = st.slider("Max results to render", 50, 1000, 200, step=50)
    shown = fdf.head(max_show)

    for _, row in shown.iterrows():
        doc_id = row.get("id")
        title = row.get("title_display", "") or "(no title)"
        year = row.get("year", "")
        cluster = row.get("cluster_name", "")

        # Optional: show score in header only when using Best match
        if sort_mode.startswith("Best match"):
            ms = float(row.get("match_score", 0.0) or 0.0)
            header = f"{title}  —  {year}  —  {cluster}  —  score {ms:.3f}  —  {doc_id}"
        else:
            header = f"{title}  —  {year}  —  {cluster}  —  {doc_id}"

        with st.expander(header, expanded=False):
            # ---- Texts (Translated first, then original) ----
            st.write("**Abstract (English translation):**")
            abs_en = (row.get("abstract_en", "") or "").strip()
            st.write(abs_en if abs_en else "_(empty)_")

            st.divider()

            st.write("**Original title (Chinese/Original):**")
            st.write((row.get("title_orig", "") or "").strip() or "_(empty)_")

            st.write("**Abstract (original):**")
            st.write((row.get("abstract_orig", "") or "").strip() or "_(empty)_")

            st.divider()

            # ---- Tags: Finto + manual ----
            raw = raw_by_id.get(doc_id, {}) or {}

            finto_tags = raw.get("finto_tags_en", [])
            manual_hits = raw.get("manual_keyword_hits", [])

            if isinstance(finto_tags, list) and finto_tags:
                st.write("**Finto / YSO tags (EN):**")
                tags_sorted = sorted(
                    finto_tags,
                    key=lambda t: float(t.get("score", 0.0) or 0.0) if isinstance(t, dict) else 0.0,
                    reverse=True
                )
                st.table([
                    {"label": t.get("label"), "score": t.get("score"), "uri": t.get("uri")}
                    for t in tags_sorted if isinstance(t, dict)
                ])
            else:
                st.info("No Finto tags for this article.")

            if isinstance(manual_hits, list) and manual_hits:
                st.write("**Manual keyword hits (custom list):**")
                st.write(", ".join(sorted(set(str(x) for x in manual_hits))))
            else:
                st.write("**Manual keyword hits (custom list):** _(none)_")

            st.divider()

            # ---- Metadata (show all) ----
            meta = raw.get("metadata", None)
            if isinstance(meta, dict):
                st.write("**Metadata (full):**")
                st.json(meta)
            else:
                st.info("No metadata dict found for this article.")

with right:
    st.subheader("Quick visuals (filtered set)")

    # Articles per year
    if "year" in fdf.columns and fdf["year"].notna().any():
        year_counts = fdf.dropna(subset=["year"]).groupby("year").size().reset_index(name="count")
        year_counts = year_counts.sort_values("year")
        st.line_chart(year_counts.set_index("year")["count"])
    else:
        st.info("No year info available for plotting.")

    # Top tags in filtered set (combined) with RANGE slider
    tag_counter = {}
    for tags in fdf["tag_labels"]:
        for t in (tags or []):
            tag_counter[t] = tag_counter.get(t, 0) + 1

    if tag_counter:
        sorted_tags = sorted(tag_counter.items(), key=lambda x: x[1], reverse=True)
        max_rank = min(200, len(sorted_tags))  # keep UI manageable

        start_rank, end_rank = st.slider(
            "Tag rank range to show (e.g., 10–30)",
            1, max_rank, (1, min(20, max_rank))
        )

        # Convert ranks (1-based) to slice (0-based)
        slice_tags = sorted_tags[start_rank - 1:end_rank]

        st.bar_chart(pd.DataFrame(slice_tags, columns=["tag", "count"]).set_index("tag"))
        st.caption(f"Showing tag ranks {start_rank}–{end_rank} (out of {len(sorted_tags)} tags)")
    else:
        st.info("No tags found in filtered set.")
