import os
from google import genai

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

print("Has GEMINI_API_KEY:", bool(os.environ.get("GEMINI_API_KEY")))

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
resp = client.models.generate_content(
    model="gemini-3-pro-preview",
    contents="Reply with exactly the word: OK"
)

print("resp.text:", repr(getattr(resp, "text", None)))
print("resp:", resp)
