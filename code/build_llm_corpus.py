# build_llm_corpus.py
# -*- coding: utf-8 -*-
"""
Batch:
- Read PDFs from:
    BRICS-artikkelit\
    Keski-Aasia-artikkelit\
- Extract full text (text-based PDFs)
- Extract an inferred title from first page
- Match that title to merged_for_app.jsonl titles (fuzzy)
- Output:
    llm_corpus.jsonl  (API-ready: one JSON per article with id + full text)
    llm_mapping_review.csv  (human review of matches, incl. warnings)
"""

import json
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pdfplumber
from rapidfuzz import fuzz, process  # pip install rapidfuzz


# -----------------------
# Paths (relative to this script)
# -----------------------
BASE_DIR = Path(__file__).resolve().parent
JSONL_PATH = BASE_DIR / "merged_for_app.jsonl"

PDF_DIRS = [
    BASE_DIR / "BRICS-artikkelit",
    BASE_DIR / "Keski-Aasia-artikkelit",
]

OUT_JSONL = BASE_DIR / "llm_corpus.jsonl"
OUT_REVIEW = BASE_DIR / "llm_mapping_review.csv"


# -----------------------
# Matching thresholds
# -----------------------
FUZZY_GOOD = 92   # confident match
FUZZY_MIN = 85    # below => id=None + warning


# -----------------------
# Normalization helpers
# -----------------------
CH_PUNCT_RE = re.compile(r"[，。！？；：、（）《》〈〉【】「」『』“”‘’—…·]")
LAT_PUNCT_RE = re.compile(r"[!\"#$%&'()*+,\-./:;<=>?@\[\]^_`{|}~]")
WS_RE = re.compile(r"\s+")
HAS_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def normalize_for_match(s: str) -> str:
    """Normalize to improve title matching across PDF vs JSONL."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = s.strip()
    s = CH_PUNCT_RE.sub("", s)
    s = LAT_PUNCT_RE.sub("", s)
    s = WS_RE.sub("", s)
    return s.lower()

def looks_like_title(line: str) -> bool:
    """Heuristic to identify a likely title line (avoid URLs/footnotes/metadata)."""
    if not line:
        return False
    l = line.strip()

    if len(l) < 6:
        return False
    if "http://" in l or "https://" in l or "www." in l:
        return False
    # footnote-ish lines like "① ..." or "[1] ..." etc.
    if re.match(r"^[\[\(（]?\d+[\]\)）]?", l) or l.startswith(("①", "②", "③", "④", "⑤")):
        return False

    bad_starts = (
        "摘要", "关键词", "作者", "基金", "分类号", "中图分类号", "DOI", "收稿",
        "引用", "参考文献", "【摘要】", "【关键词】", "［内容摘要］", "［关键词］"
    )
    if any(l.startswith(x) for x in bad_starts):
        return False

    # must contain some CJK
    return bool(HAS_CJK_RE.search(l))


def pick_title_candidates_from_text(full_text: str, max_lines: int = 80) -> List[str]:
    """
    Produce multiple plausible title candidates from the beginning of extracted text.
    CNKI PDFs usually have title as the first non-empty line.
    """
    if not full_text:
        return []

    lines = [ln.strip() for ln in full_text.splitlines()]
    lines = [ln for ln in lines if ln]  # non-empty

    # Take early region only
    head = lines[:max_lines]

    # Keep title-like lines
    cands = [ln for ln in head if looks_like_title(ln)]

    # Fallback: if filtering too strict, keep any CJK lines (still excluding URLs)
    if not cands:
        cands = [ln for ln in head if HAS_CJK_RE.search(ln) and "http" not in ln.lower()]

    # Deduplicate while preserving order
    seen = set()
    uniq = []
    for c in cands:
        key = normalize_for_match(c)
        if key and key not in seen:
            seen.add(key)
            uniq.append(c)
    return uniq


# -----------------------
# PDF extraction
# -----------------------
def extract_pdf_text(pdf_path: Path) -> Tuple[str, str, int]:
    """Return (full_text, first_page_text, num_pages)."""
    full_parts: List[str] = []
    first_page_text = ""
    num_pages = 0

    with pdfplumber.open(str(pdf_path)) as pdf:
        num_pages = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            txt = page.extract_text() or ""
            if i == 0:
                first_page_text = txt
            if txt:
                full_parts.append(txt)

    full_text = "\n\n".join(full_parts).strip()
    return full_text, first_page_text.strip(), num_pages


# -----------------------
# JSONL loading (your confirmed schema)
# -----------------------
def load_jsonl_candidates(jsonl_path: Path) -> List[Dict]:
    """
    Build candidate list from merged_for_app.jsonl.

    Prefer: metadata.article.title
    Fallback: top-level title

    Keep useful metadata for traceability:
    - id
    - cnki_id
    - metadata.article.link
    - author, year, journalName
    """
    candidates = []
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)

            rec_id = obj.get("id")
            top_title = (obj.get("title") or "").strip()

            meta = obj.get("metadata", {}) or {}
            art = meta.get("article", {}) or {}
            journal = meta.get("journal", {}) or {}

            title = (art.get("title") or top_title or "").strip()
            if not title:
                continue

            candidates.append({
                "id": rec_id,
                "title": title,
                "title_norm": normalize_for_match(title),
                "author": (art.get("author") or "").strip(),
                "year": art.get("year", None),
                "cnki_id": (meta.get("cnki_id") or "").strip(),
                "link": (art.get("link") or "").strip(),
                "journalName": (journal.get("journalName") or "").strip(),
            })
    return candidates


# -----------------------
# Matching
# -----------------------
def best_match(pdf_text: str, candidates: List[Dict]) -> Tuple[Optional[Dict], int, str]:
    """
    Match by trying multiple candidate title lines from the PDF text.
    Returns (best_candidate, score, chosen_pdf_title_line).
    """
    title_to_candidate = {c["title"]: c for c in candidates}

    def scorer(a: str, b: str, **kwargs) -> float:
        return fuzz.ratio(normalize_for_match(a), normalize_for_match(b))

    pdf_title_candidates = pick_title_candidates_from_text(pdf_text, max_lines=80)
    if not pdf_title_candidates:
        return None, 0, ""

    best_overall = None
    best_score = -1
    best_pdf_title = ""

    # Try each candidate line as a query; pick the best result overall
    for q in pdf_title_candidates[:25]:  # cap for speed
        m = process.extractOne(
            query=q,
            choices=list(title_to_candidate.keys()),
            scorer=scorer,
        )
        if not m:
            continue
        best_title, score, _idx = m
        score = int(score)
        if score > best_score:
            best_score = score
            best_overall = title_to_candidate[best_title]
            best_pdf_title = q

    return best_overall, (best_score if best_score >= 0 else 0), best_pdf_title


# -----------------------
# File iteration
# -----------------------
def iter_pdfs(root_dirs: List[Path]) -> List[Path]:
    pdfs: List[Path] = []
    for d in root_dirs:
        if d.exists():
            pdfs.extend(d.rglob("*.pdf"))  # includes subfolders
    return sorted(pdfs)


def csv_clean(s: str) -> str:
    return (s or "").replace("\n", " ").replace("\r", " ").strip()


# -----------------------
# Main
# -----------------------
def main() -> None:
    if not JSONL_PATH.exists():
        raise FileNotFoundError(f"Missing {JSONL_PATH}")

    candidates = load_jsonl_candidates(JSONL_PATH)
    if not candidates:
        raise RuntimeError("No candidates loaded from merged_for_app.jsonl")

    pdf_paths = iter_pdfs(PDF_DIRS)
    if not pdf_paths:
        raise RuntimeError("No PDFs found in BRICS-artikkelit / Keski-Aasia-artikkelit")

    # Prepare output files
    OUT_JSONL.write_text("", encoding="utf-8")
    OUT_REVIEW.write_text(
        "pdf_file,pdf_title_extracted,match_score,jsonl_id,jsonl_title,jsonl_author,jsonl_year,cnki_id,link,warning\n",
        encoding="utf-8"
    )

    unsure = 0
    exported = 0

    for pdf_path in pdf_paths:
        full_text, first_page_text, num_pages = extract_pdf_text(pdf_path)

        best, score, pdf_title = best_match(full_text, candidates)

        warning = ""
        matched_id = None
        matched_title = None
        matched_author = ""
        matched_year = None
        matched_cnki_id = ""
        matched_link = ""

        if best and score >= FUZZY_MIN:
            matched_id = best["id"]
            matched_title = best["title"]
            matched_author = best.get("author", "")
            matched_year = best.get("year", None)
            matched_cnki_id = best.get("cnki_id", "")
            matched_link = best.get("link", "")
        else:
            warning = f"LOW_MATCH(score<{FUZZY_MIN})"
            unsure += 1

        # Extra warning if text extraction looks empty
        if not full_text:
            warning = (warning + "; " if warning else "") + "EMPTY_TEXT_EXTRACTED"

        out_obj = {
            # Identity + traceability
            "id": matched_id,  # may be None
            "jsonl_title": matched_title,
            "pdf_title_extracted": pdf_title,
            "match_score": score,
            "pdf_file": str(pdf_path.relative_to(BASE_DIR)),
            "num_pages": num_pages,

            # Useful metadata for later analysis / auditing
            "author": matched_author,
            "year": matched_year,
            "cnki_id": matched_cnki_id,
            "cnki_link": matched_link,

            # Main payload for LLM
            "text": full_text,
        }

        with OUT_JSONL.open("a", encoding="utf-8") as f_out:
            f_out.write(json.dumps(out_obj, ensure_ascii=False) + "\n")

        with OUT_REVIEW.open("a", encoding="utf-8") as f_rev:
            f_rev.write(
                f"{csv_clean(str(pdf_path.relative_to(BASE_DIR)))},"
                f"{csv_clean(pdf_title)},"
                f"{score},"
                f"{csv_clean(matched_id or '')},"
                f"{csv_clean(matched_title or '')},"
                f"{csv_clean(matched_author)},"
                f"{csv_clean(str(matched_year) if matched_year is not None else '')},"
                f"{csv_clean(matched_cnki_id)},"
                f"{csv_clean(matched_link)},"
                f"{csv_clean(warning)}\n"
            )

        exported += 1

    print(f"Done. Exported {exported} PDFs -> {OUT_JSONL.name}")
    print(f"Review file: {OUT_REVIEW.name}")
    print(f"Uncertain matches (id=None): {unsure} (score < {FUZZY_MIN})")


if __name__ == "__main__":
    main()
