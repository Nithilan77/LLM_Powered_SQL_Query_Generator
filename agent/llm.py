"""
llm.py  --  Provider-agnostic SQL generation. Supports Groq and Gemini.

The ONLY file that knows which LLM provider we use. Everything else calls
generate_sql(prompt) and gets back a SQL string.

Pick the provider with LLM_PROVIDER in your .env:
    LLM_PROVIDER=groq     (default; uses GROQ_API_KEY)
    LLM_PROVIDER=gemini   (uses GEMINI_API_KEY)

Why this design:
  - One place to swap providers (a real interview talking point).
  - Groq's free tier (30 RPM / 14,400 RPD) makes the full eval + ablation
    feasible, where Gemini's 20/day did not.
  - Groq is OpenAI-API-compatible, so we use the openai SDK pointed at Groq.
"""

import os
import re
import time

from dotenv import load_dotenv

load_dotenv()

PROVIDER = os.environ.get("LLM_PROVIDER", "groq").lower()
MAX_RETRIES = 4

# Model per provider (override with LLM_MODEL if you want).
_DEFAULT_MODELS = {
    "groq": "llama-3.3-70b-versatile",
    "gemini": "gemini-2.5-flash-lite",
}
MODEL = os.environ.get("LLM_MODEL", _DEFAULT_MODELS.get(PROVIDER, "llama-3.3-70b-versatile"))

_SYSTEM = (
    "You are an expert data analyst who writes correct, efficient SQLite SQL. "
    "Return ONLY the SQL query, no explanation, no markdown fences."
)

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client

    if PROVIDER == "groq":
        from openai import OpenAI
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY not set in .env")
        _client = OpenAI(api_key=key, base_url="https://api.groq.com/openai/v1")
    elif PROVIDER == "gemini":
        from google import genai
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY not set in .env")
        _client = genai.Client(api_key=key)
    else:
        raise RuntimeError(f"Unknown LLM_PROVIDER: {PROVIDER}")
    return _client


def _strip_sql_fences(text: str) -> str:
    text = text.strip()
    fence = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1)
    return text.strip().rstrip(";").strip()


def _is_quota_error(msg: str) -> bool:
    msg = msg.lower()
    return "429" in msg or "resource_exhausted" in msg or "rate limit" in msg or "quota" in msg


def _call_groq(prompt: str, temperature: float) -> str:
    client = _get_client()
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=temperature,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt},
        ],
    )
    return resp.choices[0].message.content


def _call_gemini(prompt: str, temperature: float) -> str:
    from google.genai import types
    client = _get_client()
    config = types.GenerateContentConfig(temperature=temperature, system_instruction=_SYSTEM)
    resp = client.models.generate_content(model=MODEL, contents=prompt, config=config)
    return resp.text


def generate_sql(prompt: str, temperature: float = 0.0) -> str:
    """Send a prompt to the configured provider; return cleaned SQL.

    Deterministic (temperature=0). Retries transient errors with backoff;
    fails fast on quota/rate-limit errors so the eval runner can stop cleanly.
    """
    call = _call_groq if PROVIDER == "groq" else _call_gemini

    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            return _strip_sql_fences(call(prompt, temperature))
        except Exception as e:  # noqa: BLE001
            last_err = e
            msg = str(e)
            if _is_quota_error(msg):
                raise RuntimeError(f"{PROVIDER} quota/rate limit hit: {msg.splitlines()[0]}")
            wait = 2 ** attempt
            print(f"  [llm] attempt {attempt + 1} failed ({e}); retrying in {wait}s")
            time.sleep(wait)

    raise RuntimeError(f"{PROVIDER} failed after {MAX_RETRIES} attempts: {last_err}")


if __name__ == "__main__":
    print(f"Provider: {PROVIDER} | Model: {MODEL}")
    print(generate_sql("Write SQL to select all rows from a table named foo."))