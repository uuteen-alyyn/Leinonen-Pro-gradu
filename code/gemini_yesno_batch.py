import argparse
import json
import os
import time
from typing import Dict, Any, Iterable, Optional, Set, List

# pip install -U google-genai
from google import genai
from google.genai import types


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
- Provide a short justification (2–6 sentences) citing phrases or claims from the text.
- Output must be STRICT JSON only matching the provided schema.
"""

def load_dotenv(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

load_dotenv(".env")

def require_env(key: str) -> str:
    v = os.environ.get(key, "").strip()
    if not v:
        raise RuntimeError(f"Missing {key}. Set it as an environment variable.")
    return v

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
                cid = row.get("custom_id")
                if cid:
                    done.add(str(cid))
            except json.JSONDecodeError:
                continue
    return done

# ---------------- Prompt + Schema ----------------
def build_prompt(article_text: str) -> str:
    q_lines = "\n".join([f"{qid}: {qtext}" for qid, qtext in QUESTIONS])
    return f"""ARTICLE TEXT:
\"\"\"\n{article_text}\n\"\"\"

QUESTIONS:
{q_lines}

Return JSON only.
"""

def build_response_json_schema() -> Dict[str, Any]:
    """
    JSON schema for Gemini Structured Outputs.
    We require ALL answer keys + non-empty justification.
    """
    answers_props = {qid: {"type": "integer", "enum": [0, 1]} for qid in QIDS}
    return {
        "type": "object",
        "properties": {
            "answers": {
                "type": "object",
                "properties": answers_props,
                "required": QIDS,
                "additionalProperties": False,
            },
            "justification": {
                "type": "string",
                "minLength": 40,
                "description": "2–6 sentences citing evidence from the article text."
            },
        },
        "required": ["answers", "justification"],
        "additionalProperties": False,
    }

def normalize_answers(obj: Dict[str, Any]) -> Dict[str, Any]:
    # Extra safety: coerce to required shape even if model returns something odd.
    out = {"answers": {qid: 0 for qid in QIDS}, "justification": ""}
    if isinstance(obj, dict):
        ans = obj.get("answers", {})
        if isinstance(ans, dict):
            for qid in QIDS:
                v = ans.get(qid, 0)
                out["answers"][qid] = 1 if v == 1 or v is True or str(v).strip() == "1" else 0
        just = obj.get("justification", "")
        if isinstance(just, str):
            out["justification"] = just.strip()
    return out

# ---------------- Gemini call ----------------
def call_gemini(
    client: genai.Client,
    model: str,
    prompt: str,
    max_output_tokens: int,
    temperature: float,
) -> str:
    # Build a typed schema (SDK-native), NOT a plain dict schema.
    answers_properties = {
        qid: types.Schema(type=types.Type.INTEGER, enum=[0, 1])
        for qid in QIDS
    }

    schema = types.Schema(
        type=types.Type.OBJECT,
        required=["answers", "justification"],
        properties={
            "answers": types.Schema(
                type=types.Type.OBJECT,
                required=QIDS,
                properties=answers_properties,
            ),
            "justification": types.Schema(
                type=types.Type.STRING,
                min_length="40",  # note: string is required by python-genai
                description="2–6 sentences citing evidence from the article text.",
            ),
        },
    )

    cfg = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTIONS,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
        response_mime_type="application/json",
        response_schema=schema,  # IMPORTANT: response_schema (not response_json_schema)
    )

    resp = client.models.generate_content(
        model=model,
        contents=prompt,
        config=cfg,
    )

    text = (getattr(resp, "text", "") or "").strip()
    if not text:
        raise RuntimeError("Gemini returned empty text (possibly safety blocked).")
    return text


# ---------------- Main ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", required=True, help="Input JSONL path (e.g., merged_for_app.jsonl)")
    ap.add_argument("--out", dest="out_path", required=True, help="Output JSONL path")
    ap.add_argument("--model", default="gemini-3-flash-preview", help="Gemini model name")
    ap.add_argument("--id-field", default="id", help="Field name for article id (default: id)")
    ap.add_argument("--text-field", default="text", help="Field name for article text (default: text)")
    ap.add_argument("--also-store", default="cnki_id", help="Extra field to copy to output (default: cnki_id). Use '' to disable.")
    ap.add_argument("--max-output-tokens", type=int, default=1200)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--sleep", type=float, default=0.2)
    ap.add_argument("--max-retries", type=int, default=3)
    ap.add_argument("--resume", action="store_true", help="Skip ids already in --out")
    ap.add_argument("--dry-run", action="store_true", help="Print extracted ids + text preview and exit (no API calls)")
    args = ap.parse_args()

    # Ensure API key exists
    api_key = require_env("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)

    done_ids = load_done_ids(args.out_path) if args.resume else set()
    schema = build_response_json_schema()

    wrote = 0
    for row in iter_jsonl(args.in_path):
        article_id = str(row.get(args.id_field, "")).strip()
        if not article_id:
            raise ValueError(f"Missing '{args.id_field}' in a row; cannot safely map outputs.")

        if args.resume and article_id in done_ids:
            continue

        text = row.get(args.text_field, "")
        if not isinstance(text, str):
            text = str(text)

        if args.dry_run:
            preview = text[:200].replace("\n", "\\n")
            print(f"{article_id}\t{preview}")
            continue

        prompt = build_prompt(text)

        parsed: Optional[Dict[str, Any]] = None
        last_err: Optional[str] = None
        raw_text: Optional[str] = None

        for attempt in range(1, args.max_retries + 1):
            try:
                raw_text = call_gemini(
                    client=client,
                    model=args.model,
                    prompt=prompt,
                    max_output_tokens=args.max_output_tokens,
                    temperature=args.temperature,
                )

                obj = json.loads(raw_text)
                parsed = normalize_answers(obj)
                last_err = None
                break
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                time.sleep(min(5.0, attempt * 1.0))

        out_row: Dict[str, Any] = {
            "custom_id": article_id,
            "provider": "gemini",
            "model": args.model,
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
