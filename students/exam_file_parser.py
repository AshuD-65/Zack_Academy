"""
Exam File Parser
Reads a teacher-uploaded file (PDF, TXT, DOCX) and extracts
questions in this format:

Q: What is Python?
A) A programming language
B) A snake
C) A database
D) An operating system
Answer: A

Q: Python is interpreted.
Answer: True

Supports:
- Multiple choice  (options A B C D, answer is A/B/C/D)
- True/False       (no options needed, answer is True or False)
"""

import io
import re

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


def extract_text_from_uploaded_file(file_obj, filename: str) -> str:
    """Read raw text from an in-memory uploaded file."""
    filename_lower = filename.lower()
    raw = file_obj.read()

    # PDF
    if filename_lower.endswith('.pdf') and PdfReader:
        try:
            reader = PdfReader(io.BytesIO(raw))
            pages = [page.extract_text() or '' for page in reader.pages]
            return '\n'.join(pages)
        except Exception:
            return ''

    # Plain text / markdown
    if filename_lower.endswith(('.txt', '.md')):
        for enc in ('utf-8', 'latin-1'):
            try:
                return raw.decode(enc, errors='ignore')
            except Exception:
                continue

    # DOCX (basic — read XML without python-docx dependency)
    if filename_lower.endswith('.docx'):
        try:
            import zipfile
            from xml.etree import ElementTree as ET
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                with z.open('word/document.xml') as doc_xml:
                    tree = ET.parse(doc_xml)
                    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                    texts = [t.text or '' for t in tree.findall('.//w:t', ns)]
                    return ' '.join(texts)
        except Exception:
            return ''

    return ''


def parse_questions_from_text(text: str) -> list:
    """
    Parse text into a list of question dicts:
    {
        'question_text': str,
        'question_type': 'MULTIPLE_CHOICE' | 'TRUE_FALSE',
        'options_json': list | None,
        'correct_answer': str,   # A/B/C/D  or  True/False
    }

    Supported formats:
    ---
    Q: Question text here
    A) Option one
    B) Option two
    C) Option three
    D) Option four
    Answer: B

    Q: True or false question here
    Answer: True
    ---
    """
    questions = []

    # Normalize line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # Split on question boundaries: lines starting with Q: or numbered like 1. / 1)
    # Support both  "Q:"  and  "1."  and  "Question 1."
    question_blocks = re.split(
        r'\n(?=(?:Q\s*[:\-]\s*|(?:Question\s*)?\d+[\.\)]\s*))',
        text,
        flags=re.IGNORECASE
    )

    for block in question_blocks:
        block = block.strip()
        if not block:
            continue

        parsed = _parse_single_block(block)
        if parsed:
            questions.append(parsed)

    return questions


def _parse_single_block(block: str) -> dict | None:
    """Parse one question block."""
    lines = [l.strip() for l in block.splitlines() if l.strip()]
    if not lines:
        return None

    # ── Extract question text ──
    # Remove leading "Q:" / "1." / "Question 1." prefix
    q_line = lines[0]
    q_line = re.sub(r'^(?:Q\s*[:\-]\s*|(?:Question\s*)?\d+[\.\)]\s*)', '', q_line, flags=re.IGNORECASE).strip()
    if not q_line:
        return None

    # ── Collect remaining lines ──
    options = {}      # {'A': 'text', 'B': 'text', ...}
    answer_raw = None

    for line in lines[1:]:
        # Option line: A) / A. / A: / (A)
        opt_match = re.match(r'^[\(\[]?([A-Da-d])[\)\].:\s]\s*(.+)', line)
        if opt_match:
            letter = opt_match.group(1).upper()
            options[letter] = opt_match.group(2).strip()
            continue

        # Answer line
        ans_match = re.match(r'^(?:Answer|Ans|Correct)\s*[:\-]\s*(.+)', line, re.IGNORECASE)
        if ans_match:
            answer_raw = ans_match.group(1).strip()
            continue

        # If no Q prefix was used and question text spans multiple lines before options
        # just append to question text
        if not opt_match and not ans_match and not options:
            q_line += ' ' + line

    if not answer_raw:
        return None  # No answer found — skip

    answer_upper = answer_raw.strip().upper()

    # ── Determine question type ──
    if answer_upper in ('TRUE', 'FALSE', 'T', 'F'):
        correct = 'True' if answer_upper in ('TRUE', 'T') else 'False'
        return {
            'question_text': q_line,
            'question_type': 'TRUE_FALSE',
            'options_json': None,
            'correct_answer': correct,
        }

    if answer_upper in ('A', 'B', 'C', 'D') and options:
        options_list = [options.get(l, '') for l in ('A', 'B', 'C', 'D') if options.get(l)]
        if len(options_list) < 2:
            return None
        return {
            'question_text': q_line,
            'question_type': 'MULTIPLE_CHOICE',
            'options_json': [options.get(l, '') for l in ('A', 'B', 'C', 'D') if options.get(l)],
            'correct_answer': answer_upper,
        }

    # Answer is a full text (not A/B/C/D) — treat as True/False or skip
    return None
