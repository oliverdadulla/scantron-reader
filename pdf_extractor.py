from __future__ import annotations
from pathlib import Path
import re
import pdfplumber
from pdf_config import TWO_COLUMN_CHAR_THRESHOLD


def extract_text(pdf_path: Path) -> str:
    all_text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = _extract_page_text(page)
            if page_text:
                all_text_parts.append(page_text)
    return "\n".join(all_text_parts)


def _extract_page_text(page) -> str:
    width = page.width
    left_crop  = page.crop((0,         0, width / 2, page.height))
    right_crop = page.crop((width / 2, 0, width,     page.height))
    left_text  = left_crop.extract_text()  or ""
    right_text = right_crop.extract_text() or ""
    left_has_content  = len(left_text.strip())  > TWO_COLUMN_CHAR_THRESHOLD
    right_has_content = len(right_text.strip()) > TWO_COLUMN_CHAR_THRESHOLD
    if not (left_has_content and right_has_content):
        return (page.extract_text(layout=True) or page.extract_text() or "").strip()
    if _has_question_numbers_in_right_half(page, width):
        left_layout  = left_crop.extract_text(layout=True)  or left_text
        right_layout = right_crop.extract_text(layout=True) or right_text
        return (left_layout.rstrip("\n") + "\n" + right_layout).strip()
    return _extract_text_spatial(page)


def _has_question_numbers_in_right_half(page, width: float) -> bool:
    words = page.extract_words(x_tolerance=3, y_tolerance=3)
    count = sum(
        1 for w in words
        if w["x0"] >= width / 2 and re.match(r"^\d{1,3}\.$", w["text"])
    )
    return count >= 3


def _extract_text_spatial(page) -> str:
    words = page.extract_words(x_tolerance=5, y_tolerance=5)
    if not words:
        return ""
    lines: dict[int, list] = {}
    for word in words:
        y_key = round(word["top"] / 4) * 4
        lines.setdefault(y_key, []).append(word)
    result = []
    for y in sorted(lines):
        line_words = sorted(lines[y], key=lambda w: w["x0"])
        result.append(" ".join(w["text"] for w in line_words))
    return "\n".join(result)
