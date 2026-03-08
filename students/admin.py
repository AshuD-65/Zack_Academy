from django.contrib import admin
from django import forms
from django.contrib.auth.hashers import make_password
from django.core.mail import send_mail
from django.conf import settings
from .models import (
    Student,
    Course,
    CourseCompletion,
    CourseMaterial,
    CourseMaterialFile,
    PasswordResetToken,
    Teacher,
    StaffIDInvitation,
    AssignmentSubmission,
    Exam,
    ExamQuestion,
    ExamAttempt,
    ExamAnswer,
)

class StudentAdmin(admin.ModelAdmin):
    # This list specifies the fields that will be displayed in the Django admin's
    # list view for the Student model.
    list_display = ('student_id', 'name', 'major', 'date_of_birth', 'courses_enrolled', 'has_profile_picture')

    # The search_fields tuple allows you to add a search bar to the admin page.
    search_fields = ('name', 'student_id')

    def courses_enrolled(self, obj):
        return ", ".join([course.course_name for course in obj.courses.all()])
    courses_enrolled.short_description = "Courses Enrolled"
    
    def has_profile_picture(self, obj):
        return bool(obj.profile_picture)
    has_profile_picture.boolean = True
    has_profile_picture.short_description = "Has Profile Picture"


class TeacherAdminForm(forms.ModelForm):
    """Admin form for creating/editing teachers. Password required for new teachers."""
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        required=False,
        help_text='Required when creating a new teacher. Leave blank when editing.',
    )

    class Meta:
        model = Teacher
        fields = ['teacher_id', 'staff_id', 'name', 'email']
        help_texts = {
            'staff_id': 'Unique staff identifier. Leave blank to auto-generate. Will be emailed to the teacher.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['password'].required = False
            self.fields['password'].help_text = 'Leave blank to keep current password.'

    def clean_teacher_id(self):
        teacher_id = (self.cleaned_data.get('teacher_id') or '').strip()
        if not teacher_id:
            return teacher_id
        qs = Teacher.objects.filter(teacher_id=teacher_id)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError('A teacher with this ID already exists.')
        return teacher_id

    def clean_staff_id(self):
        staff_id = self.cleaned_data.get('staff_id')
        if staff_id:
            staff_id = staff_id.strip()
            qs = Teacher.objects.filter(staff_id=staff_id)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError('A teacher with this Staff ID already exists.')
            return staff_id
        return None

    def clean(self):
        cleaned_data = super().clean()
        if not self.instance.pk:
            pw = cleaned_data.get('password')
            if not pw or len(pw) < 6:
                self.add_error('password', 'Password is required (min 6 characters) for new teachers.')
        return cleaned_data

    def save(self, commit=True):
        teacher = super().save(commit=False)
        if self.cleaned_data.get('password'):
            teacher.password = make_password(self.cleaned_data['password'])
        if commit:
            teacher.save()
        return teacher


def _generate_staff_id():
    """Generate next staff ID (e.g. STF001, STF002)."""
    import re
    teacher_ids = Teacher.objects.exclude(staff_id__isnull=True).exclude(staff_id='').values_list('staff_id', flat=True)
    invitation_ids = StaffIDInvitation.objects.values_list('staff_id', flat=True)
    existing = set(teacher_ids) | set(invitation_ids)
    nums = []
    for sid in existing:
        m = re.match(r'^STF(\d+)$', str(sid))
        if m:
            nums.append(int(m.group(1)))
    next_num = max(nums) + 1 if nums else 1
    return f'STF{next_num:03d}'


def _send_staff_id_invitation_email(invitation):
    """Send staff ID to teacher's email. Teacher then self-registers."""
    subject = 'Your Zack Academy Staff ID - Register as Teacher'
    message = (
        f'Hello,\n\n'
        f'You have been invited to register as a teacher at Zack Academy.\n\n'
        f'Your Staff ID: {invitation.staff_id}\n\n'
        f'Please go to the teacher registration page and sign up using this Staff ID and the same email address: {invitation.email}\n\n'
        f'You will create your Teacher ID, name, and password during registration.\n\n'
        f'Best regards,\nZack Academy'
    )
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [invitation.email],
            fail_silently=False,
        )
    except Exception:
        pass


def _send_staff_id_email(teacher):
    """Send staff ID to teacher's email."""
    staff_id = teacher.staff_id or teacher.teacher_id
    subject = 'Your Zack Academy Staff ID'
    message = (
        f'Hello {teacher.name},\n\n'
        f'Your staff account has been created at Zack Academy.\n\n'
        f'Staff ID: {staff_id}\n'
        f'Teacher ID (for login): {teacher.teacher_id}\n'
        f'Email (for login): {teacher.email}\n\n'
        f'Use your Teacher ID or Email along with the password set by the admin to sign in at the teacher portal.\n\n'
        f'Best regards,\nZack Academy'
    )
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [teacher.email],
            fail_silently=False,
        )
    except Exception:
        pass  # Don't block admin save; log if you have logging


@admin.register(StaffIDInvitation)
class StaffIDInvitationAdmin(admin.ModelAdmin):
    list_display = ('staff_id', 'email', 'created_at', 'sent_at', 'used_at')
    search_fields = ('staff_id', 'email')
    ordering = ('-created_at',)
    list_filter = ('sent_at', 'used_at')
    readonly_fields = ('created_at', 'sent_at', 'used_at')
    fieldsets = (
        (None, {'fields': ('staff_id', 'email')}),
        ('Status', {'fields': ('created_at', 'sent_at', 'used_at'), 'classes': ('collapse',)}),
    )
    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return ((None, {'fields': ('staff_id', 'email')}),)
        return self.fieldsets

    def save_model(self, request, obj, form, change):
        from django.utils import timezone
        is_new = not change
        if is_new and not (obj.staff_id or '').strip():
            obj.staff_id = _generate_staff_id()
        super().save_model(request, obj, form, change)
        if is_new and obj.email:
            _send_staff_id_invitation_email(obj)
            obj.sent_at = timezone.now()
            obj.save(update_fields=['sent_at'])


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    form = TeacherAdminForm
    list_display = ('teacher_id', 'staff_id', 'name', 'email')
    search_fields = ('teacher_id', 'staff_id', 'name', 'email')
    ordering = ('teacher_id',)
    fieldsets = (
        (None, {
            'fields': ('teacher_id', 'staff_id', 'name', 'email', 'password'),
        }),
    )

    def save_model(self, request, obj, form, change):
        is_new = not change
        # Auto-generate staff_id if blank when creating
        if is_new and not (obj.staff_id or '').strip():
            obj.staff_id = _generate_staff_id()
        super().save_model(request, obj, form, change)
        if is_new and obj.email:
            _send_staff_id_email(obj)


class CourseMaterialAdminForm(forms.ModelForm):
    """Restrict material type to only 'Video File' and generic 'File'.

    We map the generic 'File' to the existing PDF material type in the model,
    which we treat as an umbrella for any non-video document upload or link.
    """

    class Meta:
        model = CourseMaterial
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['material_type'].choices = [
            (CourseMaterial.MATERIAL_TYPE_VIDEO, 'Video File'),
            (CourseMaterial.MATERIAL_TYPE_PDF, 'File'),
        ]
        
        # Add JavaScript to show/hide fields based on material type
        self.fields['material_type'].widget.attrs.update({
            'onchange': 'toggleContentFields(this.value)'
        })

    class Media:
        js = ('admin/js/course_material_admin.js',)


class CourseMaterialFileInline(admin.TabularInline):
    model = CourseMaterialFile
    extra = 1
    fields = ('file', 'file_type', 'title', 'description', 'order', 'is_visible')
    ordering = ('order',)


class CourseMaterialInline(admin.TabularInline):
    model = CourseMaterial
    form = CourseMaterialAdminForm
    extra = 1
    fields = ('title', 'material_type', 'file', 'external_url', 'order', 'is_visible', 'is_important')
    ordering = ('order',)
    
    class Media:
        js = ('admin/js/course_material_admin.js',)


# Register the Course model with its custom admin class
class CourseAdmin(admin.ModelAdmin):
    # This list controls the columns displayed on the main Course list page.
    list_display = ('course_code', 'course_name', 'instructor', 'teacher', 'credits', 'schedule', 'duration_weeks', 'price', 'is_approved')

    # This tuple controls the fields shown when you add or edit a course.
    fields = ('course_code', 'course_name', 'instructor', 'teacher', 'credits', 'schedule', 'duration_weeks', 'price', 'is_approved')
    list_filter = ('is_approved', 'teacher')
    
    # Add materials inline
    inlines = [CourseMaterialInline]

# Register all models with their respective admin classes
admin.site.register(Student, StudentAdmin)
admin.site.register(Course, CourseAdmin)


@admin.register(CourseCompletion)
class CourseCompletionAdmin(admin.ModelAdmin):
    list_display = (
        'completion_id', 'student', 'course', 'status', 'progress_percent', 'completed_at'
    )
    list_filter = ('status', 'course')
    search_fields = ('student__student_id', 'student__name', 'course__course_code', 'course__course_name')


@admin.register(CourseMaterial)
class CourseMaterialAdmin(admin.ModelAdmin):
    form = CourseMaterialAdminForm
    list_display = ('title', 'course', 'material_type', 'order', 'is_visible', 'is_important', 'created_at')
    list_filter = ('material_type', 'is_visible', 'is_important', 'course', 'created_at')
    search_fields = ('title', 'description', 'course__course_code', 'course__course_name')
    ordering = ('course', 'order', 'created_at')
    inlines = [CourseMaterialFileInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('course', 'title', 'description', 'material_type')
        }),
        ('Content', {
            'fields': ('file', 'external_url'),
            'description': 'Upload a file OR provide an external URL. Field labels will change based on material type selected above. Additional files can be added below.'
        }),
        ('Display Options', {
            'fields': ('order', 'is_visible', 'is_important')
        }),
    )


@admin.register(CourseMaterialFile)
class CourseMaterialFileAdmin(admin.ModelAdmin):
    list_display = ('title', 'material', 'file_type', 'file_size', 'order', 'is_visible', 'created_at')
    list_filter = ('file_type', 'is_visible', 'material__course', 'created_at')
    search_fields = ('title', 'description', 'material__title', 'material__course__course_code')
    ordering = ('material', 'order', 'created_at')
    
    fieldsets = (
        ('File Information', {
            'fields': ('material', 'file', 'file_type', 'title', 'description')
        }),
        ('Display Options', {
            'fields': ('order', 'is_visible')
        }),
    )


class ExamQuestionInline(admin.TabularInline):
    model = ExamQuestion
    extra = 1
    ordering = ('order',)


@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'passing_score', 'created_at')
    list_filter = ('course',)
    search_fields = ('title', 'course__course_code')
    inlines = [ExamQuestionInline]


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ('token', 'student', 'created_at', 'expires_at', 'is_used', 'is_valid_status')
    list_filter = ('is_used', 'created_at', 'expires_at')
    search_fields = ('student__email', 'student__name', 'student__student_id')
    readonly_fields = ('token', 'created_at')
    ordering = ('-created_at',)
    
    def is_valid_status(self, obj):
        return obj.is_valid()
    is_valid_status.boolean = True
    is_valid_status.short_description = 'Is Valid'
    
    fieldsets = (
        ('Token Information', {
            'fields': ('token', 'student', 'created_at', 'expires_at')
        }),
        ('Status', {
            'fields': ('is_used',)
        }),
    )


