from __future__ import annotations
from pathlib import Path
import re
import pdfplumber
from pdf_config import TWO_COLUMN_CHAR_THRESHOLD


def extract_text(pdf_path: Path, mode: str = "auto") -> str:
    """mode: 'auto' (per-page detection), 'single', or 'double' (forced)."""
    all_text_parts = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            page_text = _extract_page_text(page, mode)
            if page_text:
                all_text_parts.append(page_text)
    return "\n".join(all_text_parts)


def detect_layout(pdf_path: Path) -> dict:
    """Per-page auto-detected layout, for display/override in the UI."""
    kinds = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            kinds.append(_page_layout_kind(page))
    unique = set(kinds)
    overall = "single"
    if len(unique) == 1:
        overall = kinds[0]
    elif len(unique) > 1:
        overall = "mixed"
    return {"pages": kinds, "overall": overall}


def _halves(page):
    width = page.width
    return page.crop((0, 0, width / 2, page.height)), page.crop((width / 2, 0, width, page.height))


def _page_layout_kind(page) -> str:
    left_crop, right_crop = _halves(page)
    left_text  = left_crop.extract_text()  or ""
    right_text = right_crop.extract_text() or ""
    left_has_content  = len(left_text.strip())  > TWO_COLUMN_CHAR_THRESHOLD
    right_has_content = len(right_text.strip()) > TWO_COLUMN_CHAR_THRESHOLD
    if left_has_content and right_has_content and _has_question_numbers_in_right_half(page, page.width):
        return "double"
    return "single"


def _extract_single(page) -> str:
    return (page.extract_text(layout=True) or page.extract_text() or "").strip()


def _extract_double(page) -> str:
    left_crop, right_crop = _halves(page)
    left_layout  = left_crop.extract_text(layout=True)  or left_crop.extract_text()  or ""
    right_layout = right_crop.extract_text(layout=True) or right_crop.extract_text() or ""
    return (left_layout.rstrip("\n") + "\n" + right_layout).strip()


def _extract_page_text(page, mode: str = "auto") -> str:
    if mode == "single":
        return _extract_single(page)
    if mode == "double":
        return _extract_double(page)

    width = page.width
    left_crop, right_crop = _halves(page)
    left_text  = left_crop.extract_text()  or ""
    right_text = right_crop.extract_text() or ""
    left_has_content  = len(left_text.strip())  > TWO_COLUMN_CHAR_THRESHOLD
    right_has_content = len(right_text.strip()) > TWO_COLUMN_CHAR_THRESHOLD
    if not (left_has_content and right_has_content):
        return _extract_single(page)
    if _has_question_numbers_in_right_half(page, width):
        return _extract_double(page)
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
