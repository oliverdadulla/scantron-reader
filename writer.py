import os
from typing import List, Optional

import pandas as pd

from config import OUTPUT_COLUMN_ORDER


def write_output(
    template_df: Optional[pd.DataFrame],
    filled_df: pd.DataFrame,
    sheet_names: List[str],
    path: str,
) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)

    known = [c for c in OUTPUT_COLUMN_ORDER if c in filled_df.columns]
    extras = [c for c in filled_df.columns if c not in OUTPUT_COLUMN_ORDER]
    filled_df = filled_df[known + extras]

    filled_df = filled_df.drop(columns=["Question No."], errors="ignore")

    data_sheet_name = sheet_names[1] if len(sheet_names) > 1 else sheet_names[0]

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        if template_df is not None:
            template_df.to_excel(writer, sheet_name=sheet_names[0], index=False)
        filled_df.to_excel(writer, sheet_name=data_sheet_name, index=False)
