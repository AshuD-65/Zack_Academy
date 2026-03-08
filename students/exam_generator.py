"""
Automatic exam question generator.
Generates questions from course materials automatically.
"""

import random
import re
from typing import List, Dict
from collections import defaultdict
from .models import Exam, ExamQuestion, CourseMaterial


class ExamQuestionGenerator:
    """Generates exam questions automatically from course materials."""

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
        material_questions = cls._generate_from_materials(materials, num_questions // 2)
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
        """Generate questions based on course materials."""
        questions = []

        for material in materials:
            if len(questions) >= count:
                break

            # Generate question based on material title and type
            title = getattr(material, 'title', 'Untitled')

            # Multiple choice question
            if len(questions) < count:
                questions.append({
                    'question': f'What topic is covered in "{title}"?',
                    'type': 'MULTIPLE_CHOICE',
                    'options': [
                        title.split()[0] if title.split() else 'Topic A',
                        'Unrelated Topic B',
                        'Unrelated Topic C',
                        'Unrelated Topic D'
                    ],
                    'answer': 'A',
                    'material': material
                })

            # True/False question
            if len(questions) < count:
                questions.append({
                    'question': f'The course material "{title}" is relevant to this course.',
                    'type': 'TRUE_FALSE',
                    'options': ['True', 'False'],
                    'answer': 'True',
                    'material': material
                })

        return questions

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
            title = getattr(mat, 'title', 'Untitled')

            # choose a template and format it
            tpl = random.choice(templates)
            q_text = tpl.replace('{topic}', title).replace('{statement}', title)

            # Create either multiple choice or true/false variant
            if random.random() < 0.7:
                # multiple choice: create options by slicing title words and adding distractors
                words = title.split()
                correct = words[0] if words else 'Topic A'
                options = [correct, 'Distractor B', 'Distractor C', 'Distractor D']
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
