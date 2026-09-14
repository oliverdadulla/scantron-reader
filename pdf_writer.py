from __future__ import annotations
from pathlib import Path
import re
import pandas as pd
from pdf_config import COLUMN_ORDER, BLANK_COLUMNS


def build_dataframe(questions: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(questions)
    for col in BLANK_COLUMNS:
        df[col] = None

    # Find extra choice columns (Choice_5, Choice_6, …) and add blank iscorrect siblings
    extra_choice_pairs: list[tuple[int, str, str]] = []
    for col in list(df.columns):
        m = re.match(r"^Choice_(\d+)$", col)
        if m:
            n = int(m.group(1))
            if n >= 5:
                iscorrect_col = f"iscorrect{n} (1/0)"
                if iscorrect_col not in df.columns:
                    df[iscorrect_col] = None
                extra_choice_pairs.append((n, col, iscorrect_col))

    extra_choice_pairs.sort()
    extra_choice_flat = [c for _, ch, ic in extra_choice_pairs for c in (ch, ic)]

    existing_ordered = [c for c in COLUMN_ORDER if c in df.columns]
    remaining = [c for c in df.columns if c not in COLUMN_ORDER and c not in extra_choice_flat]
    return df[existing_ordered + extra_choice_flat + remaining]


def write_dataframe(df: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Questions")
        ws = writer.sheets["Questions"]
        for col_cells in ws.columns:
            max_len = max(
                (len(str(cell.value)) for cell in col_cells if cell.value is not None),
                default=10,
            )
            ws.column_dimensions[col_cells[0].column_letter].width = min(max_len + 4, 60)


def save_to_excel(questions: list[dict], pdf_path: Path, output_dir: Path) -> Path:
    output_path = output_dir / (pdf_path.stem + ".xlsx")
    df = build_dataframe(questions)
    write_dataframe(df, output_path)
    return output_path
