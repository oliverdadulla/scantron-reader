from __future__ import annotations
import re
from typing import Optional

QUESTION_START_RE = re.compile(r"(?:^|\n)[ \t]*(\d+)\.[ \t]", re.MULTILINE)
QUESTION_NUMBER_RE = re.compile(r"^\s*(\d+)\.\s*(.+)", re.DOTALL)
CHOICE_RE = re.compile(
    r"\b([A-Da-d])[.)]\s*(.*?)(?=\s+[A-Da-d][.)]\s|\Z)",
    re.DOTALL,
)
FIRST_CHOICE_RE = re.compile(r"\b[Aa][.)]\s", re.IGNORECASE)
HEADER_STRIP_RE = re.compile(r"^.*?(?=\n[ \t]*1\.[ \t])", re.DOTALL)

# ── Structural junk detectors (no hardcoded vocabulary) ──────────────────────

# Line starts with 2+ underscores  →  form/signature blank  (e.g. "____Date: ____")
_STARTS_WITH_BLANK = re.compile(r"^\s*_{2,}")

# Colon followed by 2+ underscores  →  labeled form field  (e.g. "Name: ____")
_COLON_BLANK = re.compile(r":\s*_{2,}")

# Classic page-number formats:  "- 3 -"  or  "– 3 –"
_PAGE_DASH = re.compile(r"^[-–]\s*\d+\s*[-–]$")

# Standalone 1-3 digit number on its own line  (page numbers like "2", "12")
_LONE_NUMBER = re.compile(r"^\d{1,3}\s*$")

# 3 or more "word:" label patterns on a single line  →  metadata/form row
# e.g. "Prepared by: ___ Date: ___ Approved: ___"
_LABEL_COLON = re.compile(r"\b\w{1,30}\s*:")

# Short line (<80 chars) with "by:" attribution pattern  →  signature line
# e.g. "Prepared by: Juan", "Checked by: Maria", "Verified by: Dr. Cruz"
_ATTRIBUTION_BY = re.compile(r"\bby\s*:\s*\S", re.IGNORECASE)

# 3+ consecutive underscores AND at least one digit on the same line
# →  form fragment  (e.g. "FORM 2018 007 No. of Copies Page ___ of 3")
# Fill-in-blank questions have underscores but rarely have digits on the same line.
_BLANK_WITH_DIGIT = re.compile(r"(?=.*_{3,})(?=.*\d)")

# Colon followed by an optional underscore then a date-format value
# →  form date field  (e.g. "Date: _2/7/2025_",  "Date: 3-30-2026")
_COLON_DATE = re.compile(r":\s*_?\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}")


def parse_questions(full_text: str) -> list[dict]:
    text = _strip_header(full_text)
    blocks = _split_into_blocks(text)
    return [q for b in blocks if (q := _parse_block(b)) is not None]


def _strip_header(text: str) -> str:
    m = HEADER_STRIP_RE.match(text)
    return text[m.end():] if m else text


def _split_into_blocks(text: str) -> list[str]:
    matches = list(QUESTION_START_RE.finditer(text))
    blocks = []
    for i, m in enumerate(matches):
        start = m.start(1)
        end = matches[i + 1].start(1) if i + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        if block:
            blocks.append(block)
    return blocks


def _is_junk_line(line: str) -> bool:
    """Return True if this line is structural metadata, not question content.

    Detects junk purely by structure — no vocabulary assumptions:
      • Lines starting with underscores        (signature/form blanks)
      • Lines with "word: ____"                (labeled blank fields)
      • Classic page-number formats  (- N -)
      • Standalone 1–3 digit numbers           (bare page numbers)
      • 3+ "word:" label patterns on one line  (metadata rows)
      • Short "...by: Name" attribution lines  (signature lines)
      • 3+ underscores AND digit on same line  (form/footer fragments)
    """
    s = line.strip()
    if not s:
        return False
    if _STARTS_WITH_BLANK.match(s):
        return True
    if _COLON_BLANK.search(s):
        return True
    if _PAGE_DASH.match(s):
        return True
    if _LONE_NUMBER.match(s):
        return True
    if len(_LABEL_COLON.findall(s)) >= 3:
        return True
    # Short attribution line: "Prepared by: Name", "Checked by: Name"
    if len(s) < 80 and _ATTRIBUTION_BY.search(s):
        return True
    # Form/footer fragment: underscores mixed with digits
    if _BLANK_WITH_DIGIT.match(s):
        return True
    # Colon + date value: "Date: _2/7/2025_", "Date: 3-30-2026"
    if _COLON_DATE.search(s):
        return True
    return False


def _clean_text(text: str) -> str:
    """Remove junk lines then collapse whitespace."""
    lines = [ln for ln in text.splitlines() if not _is_junk_line(ln)]
    return " ".join(" ".join(lines).split()).strip()


def _parse_block(block: str) -> Optional[dict]:
    block = block.strip()
    if not block:
        return None

    m = QUESTION_NUMBER_RE.match(block)
    if not m:
        return None

    question_no = int(m.group(1))
    remainder = m.group(2).strip()

    fc = FIRST_CHOICE_RE.search(remainder)
    if fc:
        question_text = _clean_text(remainder[: fc.start()])
        choices_text = remainder[fc.start():]
    else:
        question_text = _clean_text(remainder)
        choices_text = ""

    choices = _extract_choices(choices_text)

    return {
        "Question No.": question_no,
        "Question": question_text,
        "Choice1": choices.get("A", ""),
        "Choice2": choices.get("B", ""),
        "Choice_3": choices.get("C", ""),
        "Choice_4": choices.get("D", ""),
    }


def _extract_choices(choices_text: str) -> dict:
    choices = {"A": "", "B": "", "C": "", "D": ""}
    if not choices_text.strip():
        return choices
    for label, text in CHOICE_RE.findall(choices_text):
        label = label.upper()
        if label in choices:
            choices[label] = _clean_text(text)
    return choices
