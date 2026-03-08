import json
import shutil
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import Course, CourseMaterial, Exam, ExamAnswer, ExamQuestion, Student


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
