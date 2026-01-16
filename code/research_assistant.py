import argparse
import json
import os
import time
from typing import Dict, Any, Iterable, Optional

# pip install -U google-genai
from google import genai
from google.genai import types

# ---------------- Questions Definition ----------------
QUESTIONS = [
    ("A1", "Does the article suggest that some level of government has the ability to alleviate the problem?"),
    ("A2", "Does the article suggest that some level of the government is responsible for the problem?"),
    ("A3", "Does the article suggest solution(s) to the problem?"),
    ("A4", "Does the article make references to moral, religious or philosophical tenets?"),
    ("A5", "Does the article frame actions as good and / or evil, or compare the acceptability of the actions of different actors to one another?"),
    ("A6", "Does the article offer specific social prescriptions about how to behave?"),
    ("A7", "Does the article specifically reference traditional / civilizational value systems?"),
    ("A8", "Does the article portray Russia as a pro-active actor changing the world?"),
    ("A9", "Does the article portray Russia as a reactive actor trying to cope with the changing world?"),
    ("A10", "Does regional cooperation or the international community play a major in solving the problem?"),
    ("B1", "Does the story reflect disagreement between parties-individuals-groups-countries?"),
    ("B2", "Does the story refer to two sides or more of the problem or issue?"),
    ("B3", "Does the conflict involve or threaten vital national interests?"),
    ("B4", "Is there a mention of financial losses or gains?"),
    ("B5", "Is there a reference to economic consequences of a course of action?"),
    ("B6", "Does the article talk about a win-win situation or shared economic benefit?"),
    ("B7", "Does the article set the welfare of humans/citizens as a major goal?"),
    ("B8", "Does the article reference armscontrol, detente or peace mediation?"),
    ("B9", "Does the article talk about climate change or ecological issues?"),
    ("B10", "Does the article talk about sustainable development (poverty, education)?"),
]
QIDS = [qid for qid, _ in QUESTIONS]

SYSTEM_INSTRUCTIONS = """You are a careful research assistant.
Rules:
- Answer ONLY using the provided article text.
- For each question, answer "1" for Yes and "0" for No.
- Provide a justification (2-6 sentences) citing the text.
"""

def load_dotenv():
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                if "=" in line and not line.startswith("#"):
                    k, v = line.strip().split("=", 1)
                    os.environ[k.strip()] = v.strip().strip("'").strip('"')

def call_gemini(client, model, prompt):
    # STABILITY FIX: Use STRING type for both definition and enum to satisfy backend + validator
    ans_props = {qid: types.Schema(type=types.Type.STRING, enum=["0", "1"]) for qid in QIDS}
    
    response_schema = types.Schema(
        type=types.Type.OBJECT,
        required=["answers", "justification"],
        properties={
            "answers": types.Schema(type=types.Type.OBJECT, required=QIDS, properties=ans_props),
            "justification": types.Schema(type=types.Type.STRING),
        }
    )

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTIONS,
        temperature=0.0,
        response_mime_type="application/json",
        response_schema=response_schema,
        # Standard safety settings
        safety_settings=[
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_ONLY_HIGH"),
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_ONLY_HIGH"),
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_ONLY_HIGH"),
            types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_ONLY_HIGH"),
        ]
    )

    resp = client.models.generate_content(model=model, contents=prompt, config=config)
    
    if not resp.text:
        raise RuntimeError("Empty response from API.")
    
    return resp.text

def main():
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="in_file", required=True)
    parser.add_argument("--out", dest="out_file", required=True)
    args = parser.parse_args()

    client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    
    processed_count = 0
    # Read existing IDs to allow resuming
    done_ids = set()
    if os.path.exists(args.out_file):
        with open(args.out_file, "r", encoding="utf-8") as f:
            for line in f:
                try: done_ids.add(json.loads(line).get("custom_id"))
                except: pass

    with open(args.in_file, "r", encoding="utf-8") as fin, \
         open(args.out_file, "a", encoding="utf-8") as fout:
        
        for line in fin:
            row = json.loads(line)
            art_id = str(row.get("id", "unknown"))
            if art_id in done_ids: continue
            
            text = row.get("text", "")
            print(f"Processing: {art_id}...")
            
            try:
                # Build Prompt
                q_list = "\n".join([f"{qid}: {txt}" for qid, txt in QUESTIONS])
                prompt = f"ARTICLE TEXT:\n{text}\n\nQUESTIONS:\n{q_list}\n\nReturn JSON."

                raw_json = call_gemini(client, "gemini-2.0-flash", prompt)
                data = json.loads(raw_json)
                
                # COERCION FIX: Turn string "0"/"1" back into integers for your final dataset
                clean_answers = {k: int(v) for k, v in data.get("answers", {}).items()}
                
                result = {
                    "custom_id": art_id,
                    "answers": clean_answers,
                    "justification": data.get("justification", ""),
                    "error": None
                }
                processed_count += 1
                print(f"Success: {art_id}")
            except Exception as e:
                result = {"custom_id": art_id, "error": str(e)}
                print(f"Error on {art_id}: {e}")

            fout.write(json.dumps(result, ensure_ascii=False) + "\n")
            time.sleep(2) # Safe rate limit for free/standard tier

    print(f"\nFinished. Processed {processed_count} new articles.")

if __name__ == "__main__":
    main()