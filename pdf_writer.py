from __future__ import annotations
from pathlib import Path
import pandas as pd
from pdf_config import COLUMN_ORDER, BLANK_COLUMNS


def save_to_excel(questions: list[dict], pdf_path: Path, output_dir: Path) -> Path:
    output_path = output_dir / (pdf_path.stem + ".xlsx")
    df = pd.DataFrame(questions)
    for col in BLANK_COLUMNS:
        df[col] = None
    existing_ordered = [c for c in COLUMN_ORDER if c in df.columns]
    extra_cols = [c for c in df.columns if c not in COLUMN_ORDER]
    df = df[existing_ordered + extra_cols]
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
    return output_path
