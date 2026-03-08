from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator, MaxValueValidator
from decimal import Decimal
import uuid
import os


def student_profile_picture_upload_path(instance, filename):
    """Generate upload path for student profile pictures"""
    return f'student_profiles/{instance.student_id}/{filename}'


def teacher_profile_picture_upload_path(instance, filename):
    """Generate upload path for teacher profile pictures"""
    return f'teacher_profiles/{instance.teacher_id}/{filename}'


class StaffIDInvitation(models.Model):
    """
    Admin creates staff IDs and sends them to teacher emails.
    Teacher self-registers using the staff ID received.
    """
    staff_id = models.CharField(max_length=20, unique=True, db_index=True)
    email = models.EmailField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['email', 'used_at'])]

    def __str__(self):
        return f"{self.staff_id} -> {self.email}"


class Teacher(models.Model):
    """Basic teacher account used for the teacher dashboard.

    Teachers no longer have an approval status – once registered they can use
    the system and courses control visibility via the Course.is_approved flag.
    staff_id is a unique identifier only teachers have (students do not).
    """

    teacher_id = models.CharField(max_length=10, primary_key=True)
    staff_id = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        null=True,
        help_text='Unique staff identifier (only teachers have this; students do not).',
    )
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    # Store hashed password similar to Student
    password = models.CharField(max_length=128)
    profile_picture = models.ImageField(
        upload_to=teacher_profile_picture_upload_path,
        blank=True,
        null=True,
        help_text="Upload a profile picture (JPG, PNG, GIF)",
    )

    def __str__(self):
        return self.name


class Student(models.Model):
    student_id = models.CharField(max_length=10, primary_key=True)
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=128) # Increased length for hashed password
    date_of_birth = models.DateField()
    major = models.CharField(max_length=100)
    courses = models.ManyToManyField('Course', related_name='students')
    profile_picture = models.ImageField(upload_to=student_profile_picture_upload_path, blank=True, null=True, help_text="Upload a profile picture (JPG, PNG, GIF)")

    def __str__(self):
        return self.name

class Course(models.Model):
    course_code = models.CharField(max_length=10, primary_key=True)
    course_name = models.CharField(max_length=100)
    credits = models.IntegerField()
    instructor = models.CharField(max_length=100)
    # Optional explicit relation to a Teacher account for dashboards
    teacher = models.ForeignKey(
        'Teacher',
        on_delete=models.SET_NULL,
        related_name='courses',
        null=True,
        blank=True,
        help_text='Teacher responsible for this course (used in teacher dashboard).',
    )
    # Added the new schedule field
    schedule = models.CharField(max_length=100, default='To be announced')
    # Course price in dollars; use Decimal for currency to avoid float issues
    price = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('2.00'), validators=[MinValueValidator(Decimal('0.50'))])
    # Admin approval required before students can see/enroll
    is_approved = models.BooleanField(default=False, help_text='Only approved courses are visible to students.')
    # Duration in weeks
    duration_weeks = models.PositiveIntegerField(default=12)

    def __str__(self):
        return self.course_name


class CourseCompletion(models.Model):
    """Tracks a student's progress and completion status for a course.

    This model is appended as an add-on and references existing primary keys
    without changing or removing any existing fields or relationships.
    """
    completion_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='course_completions')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='course_completions')

    STATUS_IN_PROGRESS = 'IN_PROGRESS'
    STATUS_COMPLETED = 'COMPLETED'
    STATUS_FAILED = 'FAILED'
    STATUS_WITHDRAWN = 'WITHDRAWN'

    STATUS_CHOICES = [
        (STATUS_IN_PROGRESS, 'In Progress'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_FAILED, 'Failed'),
        (STATUS_WITHDRAWN, 'Withdrawn'),
    ]

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_IN_PROGRESS)
    progress_percent = models.PositiveIntegerField(default=0, validators=[MinValueValidator(0)])
    completed_at = models.DateTimeField(null=True, blank=True)
    grade = models.CharField(max_length=10, null=True, blank=True)
    certificate_url = models.URLField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=['student', 'status']),
            models.Index(fields=['course', 'status']),
        ]
        constraints = [
            models.UniqueConstraint(fields=['student', 'course'], name='unique_student_course_completion')
        ]

    def mark_completed(self, grade: str | None = None):
        self.status = self.STATUS_COMPLETED
        self.completed_at = timezone.now()
        if grade is not None:
            self.grade = grade

    def __str__(self):
        return f"{self.student.student_id}-{self.course.course_code}:{self.status}"


def course_material_upload_path(instance, filename):
    """Generate upload path for course materials"""
    return f'course_materials/{instance.course.course_code}/{instance.material_type.lower()}/{filename}'

def course_material_file_upload_path(instance, filename):
    """Generate upload path for course material files"""
    return f'course_materials/{instance.material.course.course_code}/files/{filename}'


class CourseMaterial(models.Model):
    """Model for course materials including videos and PDFs"""
    KIND_LESSON = 'LESSON'
    KIND_ASSIGNMENT = 'ASSIGNMENT'
    KIND_CHOICES = [
        (KIND_LESSON, 'Lesson'),
        (KIND_ASSIGNMENT, 'Assignment'),
    ]
    
    MATERIAL_TYPE_VIDEO = 'VIDEO'
    MATERIAL_TYPE_PDF = 'PDF'
    MATERIAL_TYPE_URL = 'URL'
    MATERIAL_TYPE_OTHER = 'OTHER'
    
    MATERIAL_TYPE_CHOICES = [
        (MATERIAL_TYPE_VIDEO, 'Video File'),
        (MATERIAL_TYPE_PDF, 'PDF Document'),
        (MATERIAL_TYPE_URL, 'External URL'),
        (MATERIAL_TYPE_OTHER, 'Other'),
    ]
    
    material_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='materials')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES, default=KIND_LESSON)
    material_type = models.CharField(max_length=10, choices=MATERIAL_TYPE_CHOICES)
    
    # For uploaded files
    file = models.FileField(upload_to=course_material_upload_path, blank=True, null=True)
    
    # For external URLs (YouTube, Vimeo, etc.)
    external_url = models.URLField(blank=True, null=True)
    
    # Ordering and visibility
    order = models.PositiveIntegerField(default=0)
    is_visible = models.BooleanField(default=True)
    is_important = models.BooleanField(default=False)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'created_at']
        indexes = [
            models.Index(fields=['course', 'material_type']),
            models.Index(fields=['course', 'is_visible']),
        ]
    
    def __str__(self):
        return f"{self.course.course_code} - {self.title}"
    
    @property
    def file_size(self):
        """Return file size in human readable format"""
        if self.file:
            try:
                size = self.file.size
                for unit in ['B', 'KB', 'MB', 'GB']:
                    if size < 1024.0:
                        return f"{size:.1f} {unit}"
                    size /= 1024.0
                return f"{size:.1f} TB"
            except (ValueError, OSError):
                return "Unknown"
        return None
    
    @property
    def is_video(self):
        return self.material_type == self.MATERIAL_TYPE_VIDEO
    
    @property
    def is_pdf(self):
        return self.material_type == self.MATERIAL_TYPE_PDF
    
    @property
    def is_external_url(self):
        return self.material_type == self.MATERIAL_TYPE_URL

    @property
    def is_other(self):
        return self.material_type == self.MATERIAL_TYPE_OTHER


class CourseMaterialFile(models.Model):
    """Model for multiple files attached to course materials"""
    
    FILE_TYPE_VIDEO = 'VIDEO'
    FILE_TYPE_DOCUMENT = 'DOCUMENT'
    FILE_TYPE_IMAGE = 'IMAGE'
    FILE_TYPE_AUDIO = 'AUDIO'
    FILE_TYPE_OTHER = 'OTHER'
    
    FILE_TYPE_CHOICES = [
        (FILE_TYPE_VIDEO, 'Video File'),
        (FILE_TYPE_DOCUMENT, 'Document'),
        (FILE_TYPE_IMAGE, 'Image'),
        (FILE_TYPE_AUDIO, 'Audio'),
        (FILE_TYPE_OTHER, 'Other'),
    ]
    
    file_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    material = models.ForeignKey(CourseMaterial, on_delete=models.CASCADE, related_name='files')
    file = models.FileField(upload_to=course_material_file_upload_path)
    file_type = models.CharField(max_length=10, choices=FILE_TYPE_CHOICES, default=FILE_TYPE_DOCUMENT)
    title = models.CharField(max_length=200, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    order = models.PositiveIntegerField(default=0)
    is_visible = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'created_at']
        indexes = [
            models.Index(fields=['material', 'file_type']),
            models.Index(fields=['material', 'is_visible']),
        ]
    
    def __str__(self):
        return f"{self.material.title} - {self.file.name}"
    
    @property
    def file_size(self):
        """Return file size in human readable format"""
        if self.file:
            try:
                size = self.file.size
                for unit in ['B', 'KB', 'MB', 'GB']:
                    if size < 1024.0:
                        return f"{size:.1f} {unit}"
                    size /= 1024.0
                return f"{size:.1f} TB"
            except (ValueError, OSError):
                return "Unknown"
        return None
    
    @property
    def is_video(self):
        return self.file_type == self.FILE_TYPE_VIDEO
    
    @property
    def is_document(self):
        return self.file_type == self.FILE_TYPE_DOCUMENT
    
    @property
    def is_image(self):
        return self.file_type == self.FILE_TYPE_IMAGE
    
    @property
    def is_audio(self):
        return self.file_type == self.FILE_TYPE_AUDIO


class PasswordResetToken(models.Model):
    """Model to store password reset tokens"""
    token = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='password_reset_tokens')
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['token', 'is_used']),
            models.Index(fields=['student', 'is_used']),
        ]
    
    def __str__(self):
        return f"Reset token for {self.student.email}"
    
    def is_expired(self):
        return timezone.now() > self.expires_at
    
    def is_valid(self):
        return not self.is_used and not self.is_expired()


class MaterialViewLog(models.Model):
    """Tracks when a student views a specific course material."""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='material_views')
    material = models.ForeignKey(CourseMaterial, on_delete=models.CASCADE, related_name='view_logs')
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'material')
        indexes = [
            models.Index(fields=['student', 'material']),
            models.Index(fields=['material', 'student']),
        ]
        ordering = ['-viewed_at']

    def __str__(self):
        return f"{self.student.student_id} viewed {self.material.title}"


def assignment_submission_upload_path(instance, filename):
    """Upload path for assignment submissions."""
    return f'assignments/{instance.material.course.course_code}/{instance.student.student_id}/{filename}'


class AssignmentSubmission(models.Model):
    """Student submission for an assignment (CourseMaterial with kind=ASSIGNMENT)."""
    submission_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='assignment_submissions')
    material = models.ForeignKey(
        CourseMaterial,
        on_delete=models.CASCADE,
        related_name='submissions',
        limit_choices_to={'kind': CourseMaterial.KIND_ASSIGNMENT},
    )
    file = models.FileField(upload_to=assignment_submission_upload_path, blank=True, null=True)
    text_answer = models.TextField(blank=True, null=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    grade = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    feedback = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('student', 'material')
        ordering = ['-submitted_at']
        indexes = [models.Index(fields=['material']), models.Index(fields=['student', 'material'])]

    def __str__(self):
        return f"{self.student.student_id} - {self.material.title}"


class Exam(models.Model):
    """Course exam - auto-generated by system. Teacher only sets passing score and release."""
    exam_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.OneToOneField(Course, on_delete=models.CASCADE, related_name='exam')
    title = models.CharField(max_length=200, default='Final Exam')
    passing_score = models.PositiveIntegerField(default=70, help_text='Minimum score % to pass')
    is_released = models.BooleanField(default=False, help_text='Students can take exam when released')
    num_questions = models.PositiveIntegerField(default=10, help_text='Number of questions to generate', validators=[MinValueValidator(1), MaxValueValidator(100)])
    time_limit_minutes = models.PositiveIntegerField(default=60, help_text='Time limit in minutes')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['course']

    def __str__(self):
        return f"{self.course.course_code} - {self.title}"


class ExamQuestion(models.Model):
    """Auto-generated question from course materials."""
    TYPE_MULTIPLE_CHOICE = 'MULTIPLE_CHOICE'
    TYPE_TRUE_FALSE = 'TRUE_FALSE'
    TYPE_CHOICES = [
        (TYPE_MULTIPLE_CHOICE, 'Multiple Choice'),
        (TYPE_TRUE_FALSE, 'True/False'),
    ]
    question_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    question_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_MULTIPLE_CHOICE)
    options_json = models.JSONField(blank=True, null=True, help_text='["Option A", "Option B", "Option C", "Option D"]')
    correct_answer = models.CharField(max_length=500, help_text='Correct answer (A, B, C, D or True/False)')
    order = models.PositiveIntegerField(default=0)
    points = models.PositiveIntegerField(default=1)
    source_material = models.ForeignKey('CourseMaterial', on_delete=models.SET_NULL, null=True, blank=True, help_text='Material this question was generated from')

    class Meta:
        ordering = ['exam', 'order']

    def __str__(self):
        return f"{self.exam.course.course_code} Q{self.order}"


class ExamAttempt(models.Model):
    """Student attempt at an exam - auto-graded by system."""
    attempt_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='exam_attempts')
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='attempts')
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    score = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    passed = models.BooleanField(null=True, blank=True)
    time_taken_seconds = models.PositiveIntegerField(null=True, blank=True, help_text='Time taken to complete')

    class Meta:
        ordering = ['-started_at']
        indexes = [models.Index(fields=['student', 'exam'])]

    def __str__(self):
        return f"{self.student.student_id} - {self.exam.course.course_code} - {'Passed' if self.passed else 'Failed' if self.passed is False else 'In Progress'}"


class ExamAnswer(models.Model):
    """Student's answer to an exam question."""
    attempt = models.ForeignKey(ExamAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(ExamQuestion, on_delete=models.CASCADE, related_name='answers')
    selected_answer = models.CharField(max_length=500, blank=True, null=True)
    is_correct = models.BooleanField(null=True, blank=True)

    class Meta:
        unique_together = ('attempt', 'question')

    def __str__(self):
        return f"{self.attempt} - Q{self.question.order}"


class MaterialEngagementSession(models.Model):
    """Stores active engagement sessions that enforce minimum study time."""
    session_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='engagement_sessions')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='engagement_sessions')
    material = models.ForeignKey(CourseMaterial, on_delete=models.CASCADE, related_name='engagement_sessions')
    required_seconds = models.PositiveIntegerField()
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=['student', 'material']),
            models.Index(fields=['course', 'material']),
        ]

    def has_met_requirement(self):
        if self.is_completed:
            return True
        elapsed = (timezone.now() - self.started_at).total_seconds()
        return elapsed >= self.required_seconds

    def remaining_seconds(self):
        elapsed = (timezone.now() - self.started_at).total_seconds()
        remaining = self.required_seconds - elapsed
        return max(0, int(remaining))
