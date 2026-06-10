import re
from typing import Optional

# Ordered most-specific first so a longer suffix wins before a shorter one.
_PATTERNS = [
    (re.compile(r"-D\d+-CO\d+[a-zA-Z]*$"),   "Competency"),
    (re.compile(r"-D\d+-ILO\d+[a-zA-Z]*$"),  "Content Standards"),
    (re.compile(r"-TS-[A-Z]+$"),    "THINKING SKILLS"),
    (re.compile(r"-D\d+$"),         "TOPIC"),
]


def classify_code(code: str) -> Optional[str]:
    for pattern, column in _PATTERNS:
        if pattern.search(code):
            return column
    print(f"  ⚠️  Warning: unrecognized code pattern '{code}', skipping.")
    return None
