import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, Optional


def extract_cnki_id(link: str) -> Optional[str]:
    """
    Extract CNKI filename id from a link like:
    ...detail.aspx?dbcode=CJFD&filename=ELSW201504019&dbname=...
    Returns None if not found.
    """
    if not link:
        return None
    m = re.search(r"(?:\?|&)filename=([A-Za-z0-9]+)", link)
    return m.group(1) if m else None


def guess_language(text: str) -> str:
    """
    Lightweight heuristic:
    - If contains CJK characters -> 'zh'
    - else if contains ASCII letters -> 'en'
    - if both -> 'mixed'
    - else 'unknown'
    """
    if not text:
        return "unknown"

    has_cjk = any("\u4e00" <= ch <= "\u9fff" for ch in text)
    has_latin = any(("A" <= ch <= "Z") or ("a" <= ch <= "z") for ch in text)

    if has_cjk and has_latin:
        return "mixed"
    if has_cjk:
        return "zh"
    if has_latin:
        return "en"
    return "unknown"


def info_list_to_dict(info: Any) -> Dict[str, Any]:
    """
    Normalize the 'info' field (often list of [key, value] pairs)
    into a dictionary. If duplicate keys exist, values become a list.
    If structure is unexpected, returns {}.
    """
    out: Dict[str, Any] = {}
    if not isinstance(info, list):
        return out

    for item in info:
        if isinstance(item, list) and len(item) == 2:
            k, v = item[0], item[1]
            if not k:
                continue
            if k in out:
                if isinstance(out[k], list):
                    out[k].append(v)
                else:
                    out[k] = [out[k], v]
            else:
                out[k] = v
    return out


def build_text_for_embedding(title: str, abstract: str, labeled: bool) -> str:
    title = (title or "").strip()
    abstract = (abstract or "").strip()

    if labeled:
        if abstract and title:
            return f"Title: {title}\nAbstract: {abstract}"
        if abstract and not title:
            return f"Abstract: {abstract}"
        if title and not abstract:
            return f"Title: {title}"
        return ""
    else:
        # plain
        if abstract and title:
            return f"{title}\n{abstract}"
        if abstract and not title:
            return abstract
        if title and not abstract:
            return title
        return ""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Flatten nested scrapingResults.json (journals -> articles) into JSONL (one article per line)."
    )
    parser.add_argument("--input", default="scrapingResults.json", help="Path to input JSON file.")
    parser.add_argument("--output", default="articles_flat.jsonl", help="Path to output JSONL file.")
    parser.add_argument("--id-prefix", default="art_", help="Prefix for your own IDs.")
    parser.add_argument("--id-width", type=int, default=6, help="Zero-padding width for your own IDs.")
    parser.add_argument(
        "--format",
        choices=["labeled", "plain"],
        default="labeled",
        help="Embedding text format: labeled='Title:..\\nAbstract:..' or plain='title\\nabstract'.",
    )
    parser.add_argument(
        "--keep-empty-title",
        action="store_true",
        help="Keep records even if title is empty (default: keep).",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    labeled = (args.format == "labeled")

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path.resolve()}")

    with input_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Expected top-level JSON array (list of journal objects).")

    total_written = 0
    total_skipped_embedding = 0
    next_id_num = 1

    with output_path.open("w", encoding="utf-8") as out:
        for journal in data:
            if not isinstance(journal, dict):
                continue

            # Keep ALL journal-level fields, except we pop 'articles'
            journal_meta = dict(journal)
            articles = journal_meta.pop("articles", [])

            if not isinstance(articles, list):
                continue

            for art in articles:
                if not isinstance(art, dict):
                    continue

                title = (art.get("title") or "").strip()
                abstract = (art.get("abstract") or "").strip()

                if (not args.keep_empty_title) and (not title):
                    # drop if user explicitly asked to drop empty titles
                    continue

                text_for_embedding = build_text_for_embedding(title, abstract, labeled=labeled)

                link = (art.get("link") or "").strip()
                cnki_id = extract_cnki_id(link)

                rec_id = f"{args.id_prefix}{next_id_num:0{args.id_width}d}"
                next_id_num += 1

                embedding_skipped = (text_for_embedding.strip() == "")
                if embedding_skipped:
                    total_skipped_embedding += 1

                # One JSONL record (one line)
                record = {
                    "id": rec_id,                     # your own stable ID
                    "title": title,                   # clean fields for humans/UI
                    "abstract": abstract,
                    "text_for_embedding": text_for_embedding,   # embed ONLY this
                    "metadata": {
                        # Preserve everything that exists (even if fields differ across articles)
                        "journal": journal_meta,        # all journal-level fields
                        "article": art,                 # all article-level fields (raw)
                        "cnki_id": cnki_id,             # extracted separately
                        "has_abstract": bool(abstract),
                        "lang_guess": guess_language(text_for_embedding),
                        "info_dict": info_list_to_dict(art.get("info")),
                        "embedding_skipped": embedding_skipped
                    },
                }

                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                total_written += 1

    print(f"Done.")
    print(f"Wrote {total_written} JSONL records to: {output_path.resolve()}")
    print(f"Records with empty text_for_embedding (embedding_skipped=true): {total_skipped_embedding}")


if __name__ == "__main__":
    main()
