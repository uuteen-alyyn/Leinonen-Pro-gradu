import json
import re
import deepl
from tqdm import tqdm
from langdetect import detect, LangDetectException

INPUT_PATH = "articles_flat.jsonl"
OUTPUT_PATH = "articles_translated_en.jsonl"

def load_deepl_api_key(path="Deepl_API_KEY.txt"):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()



def is_mostly_english(text):
    try:
        return detect(text) == "en"
    except LangDetectException:
        return False


def main():
    api_key = load_deepl_api_key()
    translator = deepl.Translator(api_key)


    with open(INPUT_PATH, "r", encoding="utf-8") as fin, \
         open(OUTPUT_PATH, "w", encoding="utf-8") as fout:

        for line in tqdm(fin, desc="Translating with DeepL"):
            obj = json.loads(line)

            title = obj.get("title", "")
            abstract = obj.get("abstract", "")

            # Translate title
            if title and not is_mostly_english(title):
                title_en = translator.translate_text(
                    title,
                    source_lang="ZH",
                    target_lang="EN-GB"
                ).text
            else:
                title_en = title

            # Translate abstract
            if abstract and not is_mostly_english(abstract):
                abstract_en = translator.translate_text(
                    abstract,
                    source_lang="ZH",
                    target_lang="EN-GB"
                ).text
            else:
                abstract_en = abstract

            out = {
                "id": obj["id"],
                "title_en": title_en,
                "abstract_en": abstract_en
            }

            fout.write(json.dumps(out, ensure_ascii=False) + "\n")

    print(f"\nFinished. Saved translations to: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

