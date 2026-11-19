"""AI-assisted re-parsing for questions the regex parser got structurally
confused by — e.g. a question whose own text contains a numbered list
("1 House Bill No. ... 2 Senate Bill No. ...") or a person's middle initial
("Neptali A. Gonzales"), which reads exactly like a choice marker to a
pattern match. parser.py calls refine_block() only on blocks it has already
flagged as suspicious (see is_suspicious there) — most questions never reach
this at all, so cost/latency stays proportional to how much a given PDF
actually confuses the regex path, not its total question count.

Disabled by default: with no GROQ_API_KEY set, refine_block() returns None
immediately and the caller keeps the regex result it already had. Nothing
else in the app changes behavior until that key is set.
"""
from __future__ import annotations
import json
import os

from .config import GROQ_MODEL, GROQ_BASE_URL

SYSTEM_PROMPT = """You are fixing a parsing mistake in an exam-questionnaire extractor.

You will receive the raw text of ONE numbered multiple-choice question, exactly as it \
was extracted from a PDF (whitespace/line breaks may be irregular). A simple pattern \
match already tried to split it into a question stem and lettered answer choices, and \
got confused by something inside the question's own wording that merely looks like a \
choice marker — for example:
  - a numbered list the question itself asks about ("1 House Bill No. ... 2 Senate \
    Bill No. ...")
  - a person's middle initial ("Neptali A. Gonzales", "Ramon V. Mitra")
  - an abbreviation or citation

None of those are answer choices. The real choices are the short lettered options at \
the very end of the block (A, B, C, D, and so on) — usually introduced right after a \
phrase like "which of the following", "which combination is correct", or similar, near \
a question mark.

Return ONLY a JSON object, no other text, in this exact shape:
{"question": "<the full question stem, with its own numbered list or names kept \
intact>", "choices": {"A": "...", "B": "...", "C": "...", "D": "..."}}

Include every real lettered choice you find (there may be more or fewer than 4). If you \
genuinely cannot find a real choice list, return an empty object for "choices".
"""


def refine_block(raw_block: str) -> dict | None:
    """Returns {"question": str, "choices": {letter: text}} or None (meaning:
    keep whatever the regex parser already produced) if there's no API key
    configured, the API call fails, or the response doesn't parse."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None

    try:
        from openai import OpenAI
    except ImportError:
        print("  ⚠️  GROQ_API_KEY is set but the 'openai' package isn't installed — skipping AI re-parse.")
        return None

    try:
        client = OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": raw_block},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        data = json.loads(response.choices[0].message.content)
        if isinstance(data, dict) and "question" in data and isinstance(data.get("choices"), dict):
            return data
    except Exception as exc:
        print(f"  ⚠️  AI re-parse failed, keeping the regex result instead: {exc}")
    return None
