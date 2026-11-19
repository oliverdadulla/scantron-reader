COLUMN_ORDER = [
    "Question No.",
    "Question",
    "Choice1",
    "iscorrect1 (1/0)",
    "Choice2",
    "iscorrect2 (1/0)",
    "Choice_3",
    "iscorrect3 (1/0)",
    "Choice_4",
    "iscorrect4 (1/0)",
    "Rate/Points",
    "Content Standards",
    "Competency",
    "TOPIC",
    "SUBTOPIC",
    "THINKING SKILLS",
    "DOMAIN",
    "RECOMMENDATIONS",
]

BLANK_COLUMNS = [
    "iscorrect1 (1/0)",
    "iscorrect2 (1/0)",
    "iscorrect3 (1/0)",
    "iscorrect4 (1/0)",
    "Rate/Points",
    "Content Standards",
    "Competency",
    "TOPIC",
    "SUBTOPIC",
    "THINKING SKILLS",
    "DOMAIN",
    "RECOMMENDATIONS",
]

TWO_COLUMN_CHAR_THRESHOLD = 50

# AI-assisted re-parsing (see ai_refine.py) — only runs on questions the
# regex parser flagged as suspicious, and only if GROQ_API_KEY is set.
# Groq's model lineup changes over time (their old llama-3.3-70b-versatile
# is gone) — check `client.models.list()` if this one stops working too.
GROQ_MODEL    = "openai/gpt-oss-120b"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
