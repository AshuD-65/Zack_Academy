# students/forms.py

import re
from datetime import date

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Course, CourseMaterial, Student, Teacher, AssignmentSubmission, AssignmentSubmission

# Common validation helpers
ALLOWED_IMAGE_TYPES = ('image/jpeg', 'image/png', 'image/gif')
ALLOWED_VIDEO_TYPES = (
    'video/mp4',
    'video/quicktime',
    'video/x-matroska',
    'video/webm',
)
ALLOWED_PDF_TYPES = ('application/pdf',)
MAX_IMAGE_SIZE_MB = 5
MAX_MATERIAL_FILE_MB = 200
NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z\s\.\-']{1,98}[A-Za-z]$")


def _validate_file_size(upload, max_mb: int, label: str):
    if upload.size > max_mb * 1024 * 1024:
        raise ValidationError(f'{label} must be smaller than {max_mb} MB.')


def _validate_image(upload):
    if upload.content_type not in ALLOWED_IMAGE_TYPES:
        raise ValidationError('Profile picture must be JPG, PNG, or GIF.')
    _validate_file_size(upload, MAX_IMAGE_SIZE_MB, 'Profile picture')


def _validate_material_file(upload, material_type: str):
    """Validate uploaded material file against the selected material type."""
    if material_type == CourseMaterial.MATERIAL_TYPE_PDF:
        if upload.content_type not in ALLOWED_PDF_TYPES:
            raise ValidationError('Upload a PDF document for this material.')
    elif material_type == CourseMaterial.MATERIAL_TYPE_VIDEO:
        if upload.content_type not in ALLOWED_VIDEO_TYPES:
            raise ValidationError('Upload a supported video file (mp4, mov, mkv, webm).')
    _validate_file_size(upload, MAX_MATERIAL_FILE_MB, 'Material file')


def _validate_name(value: str, label: str) -> str:
    """Allow letters, spaces, period, hyphen, apostrophe; block digits/other chars."""
    name = value.strip()
    if not NAME_PATTERN.fullmatch(name):
        raise ValidationError(f'{label} must contain only letters, spaces, ., -, or \', and no digits.')
    return name

class StudentRegistrationForm(forms.ModelForm):
    """
    A form to handle student registration.
    """
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = Student
        fields = ['student_id', 'name', 'email', 'password', 'date_of_birth', 'major']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
        }

    def clean_student_id(self):
        student_id = self.cleaned_data['student_id'].strip()
        if not re.fullmatch(r'[A-Za-z0-9]{3,10}', student_id):
            raise ValidationError('Student ID must be 3-10 alphanumeric characters.')
        if Student.objects.filter(student_id=student_id).exists():
            raise ValidationError('A student with this ID already exists.')
        return student_id

    def clean_name(self):
        return _validate_name(self.cleaned_data['name'], 'Name')

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if Student.objects.filter(email=email).exists():
            raise ValidationError('A student with this email already exists.')
        return email

    def clean_date_of_birth(self):
        dob = self.cleaned_data['date_of_birth']
        if dob > date.today():
            raise ValidationError('Date of birth cannot be in the future.')
        return dob

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and len(password) < 6:
            self.add_error('password', 'Password must be at least 6 characters long.')

        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', 'Passwords do not match.')

        return cleaned_data


class TeacherRegistrationForm(forms.ModelForm):
    """
    A form to handle teacher registration.
    Staff ID must come from an invitation sent by admin to this email.
    """
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = Teacher
        fields = ['teacher_id', 'staff_id', 'name', 'email', 'password']

    def clean_teacher_id(self):
        teacher_id = self.cleaned_data['teacher_id'].strip()
        if not re.fullmatch(r'[A-Za-z0-9]{3,10}', teacher_id):
            raise ValidationError('Teacher ID must be 3-10 alphanumeric characters.')
        if Teacher.objects.filter(teacher_id=teacher_id).exists():
            raise ValidationError('A teacher with this ID already exists.')
        return teacher_id

    def clean_staff_id(self):
        staff_id = (self.cleaned_data.get('staff_id') or '').strip()
        if not staff_id:
            raise ValidationError('Staff ID is required (check your email for the invitation).')
        if Teacher.objects.filter(staff_id=staff_id).exists():
            raise ValidationError('This Staff ID is already registered.')
        return staff_id

    def clean_name(self):
        return _validate_name(self.cleaned_data['name'], 'Name')

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if Teacher.objects.filter(email=email).exists():
            raise ValidationError('A teacher with this email already exists.')
        if Student.objects.filter(email=email).exists():
            raise ValidationError('This email is already registered as a student. You cannot use the same email for teacher registration.')
        return email

    def clean(self):
        from .models import StaffIDInvitation
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        staff_id = cleaned_data.get('staff_id')
        email = (cleaned_data.get('email') or '').lower().strip()

        if password and len(password) < 6:
            self.add_error('password', 'Password must be at least 6 characters long.')

        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', 'Passwords do not match.')

        # Staff ID must be from an unused invitation sent to this email
        if staff_id and email:
            inv = StaffIDInvitation.objects.filter(
                staff_id=staff_id,
                email__iexact=email,
                used_at__isnull=True,
            ).first()
            if not inv:
                self.add_error(
                    'staff_id',
                    'Invalid Staff ID or email. Use the Staff ID sent to your email.',
                )
                self.add_error(
                    'email',
                    'Email must match the one that received the Staff ID.',
                )

        return cleaned_data


class AssignmentSubmissionForm(forms.ModelForm):
    """Student submits assignment: file and/or text."""
    class Meta:
        model = AssignmentSubmission
        fields = ['file', 'text_answer']
        widgets = {
            'file': forms.FileInput(attrs={'accept': '.pdf,.doc,.docx,.txt,.zip', 'class': 'input-field'}),
            'text_answer': forms.Textarea(attrs={'rows': 6, 'class': 'input-field', 'placeholder': 'Or type your answer here...'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        file = cleaned_data.get('file')
        text = (cleaned_data.get('text_answer') or '').strip()
        if not file and not text:
            raise ValidationError('Submit a file and/or type your answer.')
        return cleaned_data


class StudentLoginForm(forms.Form):
    """
    A form to handle both student and admin login.
    """
    username = forms.CharField(max_length=200, label='ID or Email')
    password = forms.CharField(widget=forms.PasswordInput)


class TeacherLoginForm(forms.Form):
    """
    A simple login form for teachers.
    """
    username = forms.CharField(max_length=200, label='Teacher ID or Email')
    password = forms.CharField(widget=forms.PasswordInput)

class StudentProfileForm(forms.ModelForm):
    """
    A form for editing a student's profile.
    This form excludes the student_id and password fields.
    """
    class Meta:
        model = Student
        fields = ['name', 'email', 'date_of_birth', 'major', 'profile_picture']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date'}),
            'profile_picture': forms.FileInput(attrs={'accept': 'image/*', 'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['profile_picture'].required = False
        self.fields['profile_picture'].help_text = "Upload a profile picture (JPG, PNG, GIF). Leave empty to keep current picture."

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        qs = Student.objects.filter(email=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('Another student already uses this email.')
        return email

    def clean_name(self):
        return _validate_name(self.cleaned_data['name'], 'Name')

    def clean_profile_picture(self):
        upload = self.cleaned_data.get('profile_picture')
        if upload:
            _validate_image(upload)
        return upload


class TeacherProfileForm(forms.ModelForm):
    """
    A form for editing a teacher's profile.
    This form excludes the teacher_id, password, and status fields.
    """
    class Meta:
        model = Teacher
        fields = ['name', 'email', 'profile_picture']
        widgets = {
            'profile_picture': forms.FileInput(attrs={'accept': 'image/*', 'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['profile_picture'].required = False
        self.fields['profile_picture'].help_text = "Upload a profile picture (JPG, PNG, GIF). Leave empty to keep current picture."

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        qs = Teacher.objects.filter(email=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('Another teacher already uses this email.')
        return email

    def clean_name(self):
        return _validate_name(self.cleaned_data['name'], 'Name')

    def clean_profile_picture(self):
        upload = self.cleaned_data.get('profile_picture')
        if upload:
            _validate_image(upload)
        return upload


class CourseMaterialForm(forms.ModelForm):
    """
    Form used on the teacher dashboard to add lessons/assignments (includes course).
    """
    class Meta:
        model = CourseMaterial
        fields = [
            'course',
            'title',
            'description',
            'material_type',
            'file',
            'external_url',
            'order',
            'is_visible',
            'is_important',
        ]

    def clean(self):
        cleaned_data = super().clean()
        material_type = cleaned_data.get('material_type')
        file = cleaned_data.get('file')
        external_url = cleaned_data.get('external_url')

        if material_type == CourseMaterial.MATERIAL_TYPE_URL:
            if not external_url:
                self.add_error('external_url', 'An external URL is required for URL materials.')
            if file:
                self.add_error('file', 'Remove the file for URL materials.')
        else:
            if not file and not external_url:
                self.add_error('file', 'Upload a file or provide an external URL.')
            if file and material_type:
                _validate_material_file(file, material_type)
        return cleaned_data


class CourseMaterialFormAdd(forms.ModelForm):
    """
    Add lesson/assignment: course is set in the view, not in the form.
    """
    class Meta:
        model = CourseMaterial
        fields = [
            'kind',
            'title',
            'description',
            'material_type',
            'file',
            'external_url',
            'order',
            'is_visible',
            'is_important',
        ]
        widgets = {
            'kind': forms.Select(attrs={'class': 'input-field'}),
            'material_type': forms.Select(attrs={'class': 'input-field'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        material_type = cleaned_data.get('material_type')
        file = cleaned_data.get('file')
        external_url = cleaned_data.get('external_url')

        if material_type == CourseMaterial.MATERIAL_TYPE_URL:
            if not external_url:
                self.add_error('external_url', 'An external URL is required for URL materials.')
            if file:
                self.add_error('file', 'Remove the file for URL materials.')
        else:
            if not file and not external_url:
                self.add_error('file', 'Upload a file or provide an external URL.')
            if file and material_type:
                _validate_material_file(file, material_type)
        return cleaned_data


class CourseForm(forms.ModelForm):
    """
    Course form used by admin (includes price and is_approved).
    """
    class Meta:
        model = Course
        fields = [
            'course_code',
            'course_name',
            'credits',
            'instructor',
            'schedule',
            'price',
            'duration_weeks',
            'is_approved',
            'teacher',
        ]
        widgets = {
            'course_code': forms.TextInput(attrs={'class': 'input-field'}),
            'course_name': forms.TextInput(attrs={'class': 'input-field'}),
            'credits': forms.NumberInput(attrs={'class': 'input-field'}),
            'instructor': forms.TextInput(attrs={'class': 'input-field'}),
            'schedule': forms.TextInput(attrs={'class': 'input-field'}),
            'price': forms.NumberInput(attrs={'class': 'input-field', 'step': '0.01'}),
            'duration_weeks': forms.NumberInput(attrs={'class': 'input-field'}),
            'is_approved': forms.CheckboxInput(attrs={'class': 'input-field'}),
            'teacher': forms.Select(attrs={'class': 'input-field'}),
        }

    def clean_course_code(self):
        code = self.cleaned_data['course_code'].upper()
        qs = Course.objects.filter(course_code=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('A course with this code already exists.')
        return code

    def clean_credits(self):
        credits = self.cleaned_data['credits']
        if credits <= 0:
            raise ValidationError('Credits must be greater than zero.')
        return credits

    def clean_price(self):
        price = self.cleaned_data['price']
        if price <= 0:
            raise ValidationError('Price must be greater than zero.')
        return price

    def clean_duration_weeks(self):
        duration = self.cleaned_data['duration_weeks']
        if duration <= 0:
            raise ValidationError('Duration must be at least 1 week.')
        return duration


class CourseFormTeacher(forms.ModelForm):
    """
    Course creation/edit form for teachers. Excludes price (set by admin only).
    """
    class Meta:
        model = Course
        fields = [
            'course_code',
            'course_name',
            'credits',
            'instructor',
            'schedule',
            'duration_weeks',
        ]

    def clean_course_code(self):
        code = self.cleaned_data['course_code'].upper()
        qs = Course.objects.filter(course_code=code)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('A course with this code already exists.')
        return code

    def clean_credits(self):
        credits = self.cleaned_data['credits']
        if credits <= 0:
            raise ValidationError('Credits must be greater than zero.')
        return credits

    def clean_duration_weeks(self):
        duration = self.cleaned_data['duration_weeks']
        if duration <= 0:
            raise ValidationError('Duration must be at least 1 week.')
        return duration


class AdminStudentForm(forms.ModelForm):
    """Admin form for create/edit Student. Password required only for create."""
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'input-field'}),
        required=False,
        help_text='Leave blank when editing; required for new students.',
    )

    class Meta:
        model = Student
        fields = ['student_id', 'name', 'email', 'date_of_birth', 'major']
        widgets = {
            'date_of_birth': forms.DateInput(attrs={'type': 'date', 'class': 'input-field'}),
            'student_id': forms.TextInput(attrs={'class': 'input-field'}),
            'name': forms.TextInput(attrs={'class': 'input-field'}),
            'email': forms.EmailInput(attrs={'class': 'input-field'}),
            'major': forms.TextInput(attrs={'class': 'input-field'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields.pop('password', None)

    def clean_student_id(self):
        student_id = self.cleaned_data['student_id'].strip()
        qs = Student.objects.filter(student_id=student_id)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('A student with this ID already exists.')
        return student_id

    def clean_name(self):
        return _validate_name(self.cleaned_data['name'], 'Name')

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        qs = Student.objects.filter(email=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('A student with this email already exists.')
        return email

    def clean_date_of_birth(self):
        dob = self.cleaned_data['date_of_birth']
        if dob > timezone.localdate():
            raise ValidationError('Date of birth cannot be in the future.')
        return dob

    def clean(self):
        cleaned_data = super().clean()
        if not self.instance.pk and 'password' in self.fields:
            pw = cleaned_data.get('password')
            if not pw or len(pw) < 6:
                self.add_error('password', 'Password is required (min 6 characters) for new students.')
        return cleaned_data


class AdminTeacherForm(forms.ModelForm):
    """Admin form for create/edit Teacher. Admin assigns Staff ID."""
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'input-field'}),
        required=False,
        help_text='Required when creating a new teacher.',
    )

    class Meta:
        model = Teacher
        fields = ['teacher_id', 'staff_id', 'name', 'email']
        widgets = {
            'teacher_id': forms.TextInput(attrs={'class': 'input-field', 'id': 'id_teacher_id'}),
            'staff_id': forms.TextInput(attrs={'class': 'input-field', 'id': 'id_staff_id', 'autocomplete': 'off'}),
            'name': forms.TextInput(attrs={'class': 'input-field'}),
            'email': forms.EmailInput(attrs={'class': 'input-field'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields.pop('password', None)

    def clean_teacher_id(self):
        teacher_id = self.cleaned_data['teacher_id'].strip()
        qs = Teacher.objects.filter(teacher_id=teacher_id)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('A teacher with this ID already exists.')
        return teacher_id

    def clean_name(self):
        return _validate_name(self.cleaned_data['name'], 'Name')

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        qs = Teacher.objects.filter(email=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('A teacher with this email already exists.')
        return email

    def clean_staff_id(self):
        staff_id = self.cleaned_data.get('staff_id')
        if staff_id:
            staff_id = staff_id.strip()
            qs = Teacher.objects.filter(staff_id=staff_id)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError('A teacher with this Staff ID already exists.')
            return staff_id
        return None

    def clean(self):
        cleaned_data = super().clean()
        if not self.instance.pk and 'password' in self.fields:
            pw = cleaned_data.get('password')
            if not pw or len(pw) < 6:
                self.add_error('password', 'Password is required (min 6 characters) for new teachers.')
        return cleaned_data


class ForgotPasswordForm(forms.Form):
    """
    A form for requesting password reset.
    """
    email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email address',
            'autocomplete': 'email'
        }),
        help_text="Enter the email address associated with your account."
    )


class ResetPasswordForm(forms.Form):
    """
    A form for resetting password with token validation.
    """
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter new password',
            'autocomplete': 'new-password'
        }),
        min_length=6,
        help_text="Password must be at least 6 characters long."
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm new password',
            'autocomplete': 'new-password'
        }),
        help_text="Re-enter your new password to confirm."
    )
    
    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        
        if password and confirm_password:
            if password != confirm_password:
                raise forms.ValidationError("Passwords do not match.")
        
        return cleaned_data