"""
llm.py  --  The ONLY file that knows we're using Gemini.

Everything else in the project calls generate_sql(prompt) and gets back a
SQL string. If we ever switch to OpenAI/Claude, we only change THIS file.

Why this matters:
  - One place to swap providers (good engineering, good interview answer).
  - Free-tier Gemini has tight rate limits, so retry/backoff lives here
    instead of being scattered across the codebase.
"""

import os
import re
import time

from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()  # reads GEMINI_API_KEY from a .env file in the project root

# --- config --------------------------------------------------------------
# Flash-Lite for cheap dev iteration (15 RPM, 1000/day free).
# Switch to "gemini-2.5-flash" for your final, higher-quality eval run.
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
MAX_RETRIES = 4
# -------------------------------------------------------------------------

_client = None


def _get_client():
    """Create the Gemini client once and reuse it."""
    global _client
    if _client is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY not set. Put it in a .env file:\n"
                "  GEMINI_API_KEY=your_key_here"
            )
        _client = genai.Client(api_key=api_key)
    return _client


def _strip_sql_fences(text: str) -> str:
    """
    LLMs love wrapping SQL in ```sql ... ``` markdown fences, and sometimes
    add a 'Here is your query:' preamble. We strip all that so we get raw,
    runnable SQL.
    """
    text = text.strip()
    # Remove ```sql ... ``` or ``` ... ``` fences
    fence = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence:
        text = fence.group(1)
    return text.strip().rstrip(";").strip()


def generate_sql(prompt: str, temperature: float = 0.0) -> str:
    """
    Send a prompt to Gemini and return cleaned SQL.

    temperature=0.0 -> deterministic. We want the SAME SQL for the same
    question every time; no creative variation when generating queries.

    Retries with exponential backoff on rate-limit / transient errors,
    because the free tier WILL throttle us during eval runs.
    """
    client = _get_client()
    config = types.GenerateContentConfig(
        temperature=temperature,
        system_instruction=(
            "You are an expert data analyst who writes correct, efficient "
            "SQLite SQL. Return ONLY the SQL query, no explanation, no "
            "markdown fences."
        ),
    )

    last_err = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=config,
            )
            return _strip_sql_fences(resp.text)
        except Exception as e:  # noqa: BLE001
            last_err = e
            # Quota errors (429 / RESOURCE_EXHAUSTED) are NOT transient within
            # this run -- retrying just wastes attempts and time. Fail fast so
            # the caller (eval runner) can stop cleanly and resume later.
            msg = str(e)
            if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                raise RuntimeError(f"Gemini quota exhausted: {msg.splitlines()[0]}")
            wait = 2 ** attempt  # 1s, 2s, 4s, 8s
            print(f"  [llm] attempt {attempt + 1} failed ({e}); retrying in {wait}s")
            time.sleep(wait)

    raise RuntimeError(f"Gemini failed after {MAX_RETRIES} attempts: {last_err}")


if __name__ == "__main__":
    # Smoke test: does the wrapper talk to Gemini at all?
    print("Model:", MODEL)
    sql = generate_sql("Write SQL to select all rows from a table named foo.")
    print("Got SQL:\n", sql)