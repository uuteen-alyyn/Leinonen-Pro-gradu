# Offline Article Explorer (Streamlit)

A small offline Streamlit app for browsing a JSONL dataset of research articles with:
- full-text/metadata search (original + English translation, if available)
- tag-based filtering (Finto/YSO tags + custom manual tags)
- multiple clustering “runs” (EOM, Leaf, and Leaf ε variations)
- quick visual summaries (articles per year + top tags)

The UI is designed for exploratory analysis of a locally preprocessed corpus.

---

## What is `app2.py`?

`app2.py` is a **Streamlit-based offline explorer** for the merged dataset file:

- Reads `out/merged_for_app.jsonl`
- Normalizes nested JSON for filtering (via `pandas.json_normalize`)
- Provides interactive filtering (cluster, year, tags, text search)
- Renders result cards with translated/original text, tags, and full metadata
- Shows quick visual summaries for the currently filtered subset

In short: **it’s a lightweight dataset browser** for your merged article corpus.

---

## Requirements

- Python 3.10+ (3.11 also OK)
- `streamlit`, `pandas`

Recommended: run everything inside a virtual environment.

---

## Required files and folder layout

The app expects to be run from the project folder that contains an `out/` directory.

Minimum required:

```

Data/
app2.py
out/
merged_for_app.jsonl

````
That’s enough to start the visualizer.


### What must be inside `out/merged_for_app.jsonl`?

Each JSONL row should contain at least:

- `id` (string)
- `title`, `abstract` (strings; original language OK)
- `metadata` (dict; can be empty)
- `finto_tags_en` (list; can be empty)
- `manual_keyword_hits` (list of strings; can be empty)
- `translation_en` (dict; can be empty)
- `clusters` (dict of clustering runs)

Example of the cluster structure used by the app:

```json
"clusters": {
  "eom": {"label": 2, "name": "Cluster 2"},
  "leaf": {"label": 4, "name": "Cluster 4"},
  "leaf_0.5": {"label": 1, "name": "Cluster 1"},
  "leaf_0.55": {"label": -1, "name": "Noise / Unclustered"},
  "leaf_0.6": {"label": 7, "name": "Cluster 7"}
}
````

> If your merged file does not include `clusters.<run>.label/name`, the “Cluster mode” UI will not appear.

---

## Installation (recommended)

From the `Data/` folder:

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install streamlit pandas
```

---

## Start the app

From the `Data/` folder (where `app2.py` lives):

```bash
source .venv/bin/activate
streamlit run app2.py
```

Streamlit prints a local URL (typically `http://localhost:8501`).
Open that URL in your browser.

---

## UI guide (what each control does)

### Layout overview

The app has two main columns:

* **Left:** Results list (expandable article cards)
* **Right:** Quick visuals based on the currently filtered set

A **sidebar** contains all filters and sorting controls.

---

## Sidebar: Filters

### 1) Cluster mode (radio)

The different clusterings are pre-made groupings of the articles into thematic groups in vector space, using the HDBSCAN method.

Selects which clustering run to use for cluster filtering + display.
Typical options:

* `EOM`
* `Leaf (no ε)`
* `Leaf ε=0.5`
* `Leaf ε=0.55`
* `Leaf ε=0.6`

Changing cluster mode updates the available cluster options below.

### 2) Cluster (dropdown)

The cluster dropdown allows you to select spesific subclusters of the selected HDBSCAN clustering run for in depth analyses. Unclustered individual articles can be accessed under "Noise".

Filters articles by the cluster name from the selected run:

* `(All)` = no cluster filtering
* `Noise / Unclustered` = label `-1`
* `Cluster N` = label `N`

### 3) Year range (slider)

Filters by publication year (if available in metadata):

* Select a min–max year window
* Articles with missing year are kept (so you don’t lose unknown-year records)

If year data isn’t found, the app displays a note and disables this filter.

### 4) Tag match mode (radio)

Controls how multiple selected tags are interpreted:

* **AND (must include all)**: article must contain *every* selected tag
* **OR (any)**: article must contain *at least one* selected tag

### 5) Tags (Finto + manual) (multiselect)

Pick tags to filter the dataset.

* **Finto tags** appear normally: `NATO`
* **Manual tags** appear with a suffix: `NATO (Man.)`

The suffix is only for display; the underlying matching uses the base label.

### 6) Order results (dropdown)

Sorts the filtered results list:

* **Date (newest first)**: highest year first (then id)
* **Date (oldest first)**: lowest year first (then id)
* **Best match (selected tags)**:

  * scores each article by tag strength
  * manual tag hit uses a strong fixed score (0.95)
  * Finto tags use their stored score
  * results sorted by match score desc, then year desc

### 7) Search (text input)

Case-insensitive keyword search over a combined “search blob”:

* original title + abstract
* translated title + abstract (if available)
* all tag labels

---

## Main column: Results

### Results header

* Shows how many articles are displayed: `Showing X / Y articles`

### Max results to render (slider)

Limits how many result cards are rendered (performance control).

* Useful when filters return hundreds of items.

### Article cards (expanders)

Each result is an expandable card. The header includes:

* title (translated if available, otherwise original)
* year (if available)
* cluster name (based on selected cluster run)
* id
* (optional) match score when “Best match” sorting is active

Inside each expanded card you’ll see:

1. **Abstract (English translation)** (if available; otherwise empty)
2. **Original title**
3. **Original abstract**
4. **Finto / YSO tags (EN)**
   Displayed as a table: label, score, URI (sorted by score)
5. **Manual keyword hits (custom list)**
   Shown as a comma-separated list or “none”
6. **Metadata (full)**
   Raw metadata JSON shown as a structured JSON viewer

---

## Right column: Quick visuals (filtered set)

### 1) Articles per year (line chart)

Shows the number of filtered articles per year (only if year exists).

### 2) Top tags in filtered set (bar chart)

Shows tag frequency counts for the filtered subset.

Includes a **Tag rank range** slider:

* choose which rank window to show (e.g., ranks 1–20, 10–30)
* helps keep charts readable when there are many tags

---

## Notes & troubleshooting

### “Cluster mode” doesn’t appear

Your merged JSONL likely lacks multi-run cluster columns.
Ensure `merged_for_app.jsonl` contains `clusters.<run>.label` fields.

### App can’t find `out/merged_for_app.jsonl`

Run Streamlit from the folder that contains `out/`:

```bash
cd ~/Documents/Pro\ Gradu_Tampere/Data
streamlit run app2.py
```

### Streamlit command not found

Install it inside the venv:

```bash
source .venv/bin/activate
pip install streamlit
```

---

## License / attribution

Internal research tool for local exploration of a preprocessed dataset. Free to use. All code generated with ChatGPT 5.2. Data from CNKI database.
