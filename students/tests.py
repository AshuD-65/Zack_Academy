import json
import shutil
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .exam_generator import regenerate_exam_questions
from .forms import StudentProfileForm
from .models import Course, CourseMaterial, CourseMaterialFile, Exam, ExamAnswer, ExamQuestion, Student


class SecurityAndFlowRegressionTests(TestCase):
    def setUp(self):
        self.student = Student.objects.create(
            student_id='STU001',
            name='Test Student',
            email='student@example.com',
            password='hashed',
            date_of_birth=date(2000, 1, 1),
            major='CS',
        )
        self.course = Course.objects.create(
            course_code='CS101',
            course_name='Intro CS',
            credits=3,
            instructor='Teacher',
            price=Decimal('10.00'),
            is_approved=True,
            duration_weeks=8,
        )
        self.student.courses.add(self.course)
        session = self.client.session
        session['student_id'] = self.student.student_id
        session.save()

    def test_enroll_blocks_unapproved_course(self):
        hidden = Course.objects.create(
            course_code='HID001',
            course_name='Hidden Course',
            credits=3,
            instructor='Teacher',
            price=Decimal('10.00'),
            is_approved=False,
            duration_weeks=8,
        )
        response = self.client.post(reverse('enroll_course'), {'course_code': hidden.course_code})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.student.courses.filter(course_code=hidden.course_code).exists())

    def test_exam_resubmit_is_idempotent(self):
        exam = Exam.objects.create(course=self.course, is_released=True)
        q1 = ExamQuestion.objects.create(
            exam=exam,
            question_text='Q1',
            question_type=ExamQuestion.TYPE_TRUE_FALSE,
            correct_answer='true',
            order=1,
            points=1,
        )

        start = self.client.get(reverse('student_take_exam', kwargs={'course_code': self.course.course_code}))
        self.assertEqual(start.status_code, 200)
        attempt = start.context['attempt']

        payload = {
            'attempt_id': str(attempt.attempt_id),
            f'q_{q1.question_id}': 'true',
        }
        first = self.client.post(reverse('student_take_exam', kwargs={'course_code': self.course.course_code}), payload)
        self.assertEqual(first.status_code, 302)

        second = self.client.post(reverse('student_take_exam', kwargs={'course_code': self.course.course_code}), payload)
        self.assertEqual(second.status_code, 302)
        self.assertEqual(ExamAnswer.objects.filter(attempt=attempt, question=q1).count(), 1)

    @override_settings(STRIPE_SECRET_KEY=None)
    def test_missing_stripe_key_does_not_crash(self):
        response = self.client.post(
            reverse('payment_create_session'),
            {'course_code': self.course.course_code, 'amount_dollars': '10.00'},
        )
        self.assertEqual(response.status_code, 302)

    @override_settings(STRIPE_SECRET_KEY='sk_test_example')
    @patch('students.payment_views.stripe')
    def test_checkout_prefills_student_email_and_name(self, stripe_mock):
        stripe_mock.Customer.list.return_value = Mock(data=[])
        stripe_mock.Customer.create.return_value = {'id': 'cus_test_123'}
        stripe_mock.checkout.Session.create.return_value = Mock(url='https://checkout.stripe.test/session')

        response = self.client.post(
            reverse('payment_create_session'),
            {'course_code': self.course.course_code, 'amount_dollars': '10.00'},
        )

        self.assertEqual(response.status_code, 303)
        stripe_mock.Customer.create.assert_called_once_with(
            email=self.student.email,
            name=self.student.name,
            metadata={'student_id': self.student.student_id},
        )

        session_kwargs = stripe_mock.checkout.Session.create.call_args.kwargs
        self.assertEqual(session_kwargs['customer_email'], self.student.email)
        self.assertEqual(session_kwargs['customer'], 'cus_test_123')
        self.assertEqual(session_kwargs['payment_intent_data']['receipt_email'], self.student.email)
        self.assertEqual(session_kwargs['payment_intent_data']['metadata']['student_name'], self.student.name)

    def test_student_profile_form_allows_existing_image_without_reupload(self):
        image_file = SimpleUploadedFile(
            name='test_avatar.jpg',
            content=b'test-image-content',
            content_type='image/jpeg'
        )
        student_with_image = Student.objects.create(
            student_id='STU002',
            name='Image Student',
            email='image.student@example.com',
            password='hashed',
            date_of_birth=date(2000, 1, 2),
            major='Biology',
            profile_picture=image_file,
        )

        form = StudentProfileForm(
            data={
                'name': student_with_image.name,
                'email': student_with_image.email,
                'date_of_birth': student_with_image.date_of_birth,
                'major': student_with_image.major,
            },
            instance=student_with_image,
        )

        self.assertTrue(form.is_valid())

    def test_material_session_requires_csrf(self):
        csrf_client = Client(enforce_csrf_checks=True)
        session = csrf_client.session
        session['student_id'] = self.student.student_id
        session.save()
        material = CourseMaterial.objects.create(
            course=self.course,
            title='Lesson 1',
            material_type=CourseMaterial.MATERIAL_TYPE_PDF,
            kind=CourseMaterial.KIND_LESSON,
        )
        response = csrf_client.post(
            reverse('start_material_session'),
            data=json.dumps({'material_id': str(material.material_id), 'course_code': self.course.course_code}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 403)


class FilePathSecurityTests(TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix='media-test-')
        self.media_root = Path(self.tmpdir) / 'media'
        self.media_root.mkdir(parents=True, exist_ok=True)
        self.safe_file = self.media_root / 'safe.txt'
        self.safe_file.write_text('safe')
        self.secret_file = Path(self.tmpdir) / 'secret.txt'
        self.secret_file.write_text('secret')

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_path_traversal_is_blocked(self):
        with override_settings(MEDIA_ROOT=str(self.media_root)):
            response = self.client.get(reverse('serve_file', kwargs={'file_path': '../secret.txt'}))
            self.assertEqual(response.status_code, 404)

    def test_safe_file_is_served(self):
        with override_settings(MEDIA_ROOT=str(self.media_root)):
            response = self.client.get(reverse('serve_file', kwargs={'file_path': 'safe.txt'}))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, b'safe')


class ExamGenerationContentTests(TestCase):
    def test_exam_questions_include_material_content(self):
        course = Course.objects.create(
            course_code='ML100',
            course_name='Machine Learning Fundamentals',
            credits=3,
            instructor='Instructor',
            price=Decimal('2.00'),
            is_approved=True,
            duration_weeks=8,
        )
        material = CourseMaterial.objects.create(
            course=course,
            title='Intro to ML',
            description='Gradient descent minimizes the loss function by iteratively updating model parameters.',
            material_type=CourseMaterial.MATERIAL_TYPE_PDF,
            kind=CourseMaterial.KIND_LESSON,
            is_visible=True,
        )
        exam = Exam.objects.create(course=course, num_questions=4, is_released=False)
        regenerate_exam_questions(exam)
        questions = ExamQuestion.objects.filter(exam=exam)

        self.assertGreaterEqual(questions.count(), 1)
        self.assertTrue(questions.filter(source_material=material).exists())
        joined_text = " ".join(questions.values_list('question_text', flat=True)).lower()
        self.assertIn('gradient', joined_text)

    def test_multiple_choice_questions_use_statement_style_from_content(self):
        course = Course.objects.create(
            course_code='APP101',
            course_name='Application Security',
            credits=3,
            instructor='Instructor',
            price=Decimal('2.00'),
            is_approved=True,
            duration_weeks=8,
        )
        material = CourseMaterial.objects.create(
            course=course,
            title='Security basics',
            description='Encryption protects sensitive information by transforming readable data into unreadable ciphertext.',
            material_type=CourseMaterial.MATERIAL_TYPE_OTHER,
            kind=CourseMaterial.KIND_LESSON,
            is_visible=True,
        )
        exam = Exam.objects.create(course=course, num_questions=4, is_released=False)
        regenerate_exam_questions(exam)

        mcq = ExamQuestion.objects.filter(exam=exam, question_type=ExamQuestion.TYPE_MULTIPLE_CHOICE).first()
        self.assertIsNotNone(mcq)
        self.assertTrue(
            any(
                phrase in mcq.question_text.lower()
                for phrase in ['which statement best describes', 'what is correct about', 'which statement is correct']
            )
        )
        self.assertTrue(any('Encryption protects sensitive information' in option for option in (mcq.options_json or [])))
        self.assertFalse(ExamQuestion.objects.filter(exam=exam, question_type=ExamQuestion.TYPE_TRUE_FALSE).exists())

    def test_generated_questions_do_not_use_variant_suffixes(self):
        course = Course.objects.create(
            course_code='NET101',
            course_name='Network Security',
            credits=3,
            instructor='Instructor',
            price=Decimal('2.00'),
            is_approved=True,
            duration_weeks=8,
        )
        material = CourseMaterial.objects.create(
            course=course,
            title='Foundations',
            description=(
                'Confidentiality protects data from unauthorized disclosure. '
                'Integrity ensures data remains accurate and complete. '
                'Availability ensures systems and data remain accessible when needed. '
                'Authentication verifies the identity of users before granting access. '
                'Authorization determines what an authenticated user is allowed to do.'
            ),
            material_type=CourseMaterial.MATERIAL_TYPE_OTHER,
            kind=CourseMaterial.KIND_LESSON,
            is_visible=True,
        )
        exam = Exam.objects.create(course=course, num_questions=5, is_released=False)
        regenerate_exam_questions(exam)

        joined_text = " ".join(ExamQuestion.objects.filter(exam=exam).values_list('question_text', flat=True)).lower()
        self.assertNotIn('variant', joined_text)

    def test_generated_questions_can_vary_by_section_heading(self):
        course = Course.objects.create(
            course_code='SEC300',
            course_name='Security Concepts',
            credits=3,
            instructor='Instructor',
            price=Decimal('2.00'),
            is_approved=True,
            duration_weeks=8,
        )
        material = CourseMaterial.objects.create(
            course=course,
            title='Security Concepts',
            description=(
                'Confidentiality\n'
                'Protects information from unauthorized disclosure.\n\n'
                'Integrity\n'
                'Ensures information remains accurate and trustworthy.\n\n'
                'Availability\n'
                'Keeps systems and data accessible when needed.'
            ),
            material_type=CourseMaterial.MATERIAL_TYPE_OTHER,
            kind=CourseMaterial.KIND_LESSON,
            is_visible=True,
        )
        exam = Exam.objects.create(course=course, num_questions=3, is_released=False)
        regenerate_exam_questions(exam)

        question_texts = list(ExamQuestion.objects.filter(exam=exam).values_list('question_text', flat=True))
        joined = " ".join(question_texts)
        self.assertTrue(any(term in joined for term in ['Confidentiality', 'Integrity', 'Availability']))
        self.assertNotIn('What is correct about', joined)

    def test_question_prompt_ignores_weak_numeric_or_week_labels(self):
        prompt = ExamQuestionGenerator._build_question_prompt(
            'Categorical data is grouped into named classes for analysis.',
            '23',
        )
        self.assertNotIn('23', prompt)
        self.assertNotIn('What is correct about', prompt)

        week_prompt = ExamQuestionGenerator._build_question_prompt(
            'Accountability ensures that user actions can be traced to a responsible identity.',
            'week one',
        )
        self.assertNotIn('week one', week_prompt.lower())
        self.assertIn('accountability', week_prompt.lower())

    @patch('students.exam_generator.ExamQuestionGenerator._extract_text_from_file')
    def test_exam_questions_use_all_attached_course_content(self, extract_mock):
        extract_mock.side_effect = lambda storage_path, file_name: {
            'course_materials/main_files/main_overview.pptx': 'Main overview explains threat modeling and secure design principles in detail for the entire course.',
            'course_materials/SEC200/files/lesson_notes.txt': 'Attachment notes describe least privilege enforcement and system hardening across deployment environments.',
        }.get(storage_path, '')

        course = Course.objects.create(
            course_code='SEC200',
            course_name='Security Engineering',
            credits=3,
            instructor='Instructor',
            price=Decimal('2.00'),
            is_approved=True,
            duration_weeks=8,
            main_file=SimpleUploadedFile('main_overview.pptx', b'ppt-bytes'),
        )
        hidden_material = CourseMaterial.objects.create(
            course=course,
            title='Hidden draft lesson',
            description='Zero trust architecture requires continuous verification of users devices and services before access is granted.',
            material_type=CourseMaterial.MATERIAL_TYPE_OTHER,
            kind=CourseMaterial.KIND_LESSON,
            is_visible=False,
        )
        visible_material = CourseMaterial.objects.create(
            course=course,
            title='Secure operations',
            description='Operational monitoring helps detect incidents early and preserve critical evidence during response workflows.',
            material_type=CourseMaterial.MATERIAL_TYPE_OTHER,
            kind=CourseMaterial.KIND_LESSON,
            is_visible=True,
        )
        CourseMaterialFile.objects.create(
            material=visible_material,
            file=SimpleUploadedFile('lesson_notes.txt', b'notes-bytes'),
            title='Operations attachment',
            description='Attached file expands on hardening and operational safeguards for administrators.',
        )

        exam = Exam.objects.create(course=course, num_questions=10, is_released=False)
        regenerate_exam_questions(exam)
        joined_text = " ".join(ExamQuestion.objects.filter(exam=exam).values_list('question_text', flat=True)).lower()

        self.assertIn('zero trust', joined_text)
        self.assertIn('threat modeling', joined_text)
        self.assertIn('least privilege', joined_text)


class FormValidationTests(TestCase):
    def test_student_id_must_contain_letters_and_numbers(self):
        from .forms import StudentRegistrationForm
        # Valid ID
        form = StudentRegistrationForm(data={
            'student_id': 'STU123',
            'name': 'Test Student',
            'email': 'test@example.com',
            'password': 'password123',
            'confirm_password': 'password123',
            'date_of_birth': '2000-01-01',
            'major': 'CS',
        })
        self.assertTrue(form.is_valid())

        # Invalid: only letters
        form = StudentRegistrationForm(data={
            'student_id': 'STU',
            'name': 'Test Student',
            'email': 'test@example.com',
            'password': 'password123',
            'confirm_password': 'password123',
            'date_of_birth': '2000-01-01',
            'major': 'CS',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('Student ID must be 3-10 characters and contain both letters and numbers.', form.errors['student_id'])

        # Invalid: only numbers
        form = StudentRegistrationForm(data={
            'student_id': '123',
            'name': 'Test Student',
            'email': 'test@example.com',
            'password': 'password123',
            'confirm_password': 'password123',
            'date_of_birth': '2000-01-01',
            'major': 'CS',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('Student ID must be 3-10 characters and contain both letters and numbers.', form.errors['student_id'])

        # Invalid password: only letters
        form = StudentRegistrationForm(data={
            'student_id': 'STU123',
            'name': 'Test Student',
            'email': 'test@example.com',
            'password': 'password',
            'confirm_password': 'password',
            'date_of_birth': '2000-01-01',
            'major': 'CS',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('Password must contain both letters and numbers.', form.errors['password'])

    def test_teacher_id_must_contain_letters_and_numbers(self):
        from .forms import TeacherRegistrationForm
        from .models import StaffIDInvitation
        # Create invitation
        invitation = StaffIDInvitation.objects.create(
            staff_id='STAFF001',
            email='teacher@example.com',
        )
        # Valid ID
        form = TeacherRegistrationForm(data={
            'teacher_id': 'TCH456',
            'staff_id': 'STAFF001',
            'name': 'Test Teacher',
            'email': 'teacher@example.com',
            'password': 'password123',
            'confirm_password': 'password123',
        })
        self.assertTrue(form.is_valid())

        # Invalid: only letters
        form = TeacherRegistrationForm(data={
            'teacher_id': 'TCH',
            'staff_id': 'STAFF001',
            'name': 'Test Teacher',
            'email': 'teacher@example.com',
            'password': 'password123',
            'confirm_password': 'password123',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('Teacher ID must be 3-10 characters and contain both letters and numbers.', form.errors['teacher_id'])

        # Invalid password: only letters
        form = TeacherRegistrationForm(data={
            'teacher_id': 'TCH456',
            'staff_id': 'STAFF001',
            'name': 'Test Teacher',
            'email': 'teacher@example.com',
            'password': 'password',
            'confirm_password': 'password',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('Password must contain both letters and numbers.', form.errors['password'])
