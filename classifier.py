import re
from typing import Optional

# Ordered most-specific first so a longer suffix wins before a shorter one.
_PATTERNS = [
    (re.compile(r"-D\d+-CO\d+(\.\d+)*[a-zA-Z]*$"),       "Competency"),
    (re.compile(r"-D\d+-ILO\d+(\.\d+)*[a-zA-Z]*$"),      "Content Standards"),
    # Letters case-insensitive: most Thinking-Skill codes are all-caps (RE, AN,
    # EV...) but a couple of the combined categories are generated mixed-case
    # (e.g. "Cr" for Creating, "Ave" for Applying/Analyzing) — see excelreader.py.
    (re.compile(r"-TS-[A-Za-z]+(\.\d+)*$"),                "THINKING SKILLS"),
    (re.compile(r"-D\d+(\.\d+)*$"),                       "TOPIC"),
]


def classify_code(code: str) -> Optional[str]:
    for pattern, column in _PATTERNS:
        if pattern.search(code):
            return column
    print(f"  ⚠️  Warning: unrecognized code pattern '{code}', skipping.")
    return None
