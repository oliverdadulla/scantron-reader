import re
from collections import Counter

import pandas as pd

# Google Sheets / LibreOffice exports can write <family val="34"/> in styles.xml, but openpyxl
# caps font family at 14 and refuses the whole workbook ("could not read stylesheet").
# Font family is cosmetic and nothing here reads it, so raise the cap before opening anything.
from openpyxl.styles.fonts import Font
Font.family.max = 100

# A module number in column B is written as "1", "M1", "M 2", "m3" or "3A". The optional
# trailing letter is kept so 3A and 3B stay separate modules.
MODULE_NUMBER = re.compile(r"(?:[Mm]\s*)?(\d+(?:\.\d+)?)\s*([A-Za-z]?)")

THINKING_SKILLS = [
    {'code': '-TS-RE', 'desc': ['REMEMBERING', 'REMEMBER', 'KNOWLEDGE']},
    {'code': '-TS-UN', 'desc': ['UNDERSTANDING', 'UNDERSTAND', 'COMPREHENSION']},
    {'code': '-TS-AP', 'desc': ['APPLYING', 'APPLY', 'APPLICATION']},
    {'code': '-TS-AN', 'desc': ['ANALYZING', 'ANALYZE', 'ANALYSIS']},
    {'code': '-TS-EV', 'desc': ['EVALUATING', 'EVALUATE', 'EVALUATION']},
    {'code': '-TS-Cr', 'desc': ['CREATING', 'CREATE']},
    {'code': '-TS-E', 'desc': ['REMEMBERING/UNDERSTANDING', 'REMEMBER/UNDERSTAND']},
    {'code': '-TS-Ave', 'desc': ['APPLYING/ANALYZING', 'APPLY/ANALYZE']},
    {'code': '-TS-D', 'desc': ['EVALUATING/CREATING', 'EVALUATE/CREATE']},
]

DEFAULT_TAG_PREFIX = "26/27-Prelims-"


def format_module_label(value):
    """Module label for column B: a module number gets the 'Module ' word back, an existing label is kept."""
    if pd.isnull(value):
        return ""
    text = str(value).replace(" ", " ").strip()
    if not text or text.lower() == "nan":
        return ""
    # Excel hands a whole number to pandas as a float, so "1" arrives here as "1.0"
    text = re.sub(r"^(\d+)\.0+$", r"\1", text)
    match = MODULE_NUMBER.fullmatch(text)
    if match:
        return f"Module {match.group(1)}{match.group(2).upper()}"
    # "M" with no readable number behind it is a typo in the sheet, e.g. "M!" for "M1"
    if re.match(r"[Mm](?![A-Za-z])", text):
        print(f"  WARNING column B has {text!r}, which is not a module number - left as is")
    return text


def clean_ilo_code(value):
    """Column F is an ILO number, sometimes typed as "ILO 1" or handed over as 1.0. Normalise to ILO1."""
    text = str(value).replace(chr(160), " ").strip()
    # A blank anywhere in column F makes pandas read the whole column as floats, so "1" arrives as "1.0"
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    text = text.replace(" ", "").replace(".", "_")
    if not text.upper().startswith("ILO"):
        text = f"ILO{text}"
    return text


def suffix_letters(n):
    """a, b, ... z, aa, ab ... for the nth (0-based) repeat of a tag code."""
    letters = ""
    n += 1
    while n:
        n, rem = divmod(n - 1, 26)
        letters = chr(ord("a") + rem) + letters
    return letters


def to_ranges(arr):
    if not arr:
        return ""
    try:
        # Ensure items are integers for sorting and range logic
        arr = sorted(set([int(x) for x in arr if pd.notnull(x)]))
    except Exception:
        arr = sorted(set(arr))

    if not arr:
        return ""

    ranges = []
    start = arr[0]
    for i in range(1, len(arr)):
        if arr[i] != arr[i - 1] + 1:
            end = arr[i - 1]
            ranges.append(f"{start}" if start == end else f"{start}-{end}")
            start = arr[i]
    end = arr[-1]
    ranges.append(f"{start}" if start == end else f"{start}-{end}")
    return ", ".join(ranges)


def get_sheet_names(path):
    return pd.ExcelFile(path, engine="openpyxl").sheet_names


def recode_sheet_name(sheet):
    """'PHARM311 LABORATORY' -> 'PHARM311-LAB', 'PHARM311 LECTURE' -> 'PHARM311-LEC'."""
    parts = sheet.strip().split()
    if parts and parts[-1] == 'LABORATORY':
        parts[-1] = 'LAB'
    if parts and parts[-1] == 'LECTURE':
        parts[-1] = 'LEC'
    return '-'.join(parts)


def process_sheet(filename, sheet, tag_prefix):
    """Builds the Module/CO/ILO/Thinking-Skills tag rows for one CO Analysis sheet."""
    output_df = []
    code_prefix = recode_sheet_name(sheet)

    # 1. Read specific columns (A, B, C, D, F, G)
    # Skiprows=8 means Row 9 is the first data row
    sheetdata = pd.read_excel(filename, sheet, skiprows=8, header=None, usecols="A,B,C,D,F,G")

    # 2. Assign temporary names for processing
    sheetdata.columns = [
        'Item No.',         # A
        'ModNum',           # B
        'ModTitle',         # C
        'Cognitive Level',  # D
        'ILO_CO',           # F
        'Coverage Focus'    # G
    ]

    # Cells holding only whitespace (incl. non-breaking spaces from pasted text) count as empty
    sheetdata = sheetdata.replace(r'^\s*$', pd.NA, regex=True)

    # 3. MERGE Column B and C into the 'Module' column
    # This creates "Module 1 - Sample Title"
    sheetdata['Module'] = [
        " - ".join(part for part in (format_module_label(num), str(title).strip()) if part)
        for num, title in zip(sheetdata['ModNum'], sheetdata['ModTitle'])
    ]

    # Rename ILO_CO back to the long name the rest of this function expects
    sheetdata = sheetdata.rename(columns={'ILO_CO': 'Intended Learning Outcome / Course Outcome'})

    # Clean up: Remove rows where Module title might be empty/NaN
    sheetdata = sheetdata.dropna(subset=['ModTitle'])

    sheetdata = sheetdata.sort_values(by=['Module', 'Intended Learning Outcome / Course Outcome'])

    # --- Modules Logic ---
    modules = sheetdata['Module'].unique()
    for idx, module in enumerate(modules, start=1):
        # The 'module' variable here now contains "Module 1 - Sample Title"
        itemnums = to_ranges(sheetdata.loc[sheetdata['Module'] == module, 'Item No.'].tolist())
        output_df.append({'code': f"{tag_prefix}{code_prefix}-D{idx}", 'desc': module, 'ItemNos': itemnums})

    # This replaces non-breaking spaces and tabs with a standard space, then strips ends
    sheetdata['Coverage Focus'] = sheetdata['Coverage Focus'].astype(str).replace(r'\s+', ' ', regex=True).str.strip()
    sheetdata['Intended Learning Outcome / Course Outcome'] = sheetdata['Intended Learning Outcome / Course Outcome'].astype(str).replace(r'\s+', ' ', regex=True).str.strip()

    # --- CO and ILO ---
    co_df = []
    ilo_df = []

    # We iterate through the modules we already identified
    for module_entry in [m for m in output_df if '-D' in m['code']]:
        module_name = module_entry['desc']
        module_code = module_entry['code']

        # 1. Get unique Course Outcomes (CO) for this Module (Column G)
        course_outcomes = sheetdata.loc[sheetdata['Module'] == module_name, 'Coverage Focus'].dropna().unique()

        for co_idx, co in enumerate(course_outcomes, start=1):
            # Get Item Numbers for this CO
            co_items = sheetdata.loc[(sheetdata['Module'] == module_name) &
                                     (sheetdata['Coverage Focus'] == co), 'Item No.'].tolist()

            co_df.append({
                'code': f"{module_code}-CO{co_idx}",
                'desc': co,
                'ItemNos': to_ranges(co_items)
            })

        # 2. ILO tags: one per distinct column G sentence inside an ILO number. The description is
        # the sheet's own wording and is never merged into a neighbouring sentence.
        module_rows = sheetdata[(sheetdata['Module'] == module_name)
                                & sheetdata['Intended Learning Outcome / Course Outcome'].notna()
                                & sheetdata['Coverage Focus'].notna()]

        ilo_groups = {}
        for idx, row in module_rows.iterrows():
            ilo_code = clean_ilo_code(row['Intended Learning Outcome / Course Outcome'])
            group = ilo_groups.setdefault(ilo_code, {})
            # 'first' is the row's position in the sheet, kept because the sort above is not stable
            entry = group.setdefault(row['Coverage Focus'], {'items': [], 'first': idx})
            entry['items'].append(row['Item No.'])
            entry['first'] = min(entry['first'], idx)

        for ilo_code, texts in ilo_groups.items():
            for text, entry in sorted(texts.items(), key=lambda kv: kv[1]['first']):
                ilo_df.append({
                    'code': f"{module_code}-{ilo_code}",  # e.g., MLS-LEC-D1-ILO1
                    'desc': text,
                    'ItemNos': to_ranges(entry['items'])
                })

    # An ILO number can now carry several sentences, so repeated codes are expected. Suffix them
    # a, b, c... in the order built above. This also still catches two raw spellings of the same
    # number ("ILO 1" and "1") colliding.
    code_counts = Counter(entry['code'] for entry in ilo_df)
    repeats = Counter()
    for entry in ilo_df:
        base = entry['code']
        if code_counts[base] > 1:
            entry['code'] = f"{base}{suffix_letters(repeats[base])}"
            repeats[base] += 1

    # Append the newly built CO and ILO lists to the main output
    output_df.extend(co_df)
    output_df.extend(ilo_df)

    # --- Thinking Skills ---
    # 1. Clean the column to ensure matches (Uppercase and stripped)
    cl_series = sheetdata['Cognitive Level'].astype(str).str.strip().str.upper()

    for ts in THINKING_SKILLS:
        # 2. Create an uppercase list of all valid terms for this category
        search_terms = [d.upper() for d in ts['desc']]

        # 3. Get the item numbers that match any of those terms
        items = sheetdata.loc[cl_series.isin(search_terms), 'Item No.'].tolist()

        # 4. ONLY append to the output if items were actually found
        if items:
            output_df.append({
                'code': tag_prefix + code_prefix + ts['code'],
                'desc': ts['desc'][0],  # Uses the primary name (e.g., REMEMBERING)
                'ItemNos': to_ranges(items)
            })

    return pd.DataFrame(output_df)


def build_tags(filename, sheet_names, tag_prefix=DEFAULT_TAG_PREFIX):
    """Processes each selected sheet of a CO Analysis workbook into a {sheet_name: DataFrame} dict."""
    grand_output_df = {}
    for sheet in sheet_names:
        grand_output_df[sheet] = process_sheet(filename, sheet, tag_prefix)
    return grand_output_df


def write_tags(grand_output_df, out_path):
    with pd.ExcelWriter(out_path) as writer:
        for sheet_name, df in grand_output_df.items():
            # Excel sheet names are capped at 31 characters and can't contain : \ / ? * [ ]
            safe_name = re.sub(r'[:\\/?*\[\]]', '-', sheet_name)[:31]
            df.to_excel(writer, sheet_name=safe_name, index=False)


def safe_filename(name):
    """Strips characters that aren't safe in a filename (path separators etc.)."""
    return re.sub(r'[\\/:*?"<>|]', '-', name).strip()


def tags_filename_for_sheet(sheet_name):
    """'PHARM311' -> 'PHARM311_tags.xlsx' — matches the one-file-per-exam
    naming convention Exam Autofill's Tags upload already recognizes."""
    return f"{safe_filename(sheet_name)}_tags.xlsx"


def write_single_sheet_tags(df, out_path):
    """Writes just the code/ItemNos columns for one sheet — the minimal
    content Exam Autofill's merger actually reads (see merger.build_lookup),
    for sharing a single exam/course's tags as its own small file."""
    df[['code', 'ItemNos']].to_excel(out_path, index=False)


def extract_correct_answers(filename, sheet):
    """Column E of a CO Analysis sheet is "Correct Answer" (A-E) — unlike the
    Module/CO/ILO tags, this is a flat one-row-per-question mapping, not
    grouped into ranges (every question has its own distinct answer).
    Matches what loader.load_answers() expects: column 1 = item number,
    column 2 = answer letter — one row per question.
    """
    df = pd.read_excel(filename, sheet, skiprows=8, header=None, usecols="A,E")
    df.columns = ['ItemNos', 'Correct Answer']
    df = df.replace(r'^\s*$', pd.NA, regex=True).dropna(subset=['ItemNos', 'Correct Answer'])
    # Excel hands a whole number to pandas as a float, so item 1 arrives as 1.0
    df['ItemNos'] = df['ItemNos'].apply(lambda v: int(v) if float(v).is_integer() else v)
    df['Correct Answer'] = df['Correct Answer'].astype(str).str.strip().str.upper()
    return df.reset_index(drop=True)


def build_correct_answers(filename, sheet_names):
    """Same shape as build_tags() but for the Correct Answer column."""
    return {sheet: extract_correct_answers(filename, sheet) for sheet in sheet_names}


def co_analysis_filename_for_sheet(sheet_name):
    """'PHARM311' -> 'PHARM311_co-analysis.xlsx' — matches
    config.CORRECT_ANSWER_SUFFIX, the suffix Exam Autofill's Correct Answer
    upload already recognizes."""
    return f"{safe_filename(sheet_name)}_co-analysis.xlsx"


def write_single_sheet_co_analysis(df, out_path):
    df.to_excel(out_path, index=False)
