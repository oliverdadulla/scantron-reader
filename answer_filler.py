import re

import pandas as pd

from expander import expand_item_nos

ANSWER_TO_IDX = {"A": 0, "B": 1, "C": 2, "D": 3}


def detect_iscorrect_cols(df: pd.DataFrame) -> list:
    """
    Find iscorrect1-4 columns regardless of exact naming.
    Matches any column containing 'iscorrect' + a digit, e.g.:
      'iscorrect1 (1/0)', 'iscorrect1', 'IsCorrect1', 'iscorrect_1'
    Returns a list of 4 column names sorted by their digit [1, 2, 3, 4].
    """
    found = {}
    for col in df.columns:
        m = re.search(r'iscorrect\D*(\d)', col, re.IGNORECASE)
        if m:
            num = int(m.group(1))
            found[num] = col

    if not found:
        print("   ⚠️  No iscorrect columns found in the exam template — skipping answer fill.")
        return []

    missing = [i for i in range(1, 5) if i not in found]
    if missing:
        print(f"   ⚠️  Could not find iscorrect columns for positions: {missing}")

    return [found[i] for i in sorted(found.keys())]


def build_answer_lookup(answers_df: pd.DataFrame, answer_col: str) -> dict:
    lookup = {}
    for _, row in answers_df.iterrows():
        item_nos_raw = str(row["ItemNos"]).strip().lstrip("Qq")
        answer = str(row[answer_col]).strip().upper()
        if answer not in ANSWER_TO_IDX:
            print(f"  ⚠️  Warning: unrecognized answer value '{answer}', skipping.")
            continue
        for qno in expand_item_nos(item_nos_raw):
            lookup[qno] = answer
    return lookup


def apply_answers(main_df: pd.DataFrame, lookup: dict) -> pd.DataFrame:
    iscorrect_cols = detect_iscorrect_cols(main_df)
    if not iscorrect_cols:
        return main_df

    # Zero out all iscorrect columns
    for col in iscorrect_cols:
        main_df[col] = 0

    unmatched = []
    for idx, row in main_df.iterrows():
        raw_qno = str(row["Question No."]).strip().lstrip("Qq")
        try:
            qno = int(raw_qno)
        except (ValueError, TypeError):
            continue

        if qno in lookup:
            answer_idx = ANSWER_TO_IDX[lookup[qno]]
            for col in iscorrect_cols:
                main_df.at[idx, col] = 0
            if answer_idx < len(iscorrect_cols):
                main_df.at[idx, iscorrect_cols[answer_idx]] = 1
        else:
            unmatched.append(qno)

    if unmatched:
        print(f"   ⚠️  No answer found for Question No.: {sorted(unmatched)}")
    else:
        detected = ", ".join(iscorrect_cols)
        print(f"   ✅ Answers applied → columns: {detected}")
        print(f"      (A→1,0,0,0 / B→0,1,0,0 / C→0,0,1,0 / D→0,0,0,1)")

    return main_df
