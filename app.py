from flask import Flask, render_template, request, send_file, redirect, url_for
import os, glob, shutil
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'scantron_reader_dev')
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB max upload

# On Render with a Persistent Disk, DATA_DIR=/data; locally falls back to the project folder
BASE_DIR      = os.environ.get('DATA_DIR', os.path.dirname(os.path.abspath(__file__)))
STUDENTS_DIR  = os.path.join(BASE_DIR, 'Students')
ANSWERS_DIR   = os.path.join(BASE_DIR, 'Answers')
QUESTIONS_DIR = os.path.join(BASE_DIR, 'Questions')
CONVERTED_DIR = os.path.join(BASE_DIR, 'Converted')

for d in (STUDENTS_DIR, ANSWERS_DIR, QUESTIONS_DIR, CONVERTED_DIR):
    os.makedirs(d, exist_ok=True)


def get_state():
    students_exists = os.path.exists(os.path.join(STUDENTS_DIR, 'students.xlsx'))

    answer_folders = {}
    for folder in sorted(os.listdir(ANSWERS_DIR)):
        if folder.startswith('.'): continue
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


@app.route('/')
def index():
    return render_template('index.html', process_results=None, **get_state())


@app.route('/upload/students', methods=['POST'])
def upload_students():
    f = request.files.get('file')
    if f and f.filename.endswith('.xlsx'):
        f.save(os.path.join(STUDENTS_DIR, 'students.xlsx'))
    return redirect(url_for('index'))


@app.route('/upload/answers', methods=['POST'])
def upload_answers():
    folder_name = request.form.get('folder_name', '').strip()
    files = request.files.getlist('files')
    if folder_name and files:
        safe = folder_name.replace('/', '_').replace('\\', '_').replace('..', '')
        folder_path = os.path.join(ANSWERS_DIR, safe)
        os.makedirs(folder_path, exist_ok=True)
        for f in files:
            if f and f.filename.endswith('.xlsx'):
                fname = f.filename.replace('/', '_').replace('\\', '_')
                f.save(os.path.join(folder_path, fname))
    return redirect(url_for('index'))


@app.route('/upload/questions', methods=['POST'])
def upload_questions():
    for f in request.files.getlist('files'):
        if f and f.filename.endswith('.xlsx'):
            fname = secure_filename(f.filename) or f.filename
            f.save(os.path.join(QUESTIONS_DIR, fname))
    return redirect(url_for('index'))


@app.route('/delete/answers/<path:folder>', methods=['POST'])
def delete_answer_folder(folder):
    fp = os.path.join(ANSWERS_DIR, folder)
    if os.path.isdir(fp) and os.path.abspath(fp).startswith(ANSWERS_DIR):
        shutil.rmtree(fp)
    return redirect(url_for('index'))


@app.route('/delete/question/<filename>', methods=['POST'])
def delete_question(filename):
    fp = os.path.join(QUESTIONS_DIR, filename)
    if os.path.isfile(fp):
        os.remove(fp)
    return redirect(url_for('index'))


@app.route('/delete/output/<filename>', methods=['POST'])
def delete_output(filename):
    fp = os.path.join(CONVERTED_DIR, filename)
    if os.path.isfile(fp):
        os.remove(fp)
    return redirect(url_for('index'))


@app.route('/process', methods=['POST'])
def process():
    from ans_reader import run_processing
    results = run_processing(BASE_DIR)
    return render_template('index.html', process_results=results, **get_state())


@app.route('/download/<filename>')
def download(filename):
    fp = os.path.join(CONVERTED_DIR, filename)
    if os.path.isfile(fp):
        return send_file(fp, as_attachment=True, download_name=filename)
    return 'File not found', 404


if __name__ == '__main__':
    print('Scantron Reader — open http://localhost:5000 in your browser')
    app.run(debug=False, port=5000)
