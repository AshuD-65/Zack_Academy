"""
Automatic exam question generator.
Generates questions from course materials automatically.
"""

import io
import random
import re
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
            is_visible=True
        ).order_by('order')

        # Delete existing questions
        ExamQuestion.objects.filter(exam=exam).delete()

        questions = []
        num_questions = getattr(exam, 'num_questions', 10)

        # Determine course category for better question selection
        course_category = cls._categorize_course(course)

        # Generate questions from materials
        material_questions = cls._generate_from_materials(materials, num_questions)
        questions.extend(material_questions)

        # Fill remaining with generic questions
        remaining = num_questions - len(questions)
        if remaining > 0:
            generic_questions = cls._generate_generic_questions(course_category, remaining)
            questions.extend(generic_questions)

        # If still short, synthesize additional variants from materials
        remaining = num_questions - len(questions)
        if remaining > 0:
            synth = cls._synthesize_additional_questions(materials, remaining)
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
            synth_more = cls._synthesize_additional_questions(materials, need * 2)
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
    def _generate_from_materials(cls, materials, count: int) -> List[Dict]:
        """Generate questions based on course material text content."""
        questions = []
        material_sentences = cls._collect_material_sentences(materials)
        if not material_sentences:
            return questions

        # Build a global keyword pool for better distractors in MCQ questions.
        global_keywords = cls._extract_keywords(" ".join(s for _, s in material_sentences))

        for material, sentence in material_sentences:
            if len(questions) >= count:
                break

            # True/False from direct statement in the material.
            questions.append({
                'question': sentence,
                'type': 'TRUE_FALSE',
                'options': ['True', 'False'],
                'answer': 'True',
                'material': material
            })

            if len(questions) >= count:
                break

            mcq = cls._build_mcq_from_sentence(sentence, global_keywords)
            if mcq:
                mcq['material'] = material
                questions.append(mcq)

        return questions

    @classmethod
    def _collect_material_sentences(cls, materials) -> List[tuple]:
        """Extract normalized sentences from material title/description/files."""
        collected = []
        for material in materials:
            text = cls._extract_material_text(material)
            for sentence in cls._split_sentences(text):
                # Keep only meaningful content sentences.
                if len(sentence) < 35:
                    continue
                collected.append((material, sentence))
        return collected

    @classmethod
    def _extract_material_text(cls, material) -> str:
        """Extract raw text from metadata and supported file types."""
        parts = []
        description = getattr(material, "description", "") or ""
        if description:
            parts.append(description)

        file_field = getattr(material, "file", None)
        if file_field and getattr(file_field, "name", None):
            file_name = file_field.name.lower()
            extracted = cls._extract_text_from_file(file_field.name, file_name)
            if extracted:
                parts.append(extracted)

        return "\n".join(parts).strip()

    @classmethod
    def _extract_text_from_file(cls, storage_path: str, file_name: str) -> str:
        """Extract text from supported file formats stored in Django storage."""
        is_pdf = file_name.endswith(".pdf")
        is_text_like = file_name.endswith((".txt", ".md", ".csv", ".json", ".xml", ".html"))
        if not (is_pdf or is_text_like):
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

        # PDF parsing (best-effort).
        if is_pdf and PdfReader:
            try:
                reader = PdfReader(io.BytesIO(raw))
                pages = []
                for page in reader.pages[:30]:
                    txt = page.extract_text() or ""
                    if txt.strip():
                        pages.append(txt)
                return "\n".join(pages).strip()
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
    def _split_sentences(cls, text: str) -> List[str]:
        if not text:
            return []
        normalized = re.sub(r"\s+", " ", text).strip()
        if not normalized:
            return []
        candidates = re.split(r"(?<=[.!?])\s+", normalized)
        return [c.strip(" -\n\r\t") for c in candidates if c and c.strip()]

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
    def _build_mcq_from_sentence(cls, sentence: str, keyword_pool: List[str]) -> Optional[Dict]:
        """Create one MCQ by masking a key term from a sentence."""
        keywords = cls._extract_keywords(sentence)
        if not keywords:
            return None

        correct = max(keywords, key=len)
        masked_sentence = re.sub(
            rf"\b{re.escape(correct)}\b",
            "______",
            sentence,
            count=1,
            flags=re.IGNORECASE,
        )
        if "______" not in masked_sentence:
            return None

        distractors = [w for w in keyword_pool if w != correct]
        random.shuffle(distractors)
        options = [correct] + distractors[:3]

        # Ensure 4 options, even with sparse material text.
        while len(options) < 4:
            options.append(f"option_{len(options)+1}")

        random.shuffle(options)
        correct_index = options.index(correct)
        correct_letter = chr(ord("A") + correct_index)

        return {
            "question": f'According to the course material, which word best completes: "{masked_sentence}"',
            "type": "MULTIPLE_CHOICE",
            "options": options,
            "answer": correct_letter,
        }

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
            questions.append({
                'question': q['question'],
                'type': q['type'],
                'options': q.get('options'),
                'answer': q['answer'],
                'material': None
            })

        # If still short (shouldn't happen), fill with general pool with replacement
        if len(questions) < count:
            general_pool = cls.GENERIC_QUESTIONS['general']
            to_add = count - len(questions)
            add_selected = random.choices(general_pool, k=to_add)
            for q in add_selected:
                questions.append({
                    'question': q['question'],
                    'type': q['type'],
                    'options': q.get('options'),
                    'answer': q['answer'],
                    'material': None
                })

        return questions

    @classmethod
    def _synthesize_additional_questions(cls, materials, needed: int) -> List[Dict]:
        """Create additional question variants from available materials to reach needed count.

        This makes simple templated variations (using templates in QUESTION_TEMPLATES)
        and generates slightly different options so the generator can reach high
        requested counts even if the base pools are small.
        """
        questions = []
        if not materials:
            return questions

        templates = []
        for k, v in cls.QUESTION_TEMPLATES.items():
            templates.extend(v)

        mat_cycle = list(materials)
        idx = 0
        attempt = 0
        while len(questions) < needed and attempt < needed * 5:
            mat = mat_cycle[idx % len(mat_cycle)]
            source_text = cls._extract_material_text(mat)
            base_terms = cls._extract_keywords(source_text)
            topic = max(base_terms, key=len) if base_terms else "the lesson content"
            topic2 = base_terms[1] if len(base_terms) > 1 else "related concepts"
            purpose = base_terms[2] if len(base_terms) > 2 else "practical learning"

            # choose a template and format it
            tpl = random.choice(templates)
            q_text = (
                tpl.replace('{topic}', topic)
                .replace('{topic1}', topic)
                .replace('{topic2}', topic2)
                .replace('{purpose}', purpose)
                .replace('{statement}', topic)
            )

            # Create either multiple choice or true/false variant
            if random.random() < 0.7:
                # multiple choice: create options by slicing title words and adding distractors
                pool = cls._extract_keywords(source_text)
                correct = max(pool, key=len) if pool else 'Concept A'
                distractor_pool = [w for w in pool if w != correct]
                random.shuffle(distractor_pool)
                options = [correct] + distractor_pool[:3]
                while len(options) < 4:
                    options.append(f"Distractor {len(options)}")
                q = {'question': q_text, 'type': 'MULTIPLE_CHOICE', 'options': options, 'answer': 'A', 'material': mat}
            else:
                q = {'question': q_text, 'type': 'TRUE_FALSE', 'options': ['True', 'False'], 'answer': 'True', 'material': mat}

            # Add a small variant suffix when duplicates may occur
            variant_num = (idx // len(mat_cycle)) + 1
            if variant_num > 1:
                q['question'] = f"{q['question']} (variant {variant_num})"

            questions.append(q)
            idx += 1
            attempt += 1

        return questions


def regenerate_exam_questions(exam: Exam) -> int:
    """
    Regenerate all questions for an exam.
    Returns the number of questions created.
    """
    questions = ExamQuestionGenerator.generate_questions_for_exam(exam)
    return len(questions)
