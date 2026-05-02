"""
Automatic exam question generator.
Generates questions from course materials automatically.
"""

import io
import os
import random
import re
import shutil
import subprocess
import tempfile
from typing import List, Dict, Optional
from collections import defaultdict
from django.core.files.storage import default_storage

from .models import Exam, ExamQuestion, CourseMaterial

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


class ExamQuestionGenerator:
    """Generates exam questions automatically from course materials."""
    MAX_TEXT_EXTRACT_SIZE = 8 * 1024 * 1024  # 8MB safety limit
    OFFICE_DOCUMENT_EXTENSIONS = (".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls")

    # Sample question templates for different topics
    QUESTION_TEMPLATES = {
        'definition': [
            "What is {topic}?",
            "Define {topic}.",
            "Which of the following best describes {topic}?",
        ],
        'purpose': [
            "What is the main purpose of {topic}?",
            "Why is {topic} important?",
            "What problem does {topic} solve?",
        ],
        'application': [
            "When should you use {topic}?",
            "In which scenario is {topic} most appropriate?",
            "What is a common use case for {topic}?",
        ],
        'comparison': [
            "What is the difference between {topic1} and {topic2}?",
            "How does {topic1} compare to {topic2}?",
            "Which statement correctly compares {topic1} and {topic2}?",
        ],
        'true_false': [
            "{statement} is always true.",
            "{statement} is a correct statement.",
            "{topic} can be used for {purpose}.",
        ]
    }

    # Generic knowledge-based questions for different subjects
    GENERIC_QUESTIONS = {
        'programming': [
            {
                'question': 'What is the primary purpose of version control systems?',
                'type': 'MULTIPLE_CHOICE',
                'options': ['Track code changes', 'Compile code', 'Debug programs', 'Write documentation'],
                'answer': 'A'
            },
            {
                'question': 'Object-oriented programming is based on the concept of objects and classes.',
                'type': 'TRUE_FALSE',
                'options': ['True', 'False'],
                'answer': 'True'
            },
            {
                'question': 'Which principle states that a class should have only one reason to change?',
                'type': 'MULTIPLE_CHOICE',
                'options': ['Single Responsibility', 'Open/Closed', 'Liskov Substitution', 'Dependency Inversion'],
                'answer': 'A'
            },
        ],
        'data_science': [
            {
                'question': 'What is the main purpose of data preprocessing?',
                'type': 'MULTIPLE_CHOICE',
                'options': ['Clean and prepare data', 'Visualize results', 'Deploy models', 'Write reports'],
                'answer': 'A'
            },
            {
                'question': 'Machine learning algorithms can learn from data without being explicitly programmed.',
                'type': 'TRUE_FALSE',
                'options': ['True', 'False'],
                'answer': 'True'
            },
        ],
        'general': [
            {
                'question': 'What is the most important factor in successful project completion?',
                'type': 'MULTIPLE_CHOICE',
                'options': ['Clear communication', 'Advanced tools', 'Large budget', 'Long timeline'],
                'answer': 'A'
            },
            {
                'question': 'Documentation is an essential part of any professional project.',
                'type': 'TRUE_FALSE',
                'options': ['True', 'False'],
                'answer': 'True'
            },
            {
                'question': 'Which approach is best for learning new concepts?',
                'type': 'MULTIPLE_CHOICE',
                'options': ['Practice and application', 'Memorization only', 'Watching videos only', 'Reading once'],
                'answer': 'A'
            },
        ]
    }

    @classmethod
    def generate_questions_for_exam(cls, exam: Exam) -> List[ExamQuestion]:
        """
        Generate questions for an exam based on course materials.
        Returns list of created ExamQuestion objects.
        """
        course = exam.course
        materials = CourseMaterial.objects.filter(
            course=course,
        ).prefetch_related('files').order_by('order', 'created_at')

        # Delete existing questions
        ExamQuestion.objects.filter(exam=exam).delete()

        questions = []
        num_questions = getattr(exam, 'num_questions', 10)

        # Determine course category for better question selection
        course_category = cls._categorize_course(course)

        # Generate questions from materials
        material_questions = cls._generate_from_materials(course, materials, num_questions)
        questions.extend(material_questions)

        # Fill remaining with generic questions
        remaining = num_questions - len(questions)
        if remaining > 0:
            generic_questions = cls._generate_generic_questions(course_category, remaining)
            questions.extend(generic_questions)

        # If still short, synthesize additional variants from materials
        remaining = num_questions - len(questions)
        if remaining > 0:
            synth = cls._synthesize_additional_questions(course, materials, remaining)
            questions.extend(synth)

        # Reduce near-duplicates by limiting variants per base question
        def normalize_text(t: str) -> str:
            return t.lower().strip()

        def base_key_text(t: str) -> str:
            # remove variant suffix like "(variant 1)"
            s = re.sub(r"\s*\(variant\s+\d+\)\s*$", "", t, flags=re.IGNORECASE)
            return normalize_text(s)

        base_counts = defaultdict(int)
        max_variants_per_base = 1  # allow only one variant per base unless insufficient
        unique_texts = set()
        final_questions: List[Dict] = []

        # First pass: pick one question per unique base
        for q in questions:
            if len(final_questions) >= num_questions:
                break
            b = base_key_text(q['question'])
            if base_counts[b] == 0:
                t = normalize_text(q['question'])
                if t not in unique_texts:
                    unique_texts.add(t)
                    final_questions.append(q)
                    base_counts[b] += 1

        # Second pass: allow additional variants up to max_variants_per_base for bases
        if len(final_questions) < num_questions:
            for q in questions:
                if len(final_questions) >= num_questions:
                    break
                b = base_key_text(q['question'])
                if base_counts[b] < max_variants_per_base:
                    t = normalize_text(q['question'])
                    if t not in unique_texts:
                        unique_texts.add(t)
                        final_questions.append(q)
                        base_counts[b] += 1

        # Third pass: synthesize additional distinct questions from materials
        if len(final_questions) < num_questions:
            need = num_questions - len(final_questions)
            synth_more = cls._synthesize_additional_questions(course, materials, need * 2)
            for q in synth_more:
                if len(final_questions) >= num_questions:
                    break
                b = base_key_text(q['question'])
                t = normalize_text(q['question'])
                if t not in unique_texts and base_counts[b] < max_variants_per_base + 2:
                    unique_texts.add(t)
                    final_questions.append(q)
                    base_counts[b] += 1

        # Last resort: if still short, allow variants of existing bases (add variant suffixes)
        if len(final_questions) < num_questions:
            idx = 1
            i = 0
            while len(final_questions) < num_questions and i < len(final_questions) * 10:
                source = final_questions[i % len(final_questions)]
                variant = source.copy()
                variant['question'] = f"{variant['question']} (auto-variant {idx})"
                t = normalize_text(variant['question'])
                if t not in unique_texts:
                    unique_texts.add(t)
                    final_questions.append(variant)
                    idx += 1
                i += 1

        final_trimmed = final_questions[:num_questions]

        # Create ExamQuestion objects
        created_questions = []
        for idx, q_data in enumerate(final_trimmed, start=1):
            question = ExamQuestion.objects.create(
                exam=exam,
                question_text=q_data['question'],
                question_type=q_data['type'],
                options_json=q_data.get('options'),
                correct_answer=q_data['answer'],
                order=idx,
                points=1,
                source_material=q_data.get('material')
            )
            created_questions.append(question)

        return created_questions

    @classmethod
    def _categorize_course(cls, course) -> str:
        """Categorize course based on name/code for better question selection."""
        course_text = f"{getattr(course, 'course_code', '')} {getattr(course, 'course_name', '')}".lower()

        if any(keyword in course_text for keyword in ['python', 'java', 'programming', 'code', 'software', 'dev']):
            return 'programming'
        elif any(keyword in course_text for keyword in ['data', 'science', 'analytics', 'machine', 'ai']):
            return 'data_science'
        else:
            return 'general'

    @classmethod
    def _generate_from_materials(cls, course, materials, count: int) -> List[Dict]:
        """Generate questions based on course material text content."""
        questions = []
        material_units = cls._collect_material_sentences(course, materials)
        if not material_units:
            return questions

        # Build a global keyword pool for better distractors in MCQ questions.
        global_keywords = cls._extract_keywords(" ".join(unit["sentence"] for unit in material_units))

        for unit in material_units:
            if len(questions) >= count:
                break

            mcq = cls._build_mcq_from_sentence(unit["sentence"], global_keywords, unit.get("section"))
            if mcq:
                mcq['material'] = unit["material"]
                questions.append(mcq)

        return questions

    @classmethod
    def _collect_material_sentences(cls, course, materials) -> List[Dict]:
        """Extract normalized section-aware statements from course content."""
        collected: List[Dict] = []
        seen = set()
        course_main_file = getattr(course, "main_file", None)
        if course_main_file and getattr(course_main_file, "name", None):
            main_text = cls._extract_text_from_file(course_main_file.name, course_main_file.name.lower())
            for section, sentence in cls._extract_content_units(main_text, "Main Course File"):
                normalized = sentence.lower().strip()
                if len(sentence) < 25 or normalized in seen:
                    continue
                seen.add(normalized)
                collected.append({"material": None, "section": section, "sentence": sentence})

        for material in materials:
            text = cls._extract_material_text(material)
            default_section = getattr(material, "title", "") or "Course Material"
            for section, sentence in cls._extract_content_units(text, default_section):
                normalized = sentence.lower().strip()
                if len(sentence) < 25 or normalized in seen:
                    continue
                seen.add(normalized)
                collected.append({"material": material, "section": section, "sentence": sentence})
        return collected

    @classmethod
    def _extract_material_text(cls, material) -> str:
        """Extract raw text from metadata and supported file types."""
        parts = []
        title = getattr(material, "title", "") or ""
        if title:
            parts.append(title)

        description = getattr(material, "description", "") or ""
        if description:
            parts.append(description)

        file_field = getattr(material, "file", None)
        if file_field and getattr(file_field, "name", None):
            file_name = file_field.name.lower()
            extracted = cls._extract_text_from_file(file_field.name, file_name)
            if extracted:
                parts.append(extracted)

        for attachment in material.files.all():
            attachment_title = getattr(attachment, "title", "") or ""
            attachment_description = getattr(attachment, "description", "") or ""
            if attachment_title:
                parts.append(attachment_title)
            if attachment_description:
                parts.append(attachment_description)

            attachment_file = getattr(attachment, "file", None)
            if attachment_file and getattr(attachment_file, "name", None):
                extracted = cls._extract_text_from_file(attachment_file.name, attachment_file.name.lower())
                if extracted:
                    parts.append(extracted)

        return "\n".join(parts).strip()

    @classmethod
    def _extract_text_from_file(cls, storage_path: str, file_name: str) -> str:
        """Extract text from supported file formats stored in Django storage."""
        is_pdf = file_name.endswith(".pdf")
        is_text_like = file_name.endswith((".txt", ".md", ".csv", ".json", ".xml", ".html"))
        is_office_doc = file_name.endswith(cls.OFFICE_DOCUMENT_EXTENSIONS)
        if not (is_pdf or is_text_like or is_office_doc):
            # Skip binary/unsupported files (video/audio/images/docs) for stability.
            return ""

        try:
            file_size = default_storage.size(storage_path)
            if file_size and file_size > cls.MAX_TEXT_EXTRACT_SIZE:
                # Avoid loading very large files in request cycle.
                return ""
        except Exception:
            pass

        try:
            with default_storage.open(storage_path, "rb") as fh:
                raw = fh.read()
        except Exception:
            return ""

        if is_office_doc:
            return cls._extract_text_from_office_bytes(raw, file_name)

        # PDF parsing (best-effort).
        if is_pdf and PdfReader:
            try:
                reader = PdfReader(io.BytesIO(raw))
                pages = []
                for page in reader.pages[:30]:
                    txt = page.extract_text() or ""
                    if txt.strip():
                        pages.append(txt)
                return "\n\n".join(pages).strip()
            except Exception:
                return ""

        # Plain-text style files.
        if is_text_like:
            for enc in ("utf-8", "latin-1"):
                try:
                    return raw.decode(enc, errors="ignore")
                except Exception:
                    continue
        return ""

    @classmethod
    def _extract_text_from_office_bytes(cls, raw: bytes, file_name: str) -> str:
        soffice_path = shutil.which("soffice")
        if not soffice_path or not PdfReader:
            return ""

        suffix = os.path.splitext(file_name)[1].lower()
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = os.path.join(temp_dir, f"source{suffix}")
            pdf_path = os.path.join(temp_dir, "source.pdf")

            try:
                with open(source_path, "wb") as fh:
                    fh.write(raw)
            except OSError:
                return ""

            result = subprocess.run(
                [
                    soffice_path,
                    "--headless",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    temp_dir,
                    source_path,
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0 or not os.path.exists(pdf_path):
                return ""

            try:
                reader = PdfReader(pdf_path)
                pages = []
                for page in reader.pages[:30]:
                    txt = page.extract_text() or ""
                    if txt.strip():
                        pages.append(txt)
                return "\n\n".join(pages).strip()
            except Exception:
                return ""

    @classmethod
    def _extract_content_units(cls, text: str, default_section: str) -> List[tuple[str, str]]:
        if not text:
            return []

        raw_text = text.replace("\r", "\n").replace("\f", "\n\n")
        blocks = [block.strip() for block in re.split(r"\n{2,}", raw_text) if block.strip()]
        units: List[tuple[str, str]] = []

        for block in blocks:
            lines = [re.sub(r"\s+", " ", line).strip(" -\t") for line in block.splitlines()]
            lines = [line for line in lines if line]
            if not lines:
                continue

            section = default_section
            content_lines = lines
            first_line = lines[0]
            if cls._looks_like_heading(first_line):
                section = first_line
                content_lines = lines[1:] or lines[:1]

            line_candidates = content_lines if content_lines else [block]
            for candidate in line_candidates:
                for sentence in cls._split_sentences(candidate):
                    units.append((section, sentence))

        if not units:
            for sentence in cls._split_sentences(text):
                units.append((default_section, sentence))
        return units

    @classmethod
    def _looks_like_heading(cls, text: str) -> bool:
        words = text.split()
        if not words or len(words) > 12 or len(text) > 90:
            return False
        if re.fullmatch(r"[\W\d_]+", text.strip()):
            return False
        if cls._is_weak_section_label(text):
            return False
        if text.endswith((".", "?", "!")):
            return False
        uppercase_ratio = sum(1 for ch in text if ch.isupper()) / max(1, sum(1 for ch in text if ch.isalpha()))
        return uppercase_ratio > 0.2 or all(word[:1].isupper() for word in words if word[:1].isalpha())

    @classmethod
    def _split_sentences(cls, text: str) -> List[str]:
        if not text:
            return []
        raw_text = text.replace("\r", "\n")
        block_candidates = re.split(r"\n+|[•●▪◦▪]+", raw_text)
        candidates: List[str] = []

        for block in block_candidates:
            block = block.strip()
            if not block:
                continue

            block = re.sub(r"\s+", " ", block).strip()
            for sentence in re.split(r"(?<=[.!?])\s+|;\s+|\s+-\s+", block):
                sentence = re.sub(r"^\d+[\).:-]?\s*", "", sentence).strip(" -\n\r\t")
                sentence = re.sub(r"\s+", " ", sentence).strip()
                if not sentence:
                    continue

                if len(sentence) > 220:
                    sub_parts = re.split(r",\s+|:\s+", sentence)
                    for sub in sub_parts:
                        sub = sub.strip()
                        if len(sub) >= 25:
                            candidates.append(sub)
                else:
                    candidates.append(sentence)

        unique = []
        seen = set()
        for candidate in candidates:
            normalized = candidate.lower().strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            unique.append(candidate)
        return unique

    @classmethod
    def _extract_keywords(cls, text: str) -> List[str]:
        words = re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", (text or "").lower())
        stop = {
            "this", "that", "with", "from", "have", "will", "your", "their", "about", "into",
            "there", "which", "when", "where", "while", "what", "course", "material", "using",
            "used", "should", "could", "would", "were", "been", "being", "also", "only",
        }
        filtered = [w for w in words if w not in stop]
        # Preserve order while de-duplicating.
        seen = set()
        unique = []
        for w in filtered:
            if w in seen:
                continue
            seen.add(w)
            unique.append(w)
        return unique

    @classmethod
    def _build_mcq_from_sentence(cls, sentence: str, keyword_pool: List[str], section: Optional[str] = None) -> Optional[Dict]:
        """Create one MCQ with a more natural question style from the material sentence."""
        keywords = cls._extract_keywords(sentence)
        if not keywords:
            return None

        option_variants = [sentence.strip()]
        distractor_pool = [w for w in keyword_pool if w.lower() not in {k.lower() for k in keywords}]

        for keyword in sorted(keywords, key=len, reverse=True):
            replacement = next((w for w in distractor_pool if w.lower() != keyword.lower()), None)
            if not replacement:
                continue

            variant = re.sub(
                rf"\b{re.escape(keyword)}\b",
                replacement,
                sentence,
                count=1,
                flags=re.IGNORECASE,
            ).strip()
            if variant != sentence and variant not in option_variants:
                option_variants.append(variant)

            if len(option_variants) >= 4:
                break

        if len(option_variants) < 2:
            return None

        fallback_variants = [
            f"{sentence.strip()} This statement is incorrect.",
            f"{sentence.strip()} This applies in every situation without exception.",
            f"{sentence.strip()} This statement is unrelated to the lesson.",
        ]
        for fallback in fallback_variants:
            if fallback not in option_variants:
                option_variants.append(fallback)
            if len(option_variants) >= 4:
                break

        options = option_variants[:4]
        random.shuffle(options)
        correct_index = options.index(sentence.strip())
        correct_letter = chr(ord("A") + correct_index)
        section = (section or "").strip()
        question_text = cls._build_question_prompt(sentence.strip(), section)

        return {
            "question": question_text,
            "type": "MULTIPLE_CHOICE",
            "options": options,
            "answer": correct_letter,
        }

    @classmethod
    def _build_question_prompt(cls, sentence: str, section: Optional[str] = None) -> str:
        sentence = sentence.strip()
        section = (section or "").strip()
        lowered = sentence.lower()
        topic = cls._derive_topic_from_sentence(sentence)
        section_topic = cls._clean_prompt_topic(section)
        concept = topic or section_topic

        if any(lowered.startswith(prefix) for prefix in ("what is ", "what are ", "define ")):
            if concept:
                return f"Which answer best defines {concept}?"
            return "Which answer best defines the concept described in the lesson?"

        if lowered.startswith(("confidentiality ", "integrity ", "availability ", "authentication ", "authorization ")):
            topic = sentence.split()[0].strip(":,.")
            return f"Which statement best describes {topic}?"

        if " is " in lowered:
            subject = cls._clean_prompt_topic(sentence.split(" is ", 1)[0].strip(" :,."))
            if 2 <= len(subject.split()) <= 8:
                return f"Which statement best describes {subject}?"

        if " means " in lowered:
            subject = cls._clean_prompt_topic(sentence.split(" means ", 1)[0].strip(" :,."))
            if 1 <= len(subject.split()) <= 8:
                return f"What does {subject} mean?"

        if " refers to " in lowered:
            subject = cls._clean_prompt_topic(sentence.split(" refers to ", 1)[0].strip(" :,."))
            if 1 <= len(subject.split()) <= 8:
                return f"What does {subject} refer to?"

        if " used " in lowered or " use " in lowered:
            if topic:
                return f"How is {topic} used?"
            if section_topic:
                return f"How is {section_topic} used?"
            return "How is this concept applied?"

        if " purpose " in lowered or lowered.startswith("the purpose"):
            if topic:
                return f"What is the purpose of {topic}?"
            if section_topic:
                return f"What is the purpose of {section_topic}?"
            return "What is the purpose of this concept?"

        if cls._is_definition_like_sentence(sentence) and concept:
            return f"Which statement best describes {concept}?"
        if cls._is_function_like_sentence(sentence) and concept:
            return f"What is the main purpose of {concept}?"
        if cls._is_feature_like_sentence(sentence) and concept:
            return f"Which feature best matches {concept}?"
        if concept:
            prompt_templates = [
                "Which statement best describes {topic}?",
                "What is the main idea of {topic}?",
                "Which option best explains {topic}?",
                "Which statement about {topic} is accurate?",
            ]
            return random.choice(prompt_templates).format(topic=concept)
        return "Which option is most consistent with the lesson content?"

    @classmethod
    def _clean_prompt_topic(cls, text: str) -> str:
        text = (text or "").strip(" :,.")
        if not text:
            return ""
        lowered = text.lower()
        if cls._is_weak_section_label(text):
            return ""
        if re.fullmatch(r"(chapter|week|section|slide|lesson|topic|unit)\s*[:\-]?\s*[ivx\d]+", lowered):
            return ""
        return text

    @classmethod
    def _derive_topic_from_sentence(cls, sentence: str) -> str:
        sentence = sentence.strip()
        patterns = [
            r"^([A-Za-z][A-Za-z0-9\s/_-]{2,60}?)\s+is\s+",
            r"^([A-Za-z][A-Za-z0-9\s/_-]{2,60}?)\s+refers to\s+",
            r"^([A-Za-z][A-Za-z0-9\s/_-]{2,60}?)\s+means\s+",
            r"^([A-Za-z][A-Za-z0-9\s/_-]{2,60}?)\s+describes\s+",
        ]
        for pattern in patterns:
            match = re.match(pattern, sentence, flags=re.IGNORECASE)
            if match:
                topic = cls._clean_prompt_topic(match.group(1))
                if topic:
                    return topic

        phrase = cls._topic_phrase_from_sentence(sentence)
        if phrase:
            return phrase

        keywords = cls._extract_keywords(sentence)
        if not keywords:
            return ""

        chosen = []
        for keyword in keywords[:5]:
            if keyword.isdigit() or len(keyword) < 4:
                continue
            chosen.append(keyword)
        return " ".join(chosen[:3]).strip()

    @classmethod
    def _is_weak_section_label(cls, text: str) -> bool:
        lowered = (text or "").strip().lower()
        if not lowered:
            return True
        if lowered in {"course material", "main course file", "overview", "introduction"}:
            return True
        if re.fullmatch(r"[\d\W_]+", lowered):
            return True
        if re.fullmatch(r"(week|chapter|section|slide|lesson|topic|unit)\s*[:\-]?\s*[ivx\d\w]+", lowered):
            return True
        if re.fullmatch(r"(page|part)\s+\d+", lowered):
            return True
        words = lowered.split()
        if len(words) <= 3 and all(word.isdigit() for word in words):
            return True
        if len(words) <= 3 and any(word.isdigit() for word in words):
            return True
        return False

    @classmethod
    def _topic_phrase_from_sentence(cls, sentence: str) -> str:
        cleaned = re.sub(r"^\d+[\).:-]?\s*", "", sentence).strip()
        cleaned = re.sub(r"\([^)]*\)", "", cleaned)
        lead_ins = [
            "in general",
            "for example",
            "for instance",
            "according to the lesson",
            "according to the material",
            "this means",
            "this implies",
        ]
        lowered = cleaned.lower()
        for lead_in in lead_ins:
            if lowered.startswith(lead_in):
                cleaned = cleaned[len(lead_in):].lstrip(" ,:-")
                lowered = cleaned.lower()

        segments = re.split(
            r"\b(?: is | are | means | refers to | helps | allows | ensures | protects | keeps | uses | includes | involves | provides | supports )\b",
            cleaned,
            maxsplit=1,
            flags=re.IGNORECASE,
        )
        candidate = segments[0].strip(" :,-") if segments else cleaned
        candidate_words = [word for word in candidate.split() if re.search(r"[A-Za-z]", word)]
        if 1 <= len(candidate_words) <= 8:
            topic = cls._clean_prompt_topic(" ".join(candidate_words))
            if topic:
                return topic

        meaningful = [
            word for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]*", cleaned)
            if len(word) > 3 and word.lower() not in {"this", "that", "these", "those", "which", "their", "there", "general"}
        ]
        if meaningful:
            return cls._clean_prompt_topic(" ".join(meaningful[:3]))
        return ""

    @classmethod
    def _is_definition_like_sentence(cls, sentence: str) -> bool:
        lowered = sentence.lower()
        return any(token in lowered for token in (" is ", " are ", " refers to ", " means "))

    @classmethod
    def _is_function_like_sentence(cls, sentence: str) -> bool:
        lowered = sentence.lower()
        return any(token in lowered for token in (" purpose ", " used ", " use ", " helps ", " allows ", " enables ", " supports "))

    @classmethod
    def _is_feature_like_sentence(cls, sentence: str) -> bool:
        lowered = sentence.lower()
        return any(token in lowered for token in (" includes ", " consists of ", " contains ", " has ", " involves "))

    @classmethod
    def _generate_generic_questions(cls, category: str, count: int) -> List[Dict]:
        """Generate generic questions for the course category."""
        questions = []

        # Get questions for category
        category_questions = cls.GENERIC_QUESTIONS.get(category, cls.GENERIC_QUESTIONS['general'])

        # If the available pool is large enough, sample without replacement.
        # Otherwise, sample with replacement to reach the requested count.
        pool = list(category_questions)
        if len(pool) >= count:
            selected = random.sample(pool, count)
        else:
            # allow repeats when needed
            selected = random.choices(pool, k=count)

        for q in selected:
            q_type = q['type']
            options = q.get('options')
            answer = q['answer']
            question_text = q['question']

            if q_type == 'TRUE_FALSE':
                question_text = 'According to the course material, which statement is correct?'
                options = [q['question'], f"It is false that {q['question'].rstrip('.')}"]
                options.extend([
                    f"{q['question'].rstrip('.')} in every situation.",
                    f"{q['question'].rstrip('.')} only in unrelated topics.",
                ])
                answer = 'A'

            questions.append({
                'question': question_text,
                'type': 'MULTIPLE_CHOICE',
                'options': options,
                'answer': answer,
                'material': None
            })

        # If still short (shouldn't happen), fill with general pool with replacement
        if len(questions) < count:
            general_pool = cls.GENERIC_QUESTIONS['general']
            to_add = count - len(questions)
            add_selected = random.choices(general_pool, k=to_add)
            for q in add_selected:
                q_type = q['type']
                options = q.get('options')
                answer = q['answer']
                question_text = q['question']

                if q_type == 'TRUE_FALSE':
                    question_text = 'According to the course material, which statement is correct?'
                    options = [q['question'], f"It is false that {q['question'].rstrip('.')}"]
                    options.extend([
                        f"{q['question'].rstrip('.')} in every situation.",
                        f"{q['question'].rstrip('.')} only in unrelated topics.",
                    ])
                    answer = 'A'

                questions.append({
                    'question': question_text,
                    'type': 'MULTIPLE_CHOICE',
                    'options': options,
                    'answer': answer,
                    'material': None
                })

        return questions

    @classmethod
    def _synthesize_additional_questions(cls, course, materials, needed: int) -> List[Dict]:
        """Create additional distinct MCQs from unused material sentences before falling back further."""
        questions = []
        if not materials:
            return questions
        material_units = cls._collect_material_sentences(course, materials)
        random.shuffle(material_units)
        global_keywords = cls._extract_keywords(" ".join(unit["sentence"] for unit in material_units))

        for unit in material_units:
            if len(questions) >= needed:
                break
            mcq = cls._build_mcq_from_sentence(unit["sentence"], global_keywords, unit.get("section"))
            if mcq:
                mcq['material'] = unit["material"]
                questions.append(mcq)

        return questions


def regenerate_exam_questions(exam: Exam) -> int:
    """
    Regenerate all questions for an exam.
    Returns the number of questions created.
    """
    questions = ExamQuestionGenerator.generate_questions_for_exam(exam)
    return len(questions)
