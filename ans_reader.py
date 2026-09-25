import pandas as pd
import numpy as np
import re
import glob
import os
import sys
import io
import zipfile

from config import COMPLETED_SUFFIX, CORRECT_ANSWER_SUFFIX, EXAM_TEMPLATE_SUFFIX, TAGS_SUFFIX

# A Question File is usually just uploaded straight from an earlier stage's
# output (e.g. the "_completed" file from Prepare Exam Template) rather than
# renamed to bare "SUBJECTCODE-TYPE.xlsx" — strip those known suffixes so it
# still matches its answer folder.
_QUESTION_FILE_SUFFIXES = (COMPLETED_SUFFIX, EXAM_TEMPLATE_SUFFIX, TAGS_SUFFIX, CORRECT_ANSWER_SUFFIX)


def _question_file_key(path: str) -> str:
    key = '.'.join(os.path.basename(path).split(".")[:-1])
    for suffix in _QUESTION_FILE_SUFFIXES:
        if key.endswith(suffix):
            return key[:-len(suffix)]
    return key


_CHOICE_COL_RE = re.compile(r"^Choice_?(\d+)$")


def _question_choice_sets(questions_df_full):
    """Per item, which choice letters (A, B, C, D, E, ...) actually have a
    value in the question file — so a scanned answer using a letter the
    question doesn't define (e.g. E on a 4-choice item) can be flagged."""
    choice_cols = [
        (col, int(m.group(1)))
        for col in questions_df_full.columns
        if (m := _CHOICE_COL_RE.match(col))
    ]
    sets = []
    for _, row in questions_df_full.iterrows():
        letters = set()
        for col, n in choice_cols:
            val = row[col]
            if pd.notna(val) and str(val).strip():
                letters.add(chr(64 + n))
        sets.append(letters)
    return sets


def _find_column(df, name):
    """Case/whitespace-insensitive column lookup — returns the real column
    name as it appears in the file, or None if nothing matches."""
    target = name.strip().lower()
    for col in df.columns:
        if str(col).strip().lower() == target:
            return col
    return None


def nameCodeCheck(name, code): # blank_values = [None, "", "  ", np.nan]
    if (pd.isna(code) or ((isinstance(code, str) and code.strip() == ""))):
        return code
    return name

def isEmpty(value):
    if (pd.isna(value) or ((isinstance(value, str) and value.strip() == ""))):
        return True
    return False


def norm(s):
    return str(s).upper().replace('Ñ', 'N').replace('ñ', 'N')

def _patch_and_read_excel(filename):
    """Patch xlsx files where <v> holds a non-numeric value (e.g. 'A','B','C','D')
    but no t attribute, causing openpyxl to attempt int/float conversion and fail."""

    def _fix_worksheet(data):
        def _fix_cell(m):
            c_attrs = m.group(1)
            inner = m.group(2)
            v_match = re.search(rb'<v>([^<]*)</v>', inner)
            if not v_match:
                return m.group(0)
            v_val = v_match.group(1)
            try:
                float(v_val.decode('utf-8', errors='replace').strip())
                return m.group(0)          # already a valid number — leave alone
            except ValueError:
                pass
            # Non-numeric value: tag cell as t="str" so openpyxl returns it as-is
            if b't="' in c_attrs:
                c_attrs = re.sub(rb'\bt="[^"]*"', b't="str"', c_attrs)
            else:
                c_attrs = c_attrs + b' t="str"'
            return b'<c ' + c_attrs + b'>' + inner + b'</c>'

        return re.sub(rb'<c ([^>]*)>(.*?)</c>', _fix_cell, data, flags=re.DOTALL)

    buf = io.BytesIO()
    with zipfile.ZipFile(filename, 'r') as zin:
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename.startswith('xl/worksheets/'):
                    data = _fix_worksheet(data)
                zout.writestr(info, data)
    buf.seek(0)
    return pd.read_excel(buf, dtype=str, engine="openpyxl")


def run_processing(base_dir=None):
    if base_dir is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))

    students_path      = os.path.join(base_dir, 'Students', 'students.xlsx')
    questions_folder   = os.path.join(base_dir, 'Questions')
    answers_folder     = os.path.join(base_dir, 'Answers')
    output_folder      = os.path.join(base_dir, 'Converted')
    if_section = 1
    results = []

    try:
        regcodes = pd.read_excel(students_path)
    except Exception as e:
        return [{'folder': '', 'status': 'error', 'message': f'Cannot load students.xlsx: {e}', 'output': ''}]

    id_col = _find_column(regcodes, 'Student ID')
    last_col = _find_column(regcodes, 'LAST NAME')
    first_col = _find_column(regcodes, 'FIRST NAME')
    missing = [n for n, c in [('Student ID', id_col), ('LAST NAME', last_col), ('FIRST NAME', first_col)] if c is None]
    if missing:
        return [{
            'folder': '', 'status': 'error',
            'message': (
                f"students.xlsx is missing required column(s): {', '.join(missing)}. "
                f"Found columns: {', '.join(str(c) for c in regcodes.columns)}"
            ),
            'output': '',
        }]

    regcodes["_StudentID"] = regcodes[id_col].astype(str).str.strip()
    regcodes["_FirstName"] = regcodes[first_col].fillna('').astype(str).str.strip()
    regcodes["_LastName"] = regcodes[last_col].fillna('').astype(str).str.strip()
    regcodes["_DisplayName"] = regcodes["_LastName"] + ", " + regcodes["_FirstName"]
    regcodes["_LastNameNorm"] = regcodes["_LastName"].apply(norm)
    regcodes["_FirstNameNorm"] = regcodes["_FirstName"].apply(norm)

    folders = [f for f in os.listdir(answers_folder)
               if os.path.isdir(os.path.join(answers_folder, f)) and not f.startswith('.')]

    question_files = glob.glob(os.path.join(questions_folder, "*.xlsx"))
    questions_df = {}
    choice_sets_df = {}
    for qf in question_files:
        try:
            key = _question_file_key(qf)
            questions = pd.read_excel(qf, dtype=str)
            fmt = questions["Question"].to_list()
            fmt.insert(0, "studentno")
            fmt.append("")
            questions_df[key] = fmt
            choice_sets_df[key] = _question_choice_sets(questions)
        except Exception as e:
            exc_type, exc_obj, tb = sys.exc_info()
            results.append({'folder': qf, 'status': 'error',
                            'message': f'Error loading question file {os.path.basename(qf)}: {e}', 'output': ''})

    for folder_name in folders:
        try:
            questions_status = ''
            folder_path = os.path.join(answers_folder, folder_name)
            files = glob.glob(os.path.join(folder_path, "*.xlsx"))
            output = {}
            file_errors = []

            qkey = '-'.join(folder_name.split("-")[:-1]) if if_section == 1 else '-'.join(folder_name.split("-")[:2])
            item_choice_sets = choice_sets_df.get(qkey)

            for filename in files:
              try:
                studentname = '.'.join(os.path.basename(filename).split(".")[:-1])

                header_data = pd.read_excel(filename, dtype=str, nrows=8, engine="openpyxl")
                scantron_name = studentname
                scantron_code_raw = ''
                for _, row in header_data.iterrows():
                    label = str(row.iloc[0]).strip()
                    if label == 'NAME:':
                        for val in row.iloc[1:]:
                            if pd.notna(val) and str(val).strip():
                                scantron_name = str(val).strip(); break
                    elif label == 'CODE:':
                        for val in row.iloc[1:]:
                            if pd.notna(val) and str(val).strip():
                                scantron_code_raw = str(val).strip(); break

                digits = ''.join(filter(str.isdigit, scantron_code_raw))
                if len(digits) == 6:
                    studentcode = digits[:4] + '-' + digits[4:]
                elif len(digits) == 7:
                    studentcode = digits[:5] + '-' + digits[5:]
                elif '-' in scantron_code_raw:
                    studentcode = scantron_code_raw.strip()
                else:
                    studentcode = scantron_code_raw

                matched = regcodes[regcodes["_StudentID"] == studentcode] if studentcode else pd.DataFrame()

                if len(matched) == 0:
                    name_parts = [i.strip() for i in scantron_name.split(',')]
                    file_lastname = norm(name_parts[0])
                    file_firstname = norm(name_parts[1].split()[0]) if len(name_parts) > 1 and name_parts[1].strip() else ''
                    if file_firstname:
                        matched = regcodes[(regcodes["_LastNameNorm"] == file_lastname) & (regcodes["_FirstNameNorm"] == file_firstname)]
                    if len(matched) == 0 and file_lastname:
                        matched = regcodes[regcodes["_LastNameNorm"] == file_lastname]

                if len(matched) == 0 and '*' in scantron_name:
                    try:
                        raw_parts = [i.strip() for i in scantron_name.split(',')]
                        last_word = raw_parts[0].split()[0] if raw_parts[0].split() else ''
                        first_word = raw_parts[1].split()[0] if len(raw_parts) > 1 and raw_parts[1].split() else ''
                        last_pat = '^' + norm(last_word).replace('*', '.') + '$'
                        candidates = regcodes[regcodes["_LastNameNorm"].str.match(last_pat, na=False)]
                        if first_word and len(candidates) > 1:
                            first_pat = '^' + norm(first_word).replace('*', '.') + '$'
                            refined = candidates[candidates["_FirstNameNorm"].str.match(first_pat, na=False)]
                            if len(refined) >= 1:
                                candidates = refined
                        if len(candidates) == 1:
                            matched = candidates
                    except re.error:
                        pass

                if len(matched) >= 1:
                    studentcode = matched["_StudentID"].iloc[0]
                    display_name = matched["_DisplayName"].iloc[0]
                else:
                    raw_parts = [i.strip() for i in scantron_name.split(',')]
                    if len(raw_parts) >= 2 and raw_parts[1].strip():
                        clean_last = ' '.join(re.sub(r'\*', '', raw_parts[0]).split())
                        clean_first = re.sub(r'\*', '', raw_parts[1].strip().split()[0]).strip()
                        display_name = (clean_last + ', ' + clean_first).strip(', ')
                    else:
                        display_name = re.sub(r'\*', '', scantron_name).strip()

                try:
                    sheetdata = pd.read_excel(filename, dtype=str, engine="openpyxl")
                except (ValueError, TypeError):
                    sheetdata = _patch_and_read_excel(filename)
                while list(sheetdata.columns)[0] != 'Responses':
                    new_header = sheetdata.iloc[0].tolist()
                    sheetdata.columns = new_header
                    sheetdata = sheetdata.iloc[1:].reset_index(drop=True)

                scores = sheetdata.iloc[0:, 1].tolist()
                correct_answers = sheetdata.iloc[0:, 5].tolist()
                for i in range(len(scores)):
                    if isEmpty(scores[i]) and not isEmpty(correct_answers[i]):
                        ca = str(correct_answers[i])
                        correct_letter = ca[1] if len(ca) >= 2 else ca
                        scores[i] = 'D' if correct_letter != 'D' else 'A'
                    elif not isEmpty(scores[i]):
                        raw = str(scores[i]).strip()
                        if raw == '*':
                            # scanning software's mark for "no answer / multiple marks detected"
                            scores[i] = '* ⚠ (no answer / multiple marks)'
                        elif item_choice_sets and i < len(item_choice_sets):
                            letter = raw.upper()
                            valid = item_choice_sets[i]
                            if len(letter) == 1 and letter.isalpha() and valid and letter not in valid:
                                scores[i] = f'{letter} ⚠ (not a choice on this item)'

                scores.insert(0, studentcode)
                output[display_name] = scores
              except Exception as fe:
                file_errors.append(f'{os.path.basename(filename)}: {fe}')

            final_df = pd.DataFrame(output).T
            final_df = final_df.sort_index()
            max_colno = final_df.shape[1]
            final_df.columns = list(range(max_colno))

            if qkey in questions_df:
                questions_status = '— questions included'
                # A copy — questions_df[qkey] is shared across every answer
                # folder that matches this question file, so padding it in
                # place here would leak into the next folder's own row.
                header_row = list(questions_df[qkey])
                if len(header_row) <= max_colno:
                    while len(header_row) < max_colno:
                        header_row.append("")
                else:
                    while len(header_row) > final_df.shape[1]:
                        final_df[final_df.shape[1]] = np.nan
                    max_colno = final_df.shape[1]
            else:
                header_row = ["studentno"] + [""] * max(max_colno - 1, 0)

            # The stored file always keeps the Fullname column (final_df's
            # own index) — it's the "master" copy. Dropping it is a
            # download-time-only option now (see app.py's /download route),
            # so re-downloading later with the box unchecked still has it.
            width = max_colno + 1
            blank_row = [""] * width
            correct_row = [""] * width
            correct_row[1] = "CORRECT ANSWER"
            header_full_row = [""] + header_row

            answer_file = os.path.join(output_folder, folder_name + "_student_answer.xlsx")
            with pd.ExcelWriter(answer_file, engine="openpyxl") as writer:
                pd.DataFrame([blank_row, correct_row, header_full_row]).to_excel(
                    writer, index=False, header=False, sheet_name="Sheet1")
                final_df.to_excel(writer, index=True, header=False, sheet_name="Sheet1", startrow=3)

            # A second, minimal file — just the studentno column, one row
            # per student in the same order — for whoever only needs a
            # plain list of who took this exam, e.g. an attendance check.
            number_file = os.path.join(output_folder, folder_name + "_student_number.xlsx")
            final_df.iloc[:, [0]].reset_index(drop=True).rename(columns={0: "studentno"}).to_excel(
                number_file, index=False)

            msg = f'{folder_name} {questions_status}'
            if file_errors:
                msg += f' | skipped {len(file_errors)} file(s): ' + '; '.join(file_errors)
            results.append({'folder': folder_name, 'status': 'success',
                            'message': msg,
                            'output': folder_name + '_student_answer.xlsx'})

        except Exception as e:
            exc_type, exc_obj, tb = sys.exc_info()
            results.append({'folder': folder_name, 'status': 'error',
                            'message': f'{folder_name}: {e} (line {tb.tb_lineno})', 'output': ''})

    return results


if __name__ == '__main__':
    for r in run_processing():
        print(r['message'])


