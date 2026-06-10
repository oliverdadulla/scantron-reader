from __future__ import annotations
import json
import os
import re
from openai import OpenAI
from pdf_config import GROQ_MODEL, GROQ_BASE_URL

SYSTEM_PROMPT = """You are a strict exam question validator.

You will receive a JSON list of items parsed from a PDF exam paper.
Each item has: "no" (number), "question" (text), "has_choices" (true/false).

Your job: return ONLY the "no" values of items that are genuine multiple choice exam questions.

A genuine MCQ has:
- A clear question stem (a full sentence or paragraph that asks something)
- Answer choices A, B, C, D (has_choices: true)

Exclude items that are:
- Table rows or comparison table cells (e.g. "Dyspnea: Severe", "Appearance: Blue bloater")
- Page numbers (e.g. "Page 1 of 4", "- 2 -")
- School or institution names
- Exam title or subject headers
- Instruction paragraphs
- Section labels
- Any item where the question text is a short label or phrase, not a full question sentence

Respond with ONLY a valid JSON object in this exact format:
{"valid": [1, 2, 3, 5]}
"""


def filter_questions(questions: list[dict], api_key: str = "") -> list[dict]:
    if not api_key:
        api_key = __import__("os").environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("GROQ_API_KEY not provided. Enter it in the UI or set the env var.")

    client = OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)

    items = [
        {
            "no": q["Question No."],
            "question": q["Question"][:300],
            "has_choices": bool(
                q["Choice1"] or q["Choice2"] or q["Choice_3"] or q["Choice_4"]
            ),
        }
        for q in questions
    ]

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Validate these parsed exam items and return the "
                    "question numbers that are real MCQs:\n\n"
                    + json.dumps(items, indent=2)
                ),
            },
        ],
        temperature=0,
    )

    content = response.choices[0].message.content.strip()
    valid_nos = _parse_valid_nos(content)

    filtered = [q for q in questions if q["Question No."] in valid_nos]
    removed = len(questions) - len(filtered)

    if removed > 0:
        removed_nos = [q["Question No."] for q in questions if q["Question No."] not in valid_nos]
        print(f"  AI removed {removed} non-question item(s): {removed_nos}")

    return filtered


def _parse_valid_nos(content: str) -> set[int]:
    try:
        data = json.loads(content)
        if isinstance(data, dict):
            for v in data.values():
                if isinstance(v, list):
                    return set(int(x) for x in v)
        if isinstance(data, list):
            return set(int(x) for x in data)
    except (json.JSONDecodeError, ValueError):
        pass

    match = re.search(r"\[[\d,\s]+\]", content)
    if match:
        try:
            return set(int(x) for x in json.loads(match.group()))
        except (json.JSONDecodeError, ValueError):
            pass

    raise ValueError(
        f"Could not parse AI response as a list of question numbers.\n"
        f"Raw response: {content}"
    )
