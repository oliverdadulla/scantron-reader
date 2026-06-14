import glob
import io
import os
from dotenv import load_dotenv
load_dotenv()
import shutil
import time
import uuid
import zipfile
from pathlib import Path

from flask import Flask, flash, jsonify, redirect, render_template, request, send_file, session, url_for
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'scantron_reader_dev')
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB

# ── Scantron Reader paths ─────────────────────────────────────────────────────
BASE_DIR      = os.environ.get('DATA_DIR', os.path.dirname(os.path.abspath(__file__)))
STUDENTS_DIR  = os.path.join(BASE_DIR, 'Students')
ANSWERS_DIR   = os.path.join(BASE_DIR, 'Answers')
QUESTIONS_DIR = os.path.join(BASE_DIR, 'Questions')
CONVERTED_DIR = os.path.join(BASE_DIR, 'Converted')

for _d in (STUDENTS_DIR, ANSWERS_DIR, QUESTIONS_DIR, CONVERTED_DIR):
    os.makedirs(_d, exist_ok=True)

# ── Exam Autofill session paths ───────────────────────────────────────────────
AUTOFILL_TEMP_BASE = Path(BASE_DIR) / 'temp_sessions'
AUTOFILL_TEMP_BASE.mkdir(parents=True, exist_ok=True)
SESSION_TTL = 2 * 60 * 60  # 2 hours

from config import CORRECT_ANSWER_SUFFIX, EXAM_TEMPLATE_SUFFIX, TAGS_SUFFIX
from answer_filler import apply_answers, build_answer_lookup
from loader import load_answers, load_main, load_mapping
from merger import apply_lookup, build_lookup
from writer import write_output

ALL_SUFFIXES = (EXAM_TEMPLATE_SUFFIX, TAGS_SUFFIX, CORRECT_ANSWER_SUFFIX)


# ── Scantron Reader helpers ───────────────────────────────────────────────────
def get_state():
    students_exists = os.path.exists(os.path.join(STUDENTS_DIR, 'students.xlsx'))

    answer_folders = {}
    for folder in sorted(os.listdir(ANSWERS_DIR)):
        if folder.startswith('.'):
            continue
        fp = os.path.join(ANSWERS_DIR, folder)
        if os.path.isdir(fp):
            files = [f for f in os.listdir(fp) if f.endswith('.xlsx') and not f.startswith('~$')]
            answer_folders[folder] = sorted(files)

    question_files = sorted([
        os.path.basename(f) for f in glob.glob(os.path.join(QUESTIONS_DIR, '*.xlsx'))
        if not os.path.basename(f).startswith('~$')
    ])

    output_files = sorted([
        os.path.basename(f) for f in glob.glob(os.path.join(CONVERTED_DIR, '*.xlsx'))
        if not os.path.basename(f).startswith('~$')
    ])

    return dict(students_exists=students_exists, answer_folders=answer_folders,
                question_files=question_files, output_files=output_files)


# ── Exam Autofill helpers ─────────────────────────────────────────────────────
def extract_base(filename: str) -> str:
    stem = Path(filename).stem
    for suffix in ALL_SUFFIXES:
        if stem.endswith(suffix):
            return stem[:-len(suffix)]
    return stem


def cleanup_old_sessions():
    now = time.time()
    for d in AUTOFILL_TEMP_BASE.iterdir():
        if d.is_dir() and (now - d.stat().st_mtime) > SESSION_TTL:
            shutil.rmtree(d, ignore_errors=True)


def get_autofill_session_dir() -> Path:
    if 'autofill_sid' not in session:
        session['autofill_sid'] = str(uuid.uuid4())
        cleanup_old_sessions()
    d = AUTOFILL_TEMP_BASE / session['autofill_sid']
    d.mkdir(exist_ok=True)
    return d


def list_autofill_xlsx(directory: Path) -> list:
    if not directory.exists():
        return []
    return sorted(
        [f for f in directory.iterdir() if f.suffix == '.xlsx' and not f.name.startswith('~$')],
        key=lambda f: f.name,
    )


def build_autofill_stems(directory: Path) -> dict:
    result = {}
    for f in list_autofill_xlsx(directory):
        base = extract_base(f.name)
        if base not in result:
            result[base] = f
    return result


# ── Main route ────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    active_tab = request.args.get('tab', 'scantron')
    return render_template('index.html', process_results=None,
                           active_tab=active_tab, **get_state())


# ── Scantron Reader routes ────────────────────────────────────────────────────
@app.route('/upload/students', methods=['POST'])
def upload_students():
    f = request.files.get('file')
    if not f or not f.filename:
        flash('No file was selected. Please choose a students.xlsx file.', 'warning')
    elif not f.filename.endswith('.xlsx'):
        flash(f'"{f.filename}" is not an .xlsx file. Only Excel (.xlsx) files are accepted.', 'warning')
    else:
        f.save(os.path.join(STUDENTS_DIR, 'students.xlsx'))
    return redirect('/?tab=scantron')


@app.route('/upload/answers', methods=['POST'])
def upload_answers():
    folder_name = request.form.get('folder_name', '').strip()
    files = request.files.getlist('files')
    if not folder_name:
        flash('Could not determine folder name. Please try selecting the folder again.', 'warning')
        return redirect('/?tab=scantron')
    safe = folder_name.replace('/', '_').replace('\\', '_').replace('..', '')
    folder_path = os.path.join(ANSWERS_DIR, safe)
    os.makedirs(folder_path, exist_ok=True)
    saved, skipped = 0, []
    for f in files:
        if f and f.filename.endswith('.xlsx'):
            fname = f.filename.replace('/', '_').replace('\\', '_')
            f.save(os.path.join(folder_path, fname))
            saved += 1
        elif f and f.filename:
            skipped.append(os.path.basename(f.filename))
    if saved == 0:
        if os.path.isdir(folder_path) and not os.listdir(folder_path):
            os.rmdir(folder_path)
        flash(f'No .xlsx files found in "{folder_name}". Nothing was saved.', 'warning')
    elif skipped:
        flash(f'{len(skipped)} non-.xlsx file(s) were skipped in "{folder_name}".', 'warning')
    return redirect('/?tab=scantron')


@app.route('/upload/questions', methods=['POST'])
def upload_questions():
    saved, skipped = 0, []
    for f in request.files.getlist('files'):
        if f and f.filename.endswith('.xlsx'):
            fname = secure_filename(f.filename) or f.filename
            f.save(os.path.join(QUESTIONS_DIR, fname))
            saved += 1
        elif f and f.filename:
            skipped.append(os.path.basename(f.filename))
    if saved == 0 and skipped:
        flash(f'No .xlsx files were uploaded. {len(skipped)} file(s) were rejected (wrong format).', 'warning')
    elif skipped:
        flash(f'{len(skipped)} non-.xlsx file(s) were skipped.', 'warning')
    return redirect('/?tab=scantron')


@app.route('/delete/answers/<path:folder>', methods=['POST'])
def delete_answer_folder(folder):
    fp = os.path.join(ANSWERS_DIR, folder)
    if os.path.isdir(fp) and os.path.abspath(fp).startswith(ANSWERS_DIR):
        shutil.rmtree(fp)
    return redirect('/?tab=scantron')


@app.route('/delete/question/<filename>', methods=['POST'])
def delete_question(filename):
    fp = os.path.join(QUESTIONS_DIR, filename)
    if os.path.isfile(fp):
        os.remove(fp)
    return redirect('/?tab=scantron')


@app.route('/delete/output/<filename>', methods=['POST'])
def delete_output(filename):
    fp = os.path.join(CONVERTED_DIR, filename)
    if os.path.isfile(fp):
        os.remove(fp)
    return redirect('/?tab=scantron')


@app.route('/process', methods=['POST'])
def process():
    from ans_reader import run_processing
    results = run_processing(BASE_DIR)
    return render_template('index.html', process_results=results,
                           active_tab='scantron', **get_state())


@app.route('/download/<filename>')
def download(filename):
    fp = os.path.join(CONVERTED_DIR, filename)
    if os.path.isfile(fp):
        return send_file(fp, as_attachment=True, download_name=filename)
    return 'File not found', 404


@app.route('/clear', methods=['POST'])
def clear_all():
    for d in (STUDENTS_DIR, ANSWERS_DIR, QUESTIONS_DIR, CONVERTED_DIR):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d, exist_ok=True)
    return redirect('/?tab=scantron')


# ── Exam Autofill routes ──────────────────────────────────────────────────────
@app.route('/autofill/upload', methods=['POST'])
def autofill_upload():
    file_type = request.form.get('type')
    if file_type not in ('exam', 'tags', 'answer'):
        return jsonify({'error': 'Invalid type'}), 400
    if 'files' not in request.files:
        return jsonify({'error': 'No files provided'}), 400

    dest = get_autofill_session_dir() / file_type
    dest.mkdir(exist_ok=True)

    uploaded = []
    for f in request.files.getlist('files'):
        name = Path(f.filename).name
        if not name.endswith('.xlsx') or name.startswith('~$'):
            continue
        f.save(dest / name)
        uploaded.append({'filename': name, 'base': extract_base(name)})

    return jsonify({'uploaded': uploaded})


@app.route('/autofill/remove/<file_type>/<filename>', methods=['DELETE'])
def autofill_remove(file_type, filename):
    if file_type not in ('exam', 'tags', 'answer'):
        return jsonify({'error': 'Invalid type'}), 400
    target = get_autofill_session_dir() / file_type / Path(filename).name
    if target.exists():
        target.unlink()
    return jsonify({'ok': True})


@app.route('/autofill/process', methods=['POST'])
def autofill_process():
    session_dir = get_autofill_session_dir()
    exam_dir    = session_dir / 'exam'
    tags_dir    = session_dir / 'tags'
    answer_dir  = session_dir / 'answer'
    output_dir  = session_dir / 'output'
    output_dir.mkdir(exist_ok=True)

    exam_stems = build_autofill_stems(exam_dir)
    if not exam_stems:
        return jsonify({'error': 'No exam template files uploaded.'}), 400

    tags_stems   = build_autofill_stems(tags_dir)
    answer_stems = build_autofill_stems(answer_dir)

    results = []
    for base, exam_path in sorted(exam_stems.items()):
        item = {
            'base': base, 'exam': exam_path.name,
            'tags': None, 'answers': None, 'output': None,
            'rows': 0, 'status': 'ok', 'warnings': [],
        }
        try:
            template_df, main_df, sheet_names = load_main(str(exam_path))
            item['rows'] = len(main_df)

            if base in answer_stems:
                answers_df, answer_col = load_answers(str(answer_stems[base]))
                main_df = apply_answers(main_df, build_answer_lookup(answers_df, answer_col))
                item['answers'] = answer_stems[base].name
            else:
                item['warnings'].append('No correct answer file — iscorrect columns unchanged')

            if base in tags_stems:
                tags_df = load_mapping(str(tags_stems[base]))
                main_df, unmatched = apply_lookup(main_df, build_lookup(tags_df))
                item['tags'] = tags_stems[base].name
                if unmatched:
                    item['warnings'].append(f'No TOPIC match for Question No.: {sorted(unmatched)}')
            else:
                item['warnings'].append('No tags file — metadata columns left blank')

            out_name = f'{base}_completed.xlsx'
            write_output(template_df, main_df, sheet_names, str(output_dir / out_name))
            item['output'] = out_name

        except Exception as exc:
            item['status'] = 'error'
            item['error'] = str(exc)

        results.append(item)

    return jsonify({'results': results})


@app.route('/autofill/download/<filename>')
def autofill_download(filename):
    path = get_autofill_session_dir() / 'output' / Path(filename).name
    if not path.exists():
        return 'File not found', 404
    return send_file(
        str(path), as_attachment=True, download_name=path.name,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@app.route('/autofill/download-all')
def autofill_download_all():
    output_dir = get_autofill_session_dir() / 'output'
    files = [f for f in output_dir.iterdir() if f.suffix == '.xlsx'] if output_dir.exists() else []
    if not files:
        return 'No files to download', 404

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f.name)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name='completed_files.zip',
                     mimetype='application/zip')


@app.route('/autofill/clear', methods=['POST'])
def autofill_clear():
    shutil.rmtree(get_autofill_session_dir(), ignore_errors=True)
    session.pop('autofill_sid', None)
    return jsonify({'ok': True})


# ── PDF to Excel routes ───────────────────────────────────────────────────────
from pdf_extractor import extract_text as pdf_extract_text
from pdf_parser    import parse_questions
from pdf_writer    import save_to_excel as pdf_save_to_excel
from pdf_grok_filter import filter_questions as pdf_filter_questions


def get_pdf_session_dir() -> Path:
    if 'pdf_sid' not in session:
        session['pdf_sid'] = str(uuid.uuid4())
    d = AUTOFILL_TEMP_BASE / ('pdf_' + session['pdf_sid'])
    d.mkdir(exist_ok=True)
    return d


@app.route('/pdf/upload', methods=['POST'])
def pdf_upload():
    if 'files' not in request.files:
        return jsonify({'error': 'No files provided'}), 400
    dest = get_pdf_session_dir() / 'input'
    dest.mkdir(exist_ok=True)
    uploaded = []
    for f in request.files.getlist('files'):
        name = Path(f.filename).name
        if not name.lower().endswith('.pdf'):
            continue
        f.save(dest / name)
        uploaded.append(name)
    return jsonify({'uploaded': uploaded})


@app.route('/pdf/remove/<filename>', methods=['DELETE'])
def pdf_remove(filename):
    target = get_pdf_session_dir() / 'input' / Path(filename).name
    if target.exists():
        target.unlink()
    return jsonify({'ok': True})


@app.route('/pdf/process', methods=['POST'])
def pdf_process():
    data       = request.get_json(silent=True) or {}
    api_key    = data.get('api_key', '').strip()
    use_ai     = data.get('use_ai', False)

    session_dir = get_pdf_session_dir()
    input_dir   = session_dir / 'input'
    output_dir  = session_dir / 'output'
    output_dir.mkdir(exist_ok=True)

    pdf_files = sorted(input_dir.glob('*.pdf')) if input_dir.exists() else []
    if not pdf_files:
        return jsonify({'error': 'No PDF files uploaded.'}), 400

    results = []
    for pdf_path in pdf_files:
        item = {'name': pdf_path.name, 'status': 'ok', 'questions': 0,
                'output': None, 'warnings': [], 'ai_filtered': False}
        try:
            full_text = pdf_extract_text(pdf_path)
            questions = parse_questions(full_text)

            if not questions:
                item['status']  = 'error'
                item['error']   = 'No questions found in this PDF.'
                results.append(item)
                continue

            if use_ai:
                try:
                    before = len(questions)
                    questions = pdf_filter_questions(questions, api_key)
                    removed = before - len(questions)
                    item['ai_filtered'] = True
                    if removed:
                        item['warnings'].append(f'AI removed {removed} non-question item(s)')
                except Exception as e:
                    item['warnings'].append(f'AI filter skipped: {e}')

            out_path = pdf_save_to_excel(questions, pdf_path, output_dir)
            item['questions'] = len(questions)
            item['output']    = out_path.name

        except Exception as exc:
            item['status'] = 'error'
            item['error']  = str(exc)

        results.append(item)

    return jsonify({'results': results})


@app.route('/pdf/download/<filename>')
def pdf_download(filename):
    path = get_pdf_session_dir() / 'output' / Path(filename).name
    if not path.exists():
        return 'File not found', 404
    return send_file(str(path), as_attachment=True, download_name=path.name,
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@app.route('/pdf/download-all')
def pdf_download_all():
    output_dir = get_pdf_session_dir() / 'output'
    files = list(output_dir.glob('*.xlsx')) if output_dir.exists() else []
    if not files:
        return 'No files to download', 404
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.write(f, f.name)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name='pdf_converted.zip',
                     mimetype='application/zip')


@app.route('/pdf/clear', methods=['POST'])
def pdf_clear():
    shutil.rmtree(get_pdf_session_dir(), ignore_errors=True)
    session.pop('pdf_sid', None)
    return jsonify({'ok': True})


if __name__ == '__main__':
    print('Scantron Reader + Exam Autofill — open http://localhost:8080 in your browser')
    app.run(debug=False, port=8080)
