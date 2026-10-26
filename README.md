# Scantron Reader

A Flask web app for a few related exam-processing tasks. Run it once and use
whichever tab you need — nothing here requires the command line beyond
starting the server.

## Running it

**Prerequisites:** Python 3.11 (see `runtime.txt`) and `pip`.

```bash
cd scantron-reader

# Optional but recommended: keep this project's packages separate from
# anything else on your machine.
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
python3 app.py
```

Then open **http://localhost:8080** in your browser.

You'll see a line like `Running on http://127.0.0.1:8080` in the terminal
once it's ready. Leave that terminal window open — closing it (or pressing
`Ctrl+C` in it) stops the server. To come back to it later, run
`python3 app.py` again from the project folder (re-activating the virtual
environment first, if you made one: `source venv/bin/activate`).

**"Address already in use" / port 8080 busy:** something's already running
on that port — most likely an earlier copy of this same server you forgot
was still open. Find and stop it, then try again:

```bash
lsof -ti :8080 -sTCP:LISTEN | xargs kill
python3 app.py
```

## The tabs

- **Convert Questionnaire** — upload a PDF exam questionnaire and get back an
  `.xlsx` of its questions/choices, ready for the other tabs.
- **CO Analysis → Tags** — upload a CO Analysis workbook, pick which
  sheet(s) to convert, and get Module/CO/ILO/Thinking-Skills tag codes (and,
  per sheet, a correct-answer list from the "Correct Answer" column) —
  either as one combined workbook or as individual `<course>_tags.xlsx` /
  `<course>_co-analysis.xlsx` files.
- **Prepare Exam Template** — upload an exam template plus (optionally) a
  tags file and a correct-answer file, and get back the template filled in:
  `iscorrect` columns set from the answer key, and Content
  Standards/Competency/TOPIC/THINKING SKILLS/DOMAIN filled from the tags.
  The tags file can be either the traditional one-file-per-exam style or a
  single combined workbook (matched by each sheet's own name) — exactly what
  "CO Analysis → Tags" produces.
- **Convert Student Answer** — upload scanned/OMR student answer sheets
  (per exam folder) plus the question files and a student list, and get back
  each student's answers as `.xlsx`.

## Project layout

```
app.py                  Flask routes — the only place that knows about all four tabs
templates/index.html    The whole UI (one page, tab-switched client-side)

scantron/        Convert Student Answer — reading OMR answer sheets
pdf_to_excel/    Convert Questionnaire — PDF → Excel
exam_autofill/   Prepare Exam Template — filling in a template from tags + an answer key
tags/            CO Analysis → Tags

Students/, Answers/, Questions/, Converted/   Convert Student Answer's working data (gitignored)
temp_sessions/                                Per-browser-session scratch space for the other tabs (gitignored)
```

Each feature package is self-contained except for one deliberate exception:
`scantron/reader.py` borrows a handful of filename-suffix constants from
`exam_autofill/config.py` so a file re-uploaded from an earlier stage is
still recognized — not a sign the two features are otherwise related.

## Deployment

Deployed on Render (see `render.yaml`) — a persistent disk is mounted at
`/data` (via the `DATA_DIR` env var) so uploaded students/answers/questions
survive a redeploy. `temp_sessions/` is ephemeral scratch space for the
other three tabs and is cleaned up automatically after 2 hours.
