from typing import Tuple

import pandas as pd

from classifier import classify_code
from config import FILLABLE_COLUMNS
from expander import expand_item_nos


def build_lookup(mapping_df: pd.DataFrame) -> dict:
    lookup: dict = {}

    for _, row in mapping_df.iterrows():
        code = str(row["code"]).strip()
        item_nos_raw = row["ItemNos"]

        column = classify_code(code)
        if column is None:
            continue

        question_nos = expand_item_nos(str(item_nos_raw))
        for qno in question_nos:
            if qno not in lookup:
                lookup[qno] = {}
            lookup[qno][column] = code
            if column == "TOPIC":
                lookup[qno]["DOMAIN"] = code

    return lookup


def apply_lookup(main_df: pd.DataFrame, lookup: dict) -> Tuple[pd.DataFrame, list]:
    for col in FILLABLE_COLUMNS:
        if col not in main_df.columns:
            main_df[col] = None
        else:
            main_df[col] = main_df[col].astype(object)

    unmatched: list = []

    for idx, row in main_df.iterrows():
        raw_qno = str(row["Question No."]).strip()
        # Strip leading Q/q prefix (e.g. "Q001" → "1")
        normalized = raw_qno.lstrip("Qq")
        try:
            qno = int(normalized)
        except (ValueError, TypeError):
            print(
                f"  ⚠️  Warning: could not convert Question No. '{raw_qno}' "
                f"to int at row index {idx}, skipping."
            )
            continue

        if qno in lookup:
            for col, value in lookup[qno].items():
                main_df.at[idx, col] = value
        else:
            unmatched.append(qno)

    main_df["SUBTOPIC"] = None

    return main_df, unmatched
