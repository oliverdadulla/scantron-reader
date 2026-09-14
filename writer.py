import os
from typing import List, Optional

import pandas as pd

from config import OUTPUT_COLUMN_ORDER


def _whole_numbers_as_int(value):
    """1.0 -> 1, 1.5 stays 1.5, non-numeric values pass through untouched."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return value
    return int(f) if f.is_integer() else f


def prepare_filled_df(filled_df: pd.DataFrame) -> pd.DataFrame:
    filled_df = filled_df.copy()

    if "Rate/Points" not in filled_df.columns:
        filled_df["Rate/Points"] = 1
    else:
        rate = filled_df["Rate/Points"]
        is_blank = rate.isna() | rate.astype(str).str.strip().str.lower().isin(["", "nan", "none"])
        filled_df.loc[is_blank, "Rate/Points"] = 1
    cleaned = [_whole_numbers_as_int(v) for v in filled_df["Rate/Points"]]
    filled_df["Rate/Points"] = pd.Series(cleaned, index=filled_df.index, dtype=object)

    known = [c for c in OUTPUT_COLUMN_ORDER if c in filled_df.columns]
    extras = [c for c in filled_df.columns if c not in OUTPUT_COLUMN_ORDER]
    filled_df = filled_df[known + extras]
    return filled_df.drop(columns=["Question No."], errors="ignore")


def write_output(
    template_df: Optional[pd.DataFrame],
    filled_df: pd.DataFrame,
    sheet_names: List[str],
    path: str,
) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)

    filled_df = prepare_filled_df(filled_df)
    data_sheet_name = sheet_names[1] if len(sheet_names) > 1 else sheet_names[0]

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        if template_df is not None:
            template_df.to_excel(writer, sheet_name=sheet_names[0], index=False)
        filled_df.to_excel(writer, sheet_name=data_sheet_name, index=False)
