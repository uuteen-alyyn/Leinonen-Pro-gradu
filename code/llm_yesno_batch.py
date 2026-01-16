import argparse
import json
import os
import time
from typing import Dict, Any, Iterable, List, Optional, Set

# ---------------- Optional: load keys from .env ----------------

def load_dotenv(dotenv_path: str = ".env") -> None:
    if not os.path.exists(dotenv_path):
        return
    with open(dotenv_path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and (k not in os.environ):
                os.environ[k] = v

load_dotenv(".env")

# ---------------- Questions ----------------

QUESTIONS = [
    ("A1", "Does the article suggest that some level of government has the ability to alleviate the problem?"),
    ("A2", "Does the article suggest that some level of the government is responsible for the problem?"),
    ("A3", "Does the article suggest solution(s) to the problem?"),
    ("A4", "Does the article make references to moral, religious or philosophical tenets?"),
    ("A5", "Does the article frame actions as good and / or evil, or compare the acceptability of the actions of different actors to one another?"),
    ("A6", "Does the article offer specific social prescriptions about how to behave?"),
    ("A7", "Does the article spesifically reference European, Western, Chinese, Confucian, Russian or any other types of traditional / civilizational value systems?"),
    ("A8", "Does the article portray Russia as a pro-active actor changing the world?"),
    ("A9", "Does the article portray Russia as a reactive actor trying to cope with the changing world?"),
    ("A10", "Does regional (multilateral) cooperation or the international community play a major in solving the central problem of the article?"),
    ("B1", "Does the story reflect disagreement between parties-individuals-groups-countries?"),
    ("B2", "Does the story refer to two sides or to more than two sides of the problem or issue?"),
    ("B3", "Does the conflict involve, affect or even threaten vital national interests of a conflict party?"),
    ("B4", "Is there a mention of financial losses or gains now or in the future?"),
    ("B5", "Is there a reference to economic consequences of pursuing or not pursuing a course of action?"),
    ("B6", "Does the article talk about a win-win situation or a shared economic benefit for both parties?"),
    ("B7", "Does the article set the welfare of humans, citizens or communities as a major goal for action?"),
    ("B8", "Does the article reference the questions of armscontrol, detente or peace mediation?"),
    ("B9", "Does the article talk about climate change or ecological issues as a central problem?"),
    ("B10", "Does the article talk about eradicating poverty, increasing education or other sustainable development as a central problem?"),
]
QIDS = [qid for qid, _ in QUESTIONS]

SYSTEM_INSTRUCTIONS = """You are a careful research assistant.
Rules:
- Answer ONLY using information contained in the provided article text. Do not use outside knowledge.
- Each question must be answered with exactly 1 or 0 (1=yes, 0=no).
- If the article does not clearly justify "yes", answer 0.
- After the 20 answers, write a 1–2 paragraph justification explaining the main textual evidence you relied on.
- Output must be STRICT JSON only, matching the schema exactly.
"""

def build_user_prompt(article_text: str) -> str:
    q_lines = "\n".join([f"{qid}: {qtext}" for qid, qtext in QUESTIONS])
    return f"""ARTICLE TEXT (analyze carefully):
\"\"\"\n{article_text}\n\"\"\"

QUESTIONS:
{q_lines}

Return STRICT JSON in exactly this shape (no extra keys, no markdown, no commentary outside JSON):
{{
  "answers": {{
    "A1": 0, "A2": 0, "A3": 0, "A4": 0, "A5": 0,
    "A6": 0, "A7": 0, "A8": 0, "A9": 0, "A10": 0,
    "B1": 0, "B2": 0, "B3": 0, "B4": 0, "B5": 0,
    "B6": 0, "B7": 0, "B8": 0, "B9": 0, "B10": 0
  }},
  "justification": "1-2 paragraphs explaining evidence from the article text"
}}
"""

# ---------------- JSONL IO ----------------

def iter_jsonl(path: str) -> Iterable[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON on line {line_no}: {e}") from e

def append_jsonl(out_path: str, row: Dict[str, Any]) -> None:
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

def load_done_ids(out_path: str) -> Set[str]:
    done: Set[str] = set()
    if not os.path.exists(out_path):
        return done
    with open(out_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                if "custom_id" in row:
                    done.add(str(row["custom_id"]))
            except json.JSONDecodeError:
                continue
    return done

# ---------------- Parsing + validation ----------------

def parse_json_strict(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise

def normalize_answers(obj: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(obj, dict) or "answers" not in obj or "justification" not in obj:
        raise ValueError("Response must contain 'answers' and 'justification'.")

    ans = obj["answers"]
    if not isinstance(ans, dict):
        raise ValueError("'answers' must be an object.")

    fixed: Dict[str, int] = {}
    for qid in QIDS:
        v = ans.get(qid, 0)
        if isinstance(v, bool):
            fixed[qid] = 1 if v else 0
        elif isinstance(v, (int, float)):
            fixed[qid] = 1 if int(v) == 1 else 0
        elif isinstance(v, str):
            fixed[qid] = 1 if v.strip() == "1" else 0
        else:
            fixed[qid] = 0

    just = obj.get("justification", "")
    if not isinstance(just, str):
        just = ""
    return {"answers": fixed, "justification": just.strip()}

# ---------------- Provider calls ----------------

def require_env(key_name: str) -> str:
    v = os.environ.get(key_name, "").strip()
    if not v:
        raise RuntimeError(f"Missing {key_name}. Put it in .env or set it as an environment variable.")
    return v

def call_openai(model: str, user_prompt: str, max_output_tokens: int, temperature: float) -> str:
    # Requires: pip install -U openai httpx
    from openai import OpenAI
    api_key = require_env("OPENAI_API_KEY")
    client = OpenAI(api_key=api_key)
    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": SYSTEM_INSTRUCTIONS},
            {"role": "user", "content": user_prompt},
        ],
        max_output_tokens=max_output_tokens,
        temperature=temperature,
    )
    return resp.output_text

def call_anthropic(model: str, user_prompt: str, max_output_tokens: int, temperature: float) -> str:
    import anthropic
    api_key = require_env("ANTHROPIC_API_KEY")
    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model=model,
        max_tokens=max_output_tokens,
        temperature=temperature,
        system=SYSTEM_INSTRUCTIONS,
        messages=[{"role": "user", "content": user_prompt}],
    )
    parts: List[str] = []
    for block in msg.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
    return "\n".join(parts).strip()

def _chunk_text_by_chars(text: str, max_chars: int = 12000) -> List[str]:
    """
    Very simple chunker by character count.
    Keeps it deterministic and avoids tokenizers.
    """
    text = text or ""
    chunks = []
    i = 0
    n = len(text)
    while i < n:
        chunks.append(text[i:i + max_chars])
        i += max_chars
    return chunks


def call_gemini(model: str, user_prompt: str, max_output_tokens: int, temperature: float) -> str:
    # pip install google-genai
    from google import genai
    from google.genai import types
    import json as _json

    api_key = require_env("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)

    # --- Extract the article text back out of the user_prompt so we can chunk it safely ---
    # user_prompt format includes:
    # ARTICLE TEXT:
    # """\n{article_text}\n"""
    marker_start = 'ARTICLE TEXT (analyze carefully):\n"""'
    marker_end = '"""\n\nQUESTIONS:'
    if marker_start not in user_prompt or marker_end not in user_prompt:
        raise RuntimeError("Internal: cannot locate article text in prompt for chunking.")

    article_text = user_prompt.split(marker_start, 1)[1].split(marker_end, 1)[0]
    article_text = article_text.strip("\n")

    # Chunk large articles
    chunks = _chunk_text_by_chars(article_text, max_chars=12000)

    # We ask Gemini to answer per-chunk, then we aggregate:
    # - If ANY chunk says 1 => final 1
    # - Otherwise final 0
    # Justification: combine short evidence lines from chunks that triggered 1s.
    chunk_answers = []
    chunk_justs = []

    cfg = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTIONS,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        # IMPORTANT: do NOT force response_mime_type for now
    )

    # Build a smaller per-chunk prompt
    q_lines = user_prompt.split("QUESTIONS:\n", 1)[1]

    for ci, ch in enumerate(chunks, start=1):
        chunk_prompt = f"""You are analyzing CHUNK {ci}/{len(chunks)} of the same article.
Only use this chunk to answer. If the answer is not clearly supported in this chunk, output 0.

CHUNK TEXT:
\"\"\"\n{ch}\n\"\"\"

QUESTIONS:
{q_lines}
"""
        resp = client.models.generate_content(model=model, contents=chunk_prompt, config=cfg)

        # Pull text
        raw = (getattr(resp, "text", "") or "").strip()
        if not raw:
            # fallback to parts
            try:
                parts_txt = []
                for cand in (getattr(resp, "candidates", None) or []):
                    content = getattr(cand, "content", None)
                    if not content:
                        continue
                    for part in (getattr(content, "parts", None) or []):
                        t = getattr(part, "text", None)
                        if t:
                            parts_txt.append(t)
                raw = "".join(parts_txt).strip()
            except Exception:
                raw = ""

        if not raw:
            # Print diagnostics that explain "empty"
            try:
                print("---- GEMINI EMPTY TEXT DIAGNOSTICS ----")
                print("prompt_feedback:", getattr(resp, "prompt_feedback", None) or getattr(resp, "promptFeedback", None))
                cands = getattr(resp, "candidates", None) or []
                print("num_candidates:", len(cands))
                if cands:
                    c0 = cands[0]
                    print("finish_reason:", getattr(c0, "finish_reason", None) or getattr(c0, "finishReason", None))
                    print("safety_ratings:", getattr(c0, "safety_ratings", None) or getattr(c0, "safetyRatings", None))
                    content = getattr(c0, "content", None)
                    parts = getattr(content, "parts", None) or []
                    print("num_parts:", len(parts))
                    print("part_types:", [type(p).__name__ for p in parts])
            except Exception as dbg_e:
                print("diagnostics_failed:", repr(dbg_e))

            raise RuntimeError("Gemini returned empty text for a chunk (see diagnostics above).")
    
        obj = parse_json_strict(raw)
        norm = normalize_answers(obj)
        chunk_answers.append(norm["answers"])
        chunk_justs.append(norm["justification"])

    # Aggregate answers
    final = {qid: 0 for qid in QIDS}
    for qid in QIDS:
        if any(a.get(qid, 0) == 1 for a in chunk_answers):
            final[qid] = 1

    # Aggregate justification (keep it short)
    # Use up to ~2 chunks’ justifications to stay concise.
    just_parts = [j for j in chunk_justs if j]
    if len(just_parts) > 2:
        just_parts = just_parts[:2]
    final_just = "\n\n".join(just_parts).strip()

    return _json.dumps({"answers": final, "justification": final_just}, ensure_ascii=False)


def call_provider(provider: str, model: str, prompt: str, max_output_tokens: int, temperature: float) -> str:
    if provider == "openai":
        return call_openai(model, prompt, max_output_tokens, temperature)
    if provider == "anthropic":
        return call_anthropic(model, prompt, max_output_tokens, temperature)
    if provider == "gemini":
        return call_gemini(model, prompt, max_output_tokens, temperature)
    raise ValueError(f"Unknown provider: {provider}")

# ---------------- Helpers: id lists ----------------

def parse_id_list(s: str) -> Set[str]:
    s = (s or "").strip()
    if not s:
        return set()
    parts = [p.strip() for p in s.split(",")]
    return {p for p in parts if p}

# ---------------- Main ----------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True, help="Input JSONL path")
    ap.add_argument("--out", dest="out_path", required=True, help="Output JSONL path")
    ap.add_argument("--provider", choices=["openai", "anthropic", "gemini"], required=True)
    ap.add_argument("--model", required=True, help="Model ID (provider-specific)")
    ap.add_argument("--id-field", default="id", help="Field name for article id (default: id)")
    ap.add_argument("--text-field", default="text", help="Field name for article text (default: text)")
    ap.add_argument("--also-store", default="cnki_id", help="Extra field to copy to output (default: cnki_id). Use '' to disable.")
    ap.add_argument("--max-output-tokens", type=int, default=1400)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--sleep", type=float, default=0.2)
    ap.add_argument("--max-retries", type=int, default=3)
    ap.add_argument("--resume", action="store_true", help="Skip ids already in --out")
    ap.add_argument("--skip-ids", default="", help="Comma-separated ids to SKIP, e.g. art_000240,art_000241")
    ap.add_argument("--only-ids", default="", help="Comma-separated ids to process ONLY these, e.g. art_000240,art_000241")
    ap.add_argument("--dry-run", action="store_true", help="Print extracted ids + text preview and exit (no API calls)")
    args = ap.parse_args()

    skip_ids = parse_id_list(args.skip_ids)
    only_ids = parse_id_list(args.only_ids)
    done_ids = load_done_ids(args.out_path) if args.resume else set()

    wrote = 0
    for row in iter_jsonl(args.in_path):
        article_id = str(row.get(args.id_field, "")).strip()
        text = row.get(args.text_field, "")
        if not isinstance(text, str):
            text = str(text)

        if not article_id:
            raise ValueError(f"Missing '{args.id_field}' in a row; cannot safely map outputs.")

        if only_ids and article_id not in only_ids:
            continue
        if article_id in skip_ids:
            continue
        if args.resume and article_id in done_ids:
            continue

        if args.dry_run:
            preview = text[:200].replace("\n", "\\n")
            print(f"{article_id}\t{preview}")
            continue

        user_prompt = build_user_prompt(text)

        parsed = None
        last_err = None
        raw_text = None

        for attempt in range(1, args.max_retries + 1):
            try:
                raw_text = call_provider(
                    provider=args.provider,
                    model=args.model,
                    prompt=user_prompt,
                    max_output_tokens=args.max_output_tokens,
                    temperature=args.temperature,
                )
                obj = parse_json_strict(raw_text)
                parsed = normalize_answers(obj)
                last_err = None
                break
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                time.sleep(min(5.0, attempt * 1.0))

        out_row = {
            "custom_id": article_id,
            "provider": args.provider,
            "model": args.model,
            "raw": raw_text,
            "answers": (parsed["answers"] if parsed else {qid: 0 for qid in QIDS}),
            "justification": (parsed["justification"] if parsed else ""),
            "error": last_err,
        }
        if args.also_store:
            out_row[args.also_store] = row.get(args.also_store, "")

        append_jsonl(args.out_path, out_row)
        wrote += 1
        time.sleep(max(0.0, args.sleep))

    if args.dry_run:
        print("Dry-run complete (no API calls made).")
    else:
        print(f"Done. Wrote {wrote} rows to {args.out_path}.")

if __name__ == "__main__":
    main()
