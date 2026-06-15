"""
Exam File Parser
Reads a teacher-uploaded file (PDF, TXT, DOCX) and extracts questions.

Handles these real-world formats:

FORMAT 1 - Numbered with full answer text:
1. What is AI?
A. Databases
B. Machines that can perform intelligent tasks
C. Networks
D. Operating systems
Answer: B. Machines that can perform intelligent tasks

FORMAT 2 - Q: prefix:
Q: What is AI?
A) Databases
B) Machines that think
C) Networks
D) Operating systems
Answer: B

FORMAT 3 - True/False:
26. Artificial Intelligence aims to make machines perform tasks.
Answer: True
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

    # DOCX
    if filename_lower.endswith('.docx'):
        try:
            import zipfile
            from xml.etree import ElementTree as ET
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                with z.open('word/document.xml') as doc_xml:
                    tree = ET.parse(doc_xml)
                    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                    texts = [t.text or '' for t in tree.findall('.//w:t', ns)]
                    # Join with newlines at paragraph breaks
                    result = []
                    for elem in tree.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
                        para_texts = [t.text or '' for t in elem.findall('.//{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t')]
                        line = ''.join(para_texts).strip()
                        if line:
                            result.append(line)
                    return '\n'.join(result)
        except Exception:
            return ''

    return ''


def parse_questions_from_text(text: str) -> list:
    """
    Parse text into question dicts. Handles multiple real-world formats.
    Returns list of:
    {
        'question_text': str,
        'question_type': 'MULTIPLE_CHOICE' | 'TRUE_FALSE',
        'options_json': list | None,
        'correct_answer': str,   # A/B/C/D  or  True/False
    }
    """
    questions = []

    # Normalize line endings and clean up
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    # Split into blocks at each question boundary:
    # - "1." / "1)" at start of line
    # - "Q:" at start of line
    # - "Question 1" at start of line
    blocks = re.split(
        r'\n(?=(?:Q\s*[:\-]|(?:Question\s+)?\d+[\.\)]\s))',
        text,
        flags=re.IGNORECASE
    )

    for block in blocks:
        block = block.strip()
        if not block:
            continue
        parsed = _parse_single_block(block)
        if parsed:
            questions.append(parsed)

    return questions


def _parse_single_block(block: str) -> dict | None:
    """Parse one question block — handles both numbered and Q: formats."""
    lines = [l.strip() for l in block.splitlines() if l.strip()]
    if not lines:
        return None

    # ── Extract question text (first line, strip prefix) ──
    q_line = lines[0]
    # Remove:  "1."  "1)"  "Q:"  "Question 1."  "Question 1:"
    q_line = re.sub(
        r'^(?:Q\s*[:\-]\s*|(?:Question\s+)?\d+[\.\):\-]\s*)',
        '', q_line, flags=re.IGNORECASE
    ).strip()
    if not q_line:
        return None

    options = {}       # {'A': 'text', ...}
    answer_raw = None

    for line in lines[1:]:
        # ── Option line ──
        # Matches:  "A."  "A)"  "A:"  "A -"  "(A)"  "A. text"
        opt_match = re.match(
            r'^[\(\[]?([A-Da-d])[\)\]\.:\-]\s*(.+)',
            line
        )
        if opt_match:
            letter = opt_match.group(1).upper()
            option_text = opt_match.group(2).strip()
            options[letter] = option_text
            continue

        # ── Answer line ──
        # Matches:  "Answer: B"  "Answer: B. Full text"  "Ans: True"  "Correct: A"
        ans_match = re.match(
            r'^(?:Answer|Ans|Correct\s*Answer|Correct)\s*[:\-]\s*(.+)',
            line, re.IGNORECASE
        )
        if ans_match:
            answer_raw = ans_match.group(1).strip()
            continue

        # If no options yet and no answer found, it might be multi-line question
        if not options and answer_raw is None:
            q_line += ' ' + line

    if not answer_raw:
        return None

    # ── Extract just the letter from answer like "B. Machine Learning" ──
    # Try to get the leading letter first
    letter_match = re.match(r'^([A-Da-d])[\.\)\s]', answer_raw)
    if letter_match:
        answer_letter = letter_match.group(1).upper()
    else:
        # Maybe the answer IS the full option text — find which option matches
        answer_upper = answer_raw.strip().upper()
        answer_letter = None
        for letter, opt_text in options.items():
            if opt_text.upper() == answer_raw.upper():
                answer_letter = letter
                break

    # ── True/False ──
    answer_upper = answer_raw.strip().upper()
    if answer_upper in ('TRUE', 'FALSE', 'T', 'F') or (
        answer_raw.lower().startswith('true') and not options
    ) or (
        answer_raw.lower().startswith('false') and not options
    ):
        correct = 'True' if answer_upper.startswith('T') else 'False'
        return {
            'question_text': q_line,
            'question_type': 'TRUE_FALSE',
            'options_json': None,
            'correct_answer': correct,
        }

    # ── Multiple Choice ──
    if answer_letter and answer_letter in ('A', 'B', 'C', 'D') and options:
        options_list = []
        for l in ('A', 'B', 'C', 'D'):
            if l in options:
                options_list.append(options[l])
        if len(options_list) < 2:
            return None
        return {
            'question_text': q_line,
            'question_type': 'MULTIPLE_CHOICE',
            'options_json': options_list,
            'correct_answer': answer_letter,
        }

    return None
