from typing import Optional, Tuple

import pandas as pd

from config import DATA_SHEET_INDEX, TEMPLATE_SHEET_INDEX


def load_main(path: str) -> Tuple[Optional[pd.DataFrame], pd.DataFrame, list]:
    """
    Returns (template_df, data_df, sheet_names).

    Accepts files with 1 OR 2+ sheets:
      - 1 sheet  → that sheet is the data; template_df is None.
      - 2+ sheets → sheet 0 is the template, sheet 1 is the data.
    """
    try:
        xl = pd.ExcelFile(path, engine="openpyxl")
    except FileNotFoundError:
        raise FileNotFoundError(f"Main file not found: '{path}'")

    sheet_names = xl.sheet_names

    if len(sheet_names) == 1:
        template_df = None
        data_df = xl.parse(sheet_name=0)
    else:
        template_df = xl.parse(sheet_name=TEMPLATE_SHEET_INDEX)
        data_df = xl.parse(sheet_name=DATA_SHEET_INDEX)

    data_df = _autofill_question_nos(data_df, sheet_names, path)

    return template_df, data_df, sheet_names


def _autofill_question_nos(data_df: pd.DataFrame, sheet_names: list, path: str) -> pd.DataFrame:
    n = len(data_df)
    q_labels = [f"Q{str(i + 1).zfill(3)}" for i in range(n)]

    if "Question No." not in data_df.columns:
        # Column missing entirely — insert it as the first column
        data_df.insert(0, "Question No.", q_labels)
        print(f"   ℹ️  'Question No.' column not found — auto-filled Q001 to Q{str(n).zfill(3)}")
        return data_df

    col = data_df["Question No."]
    is_blank = col.isna() | (col.astype(str).str.strip() == "") | (col.astype(str).str.strip() == "nan")

    if is_blank.all():
        # Column exists but every cell is empty — fill all rows
        data_df["Question No."] = q_labels
        print(f"   ℹ️  'Question No.' was empty — auto-filled Q001 to Q{str(n).zfill(3)}")
    elif is_blank.any():
        # Partially filled — fill only the blank cells
        data_df.loc[is_blank, "Question No."] = [
            q_labels[i] for i in data_df.index[is_blank]
        ]
        print(f"   ℹ️  {is_blank.sum()} blank 'Question No.' cell(s) auto-filled")

    return data_df


def load_answers(path: str):
    """
    Reads a correct answer file where:
      Column 1 → ItemNos  (question numbers)
      Column 2 → Key Answer (A, B, C, or D)

    Column headers are ignored — position is what matters.
    """
    try:
        df = pd.read_excel(path, engine="openpyxl")
    except FileNotFoundError:
        raise FileNotFoundError(f"Answers file not found: '{path}'")

    if df.shape[1] < 2:
        raise ValueError(
            f"Correct answer file '{path}' must have at least 2 columns. "
            f"Column 1 = ItemNos, Column 2 = Key Answer."
        )

    normalized = df.iloc[:, [0, 1]].copy()
    normalized.columns = ["ItemNos", "Answer"]
    normalized = normalized.dropna(subset=["ItemNos", "Answer"])

    return normalized, "Answer"


def load_mapping(path: str) -> pd.DataFrame:
    try:
        df = pd.read_excel(path, engine="openpyxl")
    except FileNotFoundError:
        raise FileNotFoundError(f"Mapping file not found: '{path}'")

    for col in ("code", "ItemNos"):
        if col not in df.columns:
            raise ValueError(
                f"'{col}' column is missing from '{path}'. "
                f"Found columns: {list(df.columns)}"
            )
    return df
