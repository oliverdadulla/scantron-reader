import pandas as pd
import numpy as np
import re
import glob
import os
import sys

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

MA_PREFIXES       = {'MA.', 'MA', 'STO.', 'STA.', 'STO', 'STA'}
TWO_PARTICLES     = {'DE LA', 'DE LOS', 'DE LAS'}
ONE_PARTICLES     = {'DE', 'DEL', 'DOS', 'VDA.', 'DELA', 'DELOS', 'DELAS', 'SAN', 'SANTA', 'SANTO'}
GEN_SUFFIXES      = {'JR.', 'JR', 'SR.', 'SR', 'II', 'III', 'IV', 'V', 'VI'}

def extract_name_parts(fullname):
    words = str(fullname).strip().split()
    if not words:
        return '', ''
    # Strip trailing generation suffixes (JR., SR., III, etc.) and stray commas
    while words and words[-1].upper().rstrip(',') in GEN_SUFFIXES:
        words = words[:-1]
    words = [w.rstrip(',') for w in words]
    words = [w for w in words if w]
    if not words:
        return '', ''
    # First name: keep "MA." / "STO." prefix together with the next word
    if len(words) >= 2 and words[0].upper() in MA_PREFIXES:
        first = (words[0] + ' ' + words[1]).upper()
        rest = words[2:]
    else:
        first = words[0].upper()
        rest = words[1:]
    if not rest:
        return first, ''
    # Last name: scan backward absorbing surname particles.
    # Two-word particles (DE LA, DE LOS) are detected by checking rest[i-1]+rest[i].
    i = len(rest) - 1
    last_parts = [rest[i].upper()]
    i -= 1
    while i >= 0:
        w = rest[i].upper()
        if i > 0 and (rest[i-1].upper() + ' ' + w) in TWO_PARTICLES:
            last_parts.insert(0, w)
            last_parts.insert(0, rest[i-1].upper())
            i -= 2
        elif w in ONE_PARTICLES:
            last_parts.insert(0, w)
            i -= 1
        else:
            break
    return first, ' '.join(last_parts)

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

    regcodes[["_FirstName", "_LastName"]] = regcodes["Fullname"].apply(
        lambda x: pd.Series(extract_name_parts(x))
    )
    regcodes["_DisplayName"] = regcodes["_LastName"] + ", " + regcodes["_FirstName"]
    regcodes["_LastNameNorm"] = regcodes["_LastName"].apply(norm)
    regcodes["_FirstNameNorm"] = regcodes["_FirstName"].apply(norm)

    folders = [f for f in os.listdir(answers_folder)
               if os.path.isdir(os.path.join(answers_folder, f)) and not f.startswith('.')]

    question_files = glob.glob(os.path.join(questions_folder, "*.xlsx"))
    questions_df = {}
    for qf in question_files:
        try:
            key = '.'.join(os.path.basename(qf).split(".")[:-1])
            questions = pd.read_excel(qf, usecols=[0, 1], dtype=str)
            fmt = questions["Question"].to_list()
            fmt.insert(0, "Best Match")
            fmt.append("")
            questions_df[key] = fmt
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

            for filename in files:
                studentname = '.'.join(os.path.basename(filename).split(".")[:-1])

                header_data = pd.read_excel(filename, dtype=str, nrows=8, engine="calamine")
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

                matched = regcodes[regcodes["StudentNo"].str.strip() == studentcode] if studentcode else pd.DataFrame()

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
                    studentcode = matched["StudentNo"].iloc[0]
                    display_name = matched["_DisplayName"].iloc[0]
                else:
                    raw_parts = [i.strip() for i in scantron_name.split(',')]
                    if len(raw_parts) >= 2 and raw_parts[1].strip():
                        clean_last = ' '.join(re.sub(r'\*', '', raw_parts[0]).split())
                        clean_first = re.sub(r'\*', '', raw_parts[1].strip().split()[0]).strip()
                        display_name = (clean_last + ', ' + clean_first).strip(', ')
                    else:
                        display_name = re.sub(r'\*', '', scantron_name).strip()

                sheetdata = pd.read_excel(filename, dtype=str, usecols=[0, 1, 5], engine="calamine")
                while list(sheetdata.columns)[0] != 'Responses':
                    new_header = sheetdata.iloc[0].tolist()
                    sheetdata.columns = new_header
                    sheetdata = sheetdata.iloc[1:].reset_index(drop=True)

                scores = sheetdata.iloc[0:, 1].tolist()
                correct_answers = sheetdata.iloc[0:, 2].tolist()
                for i in range(len(scores)):
                    if isEmpty(scores[i]) and not isEmpty(correct_answers[i]):
                        scores[i] = 'D' if correct_answers[i][1] != 'D' else 'A'

                scores.insert(0, studentcode)
                output[display_name] = scores

            final_df = pd.DataFrame(output).T
            max_colno = final_df.shape[1]
            final_df.columns = list(range(max_colno))

            qkey = '-'.join(folder_name.split("-")[:-1]) if if_section == 1 else '-'.join(folder_name.split("-")[:2])
            if qkey in questions_df:
                questions_status = '— questions included'
                question_headers = questions_df[qkey]
                if len(question_headers) <= max_colno:
                    while len(question_headers) < max_colno:
                        question_headers.append("")
                else:
                    while len(question_headers) > final_df.shape[1]:
                        final_df[final_df.shape[1]] = np.nan
                final_df.columns = question_headers

            out_file = os.path.join(output_folder, folder_name + ".xlsx")
            final_df.to_excel(out_file, index=True)
            results.append({'folder': folder_name, 'status': 'success',
                            'message': f'{folder_name} {questions_status}',
                            'output': folder_name + '.xlsx'})

        except Exception as e:
            exc_type, exc_obj, tb = sys.exc_info()
            results.append({'folder': folder_name, 'status': 'error',
                            'message': f'{folder_name}: {e} (line {tb.tb_lineno})', 'output': ''})

    return results


if __name__ == '__main__':
    for r in run_processing():
        print(r['message'])


