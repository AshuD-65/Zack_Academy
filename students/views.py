from django.shortcuts import render, redirect, get_object_or_404
from django.forms import HiddenInput
from django.urls import reverse
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
import json
from .forms import (
    StudentRegistrationForm,
    StudentLoginForm,
    StudentProfileForm,
    ForgotPasswordForm,
    ResetPasswordForm,
    TeacherLoginForm,
    TeacherProfileForm,
    CourseMaterialForm,
    CourseMaterialFormAdd,
    TeacherRegistrationForm,
    CourseForm,
    CourseFormTeacher,
    AssignmentSubmissionForm,
)
from django.contrib.auth.hashers import make_password, check_password
from .models import (
    Student,
    Course,
    CourseCompletion,
    CourseMaterial,
    CourseMaterialFile,
    PasswordResetToken,
    MaterialViewLog,
    MaterialEngagementSession,
    Teacher,
    AssignmentSubmission,
    Exam,
    ExamQuestion,
    ExamAttempt,
    ExamAnswer,
)
from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string
from django.utils.html import strip_tags
import secrets
import logging

from .progress import recalculate_course_progress

PDF_REQUIRED_SECONDS = 30 * 60  # 30 minutes
VIDEO_REQUIRED_SECONDS = 15 * 60  # 15 minutes minimum viewing
DEFAULT_REQUIRED_SECONDS = 5 * 60  # fallback for other material types


def _required_seconds_for_material(material: CourseMaterial) -> int:
    if material.material_type == CourseMaterial.MATERIAL_TYPE_PDF:
        return PDF_REQUIRED_SECONDS
    if material.material_type == CourseMaterial.MATERIAL_TYPE_VIDEO:
        return VIDEO_REQUIRED_SECONDS
    return DEFAULT_REQUIRED_SECONDS


def teacher_login(request):
    """
    Login view for teachers. Teachers are stored in the Teacher model and
    authenticated similarly to students (with hashed passwords).
    """
    if request.method == 'POST':
        form = TeacherLoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']

            try:
                # Try lookup by teacher_id first, then by email
                try:
                    teacher = Teacher.objects.get(teacher_id=username)
                except Teacher.DoesNotExist:
                    teacher = Teacher.objects.get(email=username)

                if check_password(password, teacher.password):
                    # Teachers can login regardless of status - courses are what get approved, not teachers
                    # Clear any student session to avoid mixed nav/redirects
                    if 'student_id' in request.session:
                        del request.session['student_id']
                    request.session['teacher_id'] = teacher.teacher_id
                    return redirect(reverse('teacher_dashboard'))
                else:
                    form.add_error(None, "Invalid credentials.")
            except Teacher.DoesNotExist:
                form.add_error(None, "Invalid credentials.")
    else:
        form = TeacherLoginForm()

    return render(request, 'teachers/login.html', {'form': form})


def teacher_logout(request):
    """
    Simple logout for teacher accounts.
    """
    # Clear teacher session (and any student session to avoid mixed state)
    request.session.pop('teacher_id', None)
    request.session.pop('student_id', None)
    # Always send everyone to the main sign-in form
    return redirect(reverse('login_student'))


def teacher_required(view_func):
    """
    Decorator-like helper to ensure a teacher is logged in.
    Blocks access if the same email is registered as a student.
    Returns (teacher, redirect_response) so views can reuse the logic.
    """
    def _inner(request, *args, **kwargs):
        teacher_id = request.session.get('teacher_id')
        if not teacher_id:
            return None, redirect(reverse('teacher_login'))
        teacher = get_object_or_404(Teacher, teacher_id=teacher_id)
        # Prevent students from accessing teacher dashboard (same email = student account takes precedence)
        if Student.objects.filter(email=teacher.email).exists():
            request.session.pop('teacher_id', None)
            from django.contrib import messages
            messages.error(request, 'This email is registered as a student. Please use the student login.')
            return None, redirect(reverse('teacher_login'))
        return teacher, None

    return _inner


def teacher_dashboard(request):
    """
    Dashboard for teachers to see their courses and manage materials.
    """
    get_teacher = teacher_required(None)
    teacher, redirect_response = get_teacher(request)
    if redirect_response:
        return redirect_response

    # Courses explicitly linked to this teacher
    courses = Course.objects.filter(teacher=teacher).order_by('course_code')

    context = {
        'teacher': teacher,
        'courses': courses,
    }
    return render(request, 'teachers/dashboard.html', context)


def teacher_create_course(request):
    """
    Allow a teacher to create a course. Admin must approve before it is visible to students.
    """
    get_teacher = teacher_required(None)
    teacher, redirect_response = get_teacher(request)
    if redirect_response:
        return redirect_response

    if request.method == 'POST':
        form = CourseFormTeacher(request.POST)
        if form.is_valid():
            course = form.save(commit=False)
            course.teacher = teacher
            course.is_approved = False
            # Price is set by admin only; use model default
            course.save()
            # Optional main course file (PDF or document) – separate from lessons/assignments
            main_file = request.FILES.get('main_file')
            if main_file:
                name = main_file.name.lower()
                mtype = CourseMaterial.MATERIAL_TYPE_PDF if name.endswith('.pdf') else CourseMaterial.MATERIAL_TYPE_OTHER
                CourseMaterial.objects.create(
                    course=course,
                    title=main_file.name,
                    material_type=mtype,
                    file=main_file,
                    order=0,
                    is_visible=True,
                )
            return redirect(reverse('teacher_add_lesson', kwargs={'course_code': course.course_code}))
    else:
        form = CourseFormTeacher(initial={'instructor': teacher.name})

    context = {
        'teacher': teacher,
        'form': form,
    }
    return render(request, 'teachers/create_course.html', context)


def teacher_add_lesson(request, course_code):
    """Add a new lesson (material) to a course."""
    return _teacher_add_material(request, course_code, CourseMaterial.KIND_LESSON, 'teachers/add_lesson.html')


def teacher_add_assignment(request, course_code):
    """Add a new assignment to a course."""
    return _teacher_add_material(request, course_code, CourseMaterial.KIND_ASSIGNMENT, 'teachers/add_assignment.html')


def _teacher_add_material(request, course_code, kind, template_name):
    """Shared logic for adding lesson or assignment."""
    get_teacher = teacher_required(None)
    teacher, redirect_response = get_teacher(request)
    if redirect_response:
        return redirect_response

    course = get_object_or_404(Course, course_code=course_code, teacher=teacher)

    if request.method == 'POST':
        form = CourseMaterialFormAdd(request.POST, request.FILES)
        if form.is_valid():
            material = form.save(commit=False)
            material.course = course
            material.kind = kind
            material.save()
            return redirect(reverse('teacher_dashboard'))
    else:
        form = CourseMaterialFormAdd(initial={'order': 0, 'kind': kind})
    if 'kind' in form.fields:
        form.fields['kind'].widget = HiddenInput()

    context = {
        'teacher': teacher,
        'course': course,
        'form': form,
        'kind': kind,
    }
    return render(request, template_name, context)


def teacher_course_edit_list(request):
    """List of teacher's courses with Edit and Add Material links."""
    get_teacher = teacher_required(None)
    teacher, redirect_response = get_teacher(request)
    if redirect_response:
        return redirect_response
    courses = Course.objects.filter(teacher=teacher).order_by('course_code')
    context = {'teacher': teacher, 'courses': courses}
    return render(request, 'teachers/course_edit_list.html', context)


def teacher_edit_course(request, course_code):
    """Edit course details (teachers cannot set price)."""
    get_teacher = teacher_required(None)
    teacher, redirect_response = get_teacher(request)
    if redirect_response:
        return redirect_response
    course = get_object_or_404(Course, course_code=course_code, teacher=teacher)
    if request.method == 'POST':
        data = request.POST.copy()
        data['course_code'] = course.course_code
        form = CourseFormTeacher(data, instance=course)
        if form.is_valid():
            form.save()
            return redirect(reverse('teacher_course_detail', kwargs={'course_code': course.course_code}))
    else:
        form = CourseFormTeacher(instance=course)
        form.fields['course_code'].disabled = True
    context = {'teacher': teacher, 'course': course, 'form': form}
    return render(request, 'teachers/edit_course.html', context)


def teacher_course_detail(request, course_code):
    """
    View to display all details about a course for teachers.
    Shows all materials (visible and invisible), enrolled students, and course information.
    """
    get_teacher = teacher_required(None)
    teacher, redirect_response = get_teacher(request)
    if redirect_response:
        return redirect_response
    
    course = get_object_or_404(Course, course_code=course_code, teacher=teacher)
    
    # Get all course materials (both visible and invisible for teachers)
    materials = CourseMaterial.objects.filter(course=course).order_by('order', 'created_at')
    important_materials = materials.filter(is_important=True)
    lessons = materials.filter(kind=CourseMaterial.KIND_LESSON)
    assignments = materials.filter(kind=CourseMaterial.KIND_ASSIGNMENT)
    
    # Get enrolled students
    enrolled_students = course.students.all()
    enrolled_students_count = enrolled_students.count()
    
    context = {
        'teacher': teacher,
        'course': course,
        'materials': materials,
        'important_materials': important_materials,
        'lessons': lessons,
        'assignments': assignments,
        'enrolled_students': enrolled_students,
        'enrolled_students_count': enrolled_students_count,
    }
    return render(request, 'teachers/course_detail.html', context)


def teacher_submissions(request, course_code, material_id):
    """Teacher views all submissions for an assignment."""
    get_teacher = teacher_required(None)
    teacher, redirect_response = get_teacher(request)
    if redirect_response:
        return redirect_response
    course = get_object_or_404(Course, course_code=course_code, teacher=teacher)
    material = get_object_or_404(
        CourseMaterial,
        material_id=material_id,
        course=course,
        kind=CourseMaterial.KIND_ASSIGNMENT,
    )
    submissions = AssignmentSubmission.objects.filter(material=material).select_related('student').order_by('-submitted_at')
    return render(request, 'teachers/assignment_submissions.html', {
        'teacher': teacher,
        'course': course,
        'material': material,
        'submissions': submissions,
    })


@require_POST
def teacher_grade_submission(request, submission_id):
    """Teacher grades a submission."""
    get_teacher = teacher_required(None)
    teacher, redirect_response = get_teacher(request)
    if redirect_response:
        return redirect_response
    sub = get_object_or_404(AssignmentSubmission, submission_id=submission_id)
    if sub.material.course.teacher_id != teacher.teacher_id:
        from django.contrib import messages
        messages.error(request, 'You cannot grade this submission.')
        return redirect('teacher_dashboard')
    grade = request.POST.get('grade')
    feedback = request.POST.get('feedback', '')
    if grade is not None:
        try:
            sub.grade = float(grade)
        except (TypeError, ValueError):
            pass
    sub.feedback = feedback
    sub.save()
    from django.contrib import messages
    messages.success(request, 'Submission graded.')
    return redirect(reverse('teacher_submissions', kwargs={
        'course_code': sub.material.course.course_code,
        'material_id': sub.material_id,
    }))


@require_POST
def teacher_delete_course(request, course_code):
    """
    Allow a teacher to delete one of their courses.
    """
    get_teacher = teacher_required(None)
    teacher, redirect_response = get_teacher(request)
    if redirect_response:
        return redirect_response
    
    course = get_object_or_404(Course, course_code=course_code, teacher=teacher)
    course_name = course.course_name
    course.delete()
    
    # Import messages here to avoid circular imports
    from django.contrib import messages
    messages.success(request, f'Course "{course_name}" has been deleted successfully.')
    return redirect(reverse('teacher_dashboard'))


def register_choice(request):
    """
    Simple page with buttons to register as student or teacher.
    """
    return render(request, 'students/register_choice.html')


def register_student(request):
    """
    Student registration form.
    """
    if request.method == 'POST':
        form = StudentRegistrationForm(request.POST)
        if form.is_valid():
            # Correctly hash the password before saving.
            student = form.save(commit=False)
            student.password = make_password(form.cleaned_data['password'])
            student.save()
            # Auto-login after registration
            request.session['student_id'] = student.student_id
            # Redirect to intended destination or dashboard
            next_url = request.session.get('next', reverse('dashboard'))
            if 'next' in request.session:
                del request.session['next']
            return redirect(next_url)
    else:
        form = StudentRegistrationForm()
        # Store intended destination if coming from course list
        if request.GET.get('from') == 'courses':
            request.session['next'] = reverse('course_list')

    return render(request, 'students/register.html', {'form': form})


def register_teacher(request):
    """
    Register a teacher account.
    Staff ID must come from an invitation sent by admin to teacher's email.
    """
    from .models import StaffIDInvitation
    from django.utils import timezone
    if request.method == 'POST':
        form = TeacherRegistrationForm(request.POST)
        if form.is_valid():
            teacher = form.save(commit=False)
            teacher.password = make_password(form.cleaned_data['password'])
            teacher.staff_id = form.cleaned_data.get('staff_id') or None
            teacher.save()
            # Mark the invitation as used
            StaffIDInvitation.objects.filter(
                staff_id=teacher.staff_id,
                email__iexact=teacher.email,
                used_at__isnull=True,
            ).update(used_at=timezone.now())
            request.session['teacher_id'] = teacher.teacher_id
            return redirect(reverse('teacher_dashboard'))
    else:
        form = TeacherRegistrationForm()

    return render(request, 'teachers/register.html', {'form': form})

def login_student(request):
    if request.method == 'POST':
        form = StudentLoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            
            # Try admin login first
            from django.contrib.auth import authenticate
            user = authenticate(request, username=username, password=password)
            
            if user is not None and user.is_staff:
                # Admin login successful - use Django's login
                from django.contrib.auth import login
                login(request, user)
                return redirect(reverse('admin_dashboard'))

            # Try teacher login next
            try:
                try:
                    teacher = Teacher.objects.get(teacher_id=username)
                except Teacher.DoesNotExist:
                    teacher = Teacher.objects.get(email=username)

                if check_password(password, teacher.password):
                    # Teachers can login regardless of status - courses are what get approved, not teachers
                    # Clear any student session to avoid mixed nav/redirects
                    if 'student_id' in request.session:
                        del request.session['student_id']
                    request.session['teacher_id'] = teacher.teacher_id
                    return redirect(reverse('teacher_dashboard'))
            except Teacher.DoesNotExist:
                pass
            
            # Try student login by student_id
            try:
                student = Student.objects.get(student_id=username)
                if check_password(password, student.password):
                    # Store the student_id in the session
                    request.session['student_id'] = student.student_id
                    # Redirect to intended destination or dashboard
                    next_url = request.session.get('next', reverse('dashboard'))
                    if 'next' in request.session:
                        del request.session['next']
                    return redirect(next_url)
                else:
                    form.add_error(None, "Invalid credentials.")
            except Student.DoesNotExist:
                # Try with email
                try:
                    student = Student.objects.get(email=username)
                    if check_password(password, student.password):
                        request.session['student_id'] = student.student_id
                        # Redirect to intended destination or dashboard
                        next_url = request.session.get('next', reverse('dashboard'))
                        if 'next' in request.session:
                            del request.session['next']
                        return redirect(next_url)
                    else:
                        form.add_error(None, "Invalid credentials.")
                except Student.DoesNotExist:
                    form.add_error(None, "Invalid credentials.")
    else:
        form = StudentLoginForm()

    return render(request, 'students/login.html', {'form': form})
    
def dashboard(request):
    """
    A simple dashboard for logged-in students.
    """
    student = None
    enrolled_courses = []
    progress_summaries = []
    if 'student_id' in request.session:
        try:
            student = Student.objects.get(student_id=request.session['student_id'])
            # Get the courses enrolled by the student
            enrolled_courses = student.courses.all()
            # Build progress summaries for enrolled courses
            for c in enrolled_courses:
                completion = CourseCompletion.objects.filter(student=student, course=c).first()
                progress_summaries.append({
                    'course': c,
                    'status': completion.status if completion else 'IN_PROGRESS',
                    'progress_percent': completion.progress_percent if completion else 0,
                    'grade': completion.grade if completion else None,
                    'certificate_url': completion.certificate_url if completion else None,
                    'completed_at': completion.completed_at if completion else None,
                })
        except Student.DoesNotExist:
            # Handle the case where the session has a bad ID
            pass
    
    context = {
        'student': student,
        'enrolled_courses': enrolled_courses,
        'progress_summaries': progress_summaries,
    }
    
    return render(request, 'students/dashboard.html', context)
    
def course_list(request):
    """
    A view to display all available courses.
    Requires user to be logged in.
    """
    # Check if student is logged in
    if 'student_id' not in request.session:
        # Store the intended destination
        request.session['next'] = reverse('course_list')
        # Redirect to login with a message
        from django.contrib import messages
        messages.info(request, 'Please login or register to view available courses.')
        return redirect(reverse('login_student'))
    
    courses = Course.objects.filter(is_approved=True)
    context = {
        'courses': courses
    }
    return render(request, 'students/course_list.html', context)

def enroll_course(request):
    """
    A view to handle course enrollment.
    """
    if request.method == 'POST':
        # Get the course_code from the form
        course_code = request.POST.get('course_code')
        
        # Check if a student is logged in
        if 'student_id' in request.session:
            student_id = request.session['student_id']
            try:
                # Get the student and the course objects
                student = get_object_or_404(Student, student_id=student_id)
                course = Course.objects.filter(course_code=course_code, is_approved=True).first()
                if not course:
                    return redirect(reverse('course_list'))
                
                # Add the course to the student's courses
                student.courses.add(course)
                return redirect(reverse('dashboard'))
            except (Student.DoesNotExist, Course.DoesNotExist):
                # Handle cases where the student or course is not found
                pass
    
    return redirect(reverse('course_list'))

def logout_student(request):
    """
    A view to handle student logout.
    """
    if 'student_id' in request.session:
        del request.session['student_id']
    return redirect(reverse('login_student'))

def edit_profile(request):
    """
    A view to handle editing a student's profile.
    """
    if 'student_id' not in request.session:
        return redirect(reverse('login_student'))

    student = get_object_or_404(Student, student_id=request.session['student_id'])

    if request.method == 'POST':
        form = StudentProfileForm(request.POST, request.FILES, instance=student)
        if form.is_valid():
            form.save()
            return redirect(reverse('dashboard'))
    else:
        form = StudentProfileForm(instance=student)
    
    context = {
        'form': form,
        'student': student
    }
    return render(request, 'students/edit_profile.html', context)


def teacher_edit_profile(request):
    """
    A view to handle editing a teacher's profile.
    """
    get_teacher = teacher_required(None)
    teacher, redirect_response = get_teacher(request)
    if redirect_response:
        return redirect_response

    if request.method == 'POST':
        form = TeacherProfileForm(request.POST, request.FILES, instance=teacher)
        if form.is_valid():
            form.save()
            return redirect(reverse('teacher_dashboard'))
    else:
        form = TeacherProfileForm(instance=teacher)
    
    context = {
        'form': form,
        'teacher': teacher
    }
    return render(request, 'teachers/edit_profile.html', context)

def course_detail(request, course_code):
    """
    A view to display details for a single course, including enrolled students and materials.
    """
    course = get_object_or_404(Course, course_code=course_code)
    enrolled_students_count = course.students.count()  # Only get count, not all students
    current_student = None
    completion = None
    is_enrolled = False
    submissions_by_material = {}
    
    # Get course materials (only visible ones) and split by lesson/assignment
    materials = CourseMaterial.objects.filter(course=course, is_visible=True).order_by('order', 'created_at')
    important_materials = materials.filter(is_important=True)
    lessons = materials.filter(kind=CourseMaterial.KIND_LESSON)
    assignments = materials.filter(kind=CourseMaterial.KIND_ASSIGNMENT)

    if 'student_id' in request.session:
        try:
            current_student = Student.objects.get(student_id=request.session['student_id'])
            is_enrolled = current_student.courses.filter(course_code=course.course_code).exists()
            if is_enrolled:
                completion = CourseCompletion.objects.filter(student=current_student, course=course).first()
                submissions_by_material = {
                    s.material_id: s for s in AssignmentSubmission.objects.filter(
                        student=current_student, material__course=course
                    ).select_related('material')
                }
        except Student.DoesNotExist:
            current_student = None

    # Check if exam exists and is released
    course_has_exam = hasattr(course, 'exam') and course.exam.is_released
    
    context = {
        'course': course,
        'enrolled_students_count': enrolled_students_count,
        'current_student': current_student,
        'completion': completion,
        'is_enrolled': is_enrolled,
        'materials': materials,
        'important_materials': important_materials,
        'lessons': lessons,
        'assignments': assignments,
        'submissions_by_material': submissions_by_material,
        'course_has_exam': course_has_exam,
    }
    return render(request, 'students/course_detail.html', context)


def delete_enrollment(request, course_code):
    """
    A view to handle the deletion of a student's course enrollment.
    """
    if 'student_id' not in request.session:
        return redirect(reverse('login_student'))
    
    if request.method == 'POST':
        student = get_object_or_404(Student, student_id=request.session['student_id'])
        course = get_object_or_404(Course, course_code=course_code)
        
        # Remove the course from the student's enrolled courses.
        student.courses.remove(course)
    
    return redirect(reverse('dashboard'))


def submit_assignment(request, course_code, material_id):
    """Student submits assignment (file and/or text)."""
    if 'student_id' not in request.session:
        return redirect(reverse('login_student'))
    student = get_object_or_404(Student, student_id=request.session['student_id'])
    course = get_object_or_404(Course, course_code=course_code)
    if not student.courses.filter(course_code=course_code).exists():
        return redirect(reverse('course_detail', kwargs={'course_code': course_code}))
    material = get_object_or_404(
        CourseMaterial,
        material_id=material_id,
        course=course,
        kind=CourseMaterial.KIND_ASSIGNMENT,
    )
    existing = AssignmentSubmission.objects.filter(student=student, material=material).first()
    if request.method == 'POST':
        form = AssignmentSubmissionForm(request.POST, request.FILES, instance=existing)
        if form.is_valid():
            sub = form.save(commit=False)
            sub.student = student
            sub.material = material
            sub.save()
            from django.contrib import messages
            messages.success(request, 'Assignment submitted successfully.')
            return redirect(reverse('course_detail', kwargs={'course_code': course_code}) + '?tab=assignments')
    else:
        form = AssignmentSubmissionForm(instance=existing)
    return render(request, 'students/submit_assignment.html', {
        'form': form,
        'course': course,
        'material': material,
        'existing': existing,
    })


@require_POST
def start_material_session(request):
    """Create a timed engagement session before the student can get credit."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = {}

    if 'student_id' not in request.session:
        return JsonResponse({'error': 'Not logged in'}, status=401)

    student = get_object_or_404(Student, student_id=request.session['student_id'])
    material_id = data.get('material_id')
    course_code = data.get('course_code')

    if not material_id or not course_code:
        return JsonResponse({'error': 'Missing material information'}, status=400)

    course = get_object_or_404(Course, course_code=course_code)
    material = get_object_or_404(CourseMaterial, material_id=material_id, course=course)

    if not student.courses.filter(course_code=course.course_code).exists():
        return JsonResponse({'error': 'Not enrolled in course'}, status=403)

    # Clear any previous incomplete sessions for this material
    MaterialEngagementSession.objects.filter(
        student=student, material=material, is_completed=False
    ).delete()

    required_seconds = _required_seconds_for_material(material)
    session = MaterialEngagementSession.objects.create(
        student=student,
        course=course,
        material=material,
        required_seconds=required_seconds,
    )

    return JsonResponse({
        'success': True,
        'session_id': str(session.session_id),
        'required_seconds': required_seconds,
        'material_title': material.title,
        'material_type': material.material_type,
    })


@require_POST
def complete_material_session(request):
    """Mark a timed engagement session as completed once enough time has passed."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        data = {}

    if 'student_id' not in request.session:
        return JsonResponse({'error': 'Not logged in'}, status=401)

    student = get_object_or_404(Student, student_id=request.session['student_id'])
    session_id = data.get('session_id')

    if not session_id:
        return JsonResponse({'error': 'Missing session ID'}, status=400)

    session = get_object_or_404(MaterialEngagementSession, session_id=session_id)

    if session.student_id != student.pk:
        return JsonResponse({'error': 'Session does not belong to this student'}, status=403)

    if session.is_completed:
        completion, total_materials, viewed_materials = recalculate_course_progress(student, session.course)
        return JsonResponse({
            'success': True,
            'already_completed': True,
            'progress_percent': completion.progress_percent,
            'status': completion.status,
            'total_materials': total_materials,
            'viewed_materials': viewed_materials,
        })

    if not session.has_met_requirement():
        return JsonResponse({
            'error': 'REQUIREMENT_NOT_MET',
            'remaining_seconds': session.remaining_seconds(),
        }, status=400)

    session.is_completed = True
    session.completed_at = timezone.now()
    session.save(update_fields=['is_completed', 'completed_at'])

    MaterialViewLog.objects.get_or_create(student=student, material=session.material)
    completion, total_materials, viewed_materials = recalculate_course_progress(student, session.course)

    return JsonResponse({
        'success': True,
        'progress_percent': completion.progress_percent,
        'status': completion.status,
        'total_materials': total_materials,
        'viewed_materials': viewed_materials,
    })

@require_POST
def track_material_view(request):
    """
    Track when a student views course material and update their progress
    """
    try:
        data = json.loads(request.body)
        material_id = data.get('material_id')
        course_code = data.get('course_code')
        
        # Check if student is logged in
        if 'student_id' not in request.session:
            return JsonResponse({'error': 'Not logged in'}, status=401)
        
        student_id = request.session['student_id']
        student = get_object_or_404(Student, student_id=student_id)
        course = get_object_or_404(Course, course_code=course_code)
        material = get_object_or_404(CourseMaterial, material_id=material_id, course=course)
        
        # Check if student is enrolled in the course
        if not student.courses.filter(course_code=course_code).exists():
            return JsonResponse({'error': 'Not enrolled in course'}, status=403)
        
        # Timed materials must go through engagement sessions
        # Count any material view (including PDFs/videos) toward progress

        # Persist view log and recalculate progress centrally
        MaterialViewLog.objects.get_or_create(student=student, material=material)
        completion, total_materials, viewed_materials = recalculate_course_progress(student, course)
        
        return JsonResponse({
            'success': True,
            'progress_percent': completion.progress_percent,
            'status': completion.status,
            'total_materials': total_materials,
            'viewed_materials': viewed_materials
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def generate_certificate(request):
    """
    Generate a unified certificate for all completed courses.
    Students must pass the course exam (if one exists) before the course appears on the certificate.
    """
    if 'student_id' not in request.session:
        return redirect(reverse('login_student'))
    
    student_id = request.session['student_id']
    student = get_object_or_404(Student, student_id=student_id)
    
    # Get completed course completions
    completions = CourseCompletion.objects.filter(
        student=student,
        status='COMPLETED'
    ).select_related('course').order_by('completed_at')
    
    # Filter: only include courses where student passed the exam (if exam exists)
    eligible = []
    for c in completions:
        try:
            exam = c.course.exam
        except Exam.DoesNotExist:
            exam = None
        if exam is None:
            eligible.append(c)
        else:
            if ExamAttempt.objects.filter(student=student, exam=exam, passed=True).exists():
                eligible.append(c)
    
    if not eligible:
        return render(request, 'students/no_certificate.html', {
            'student': student,
            'message': 'You need to complete at least one course and pass its exam to receive a certificate.'
        })
    
    completed_courses = eligible
    total_credits = sum(c.course.credits for c in completed_courses)
    latest_completion = max(completed_courses, key=lambda x: (x.completed_at or timezone.now()).timestamp())
    
    context = {
        'student': student,
        'completed_courses': completed_courses,
        'total_credits': total_credits,
        'completion_date': latest_completion.completed_at,
        'total_courses': len(completed_courses),
    }
    
    return render(request, 'students/certificate.html', context)


def teacher_exam_manage(request, course_code):
    """Teacher manages exam: set passing score, release status, and regenerate questions."""
    get_teacher = teacher_required(None)
    teacher, redirect_response = get_teacher(request)
    if redirect_response:
        return redirect_response
    course = get_object_or_404(Course, course_code=course_code, teacher=teacher)
    exam = getattr(course, 'exam', None)

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'create_exam' and exam is None:
            # Create exam with teacher-specified settings
            # clamp number of questions to allowed maximum
            raw_num_questions = int(request.POST.get('num_questions', 10))
            num_q = max(1, min(raw_num_questions, 100))
            exam = Exam.objects.create(
                course=course,
                title=request.POST.get('title', 'Final Exam'),
                passing_score=int(request.POST.get('passing_score', 70)),
                num_questions=num_q,
                time_limit_minutes=int(request.POST.get('time_limit_minutes', 60)),
                is_released=False  # Not released by default
            )

            # Auto-generate questions
            from .exam_generator import regenerate_exam_questions
            num_created = regenerate_exam_questions(exam)

            from django.contrib import messages
            messages.success(request, f'Exam created with {num_created} auto-generated questions.')
            return redirect(reverse('teacher_exam_manage', kwargs={'course_code': course_code}))

        elif action == 'update_exam' and exam:
            # Update exam settings
            exam.title = request.POST.get('title', exam.title)
            exam.passing_score = int(request.POST.get('passing_score', exam.passing_score))
            raw_num_questions = int(request.POST.get('num_questions', exam.num_questions))
            exam.num_questions = max(1, min(raw_num_questions, 100))
            exam.time_limit_minutes = int(request.POST.get('time_limit_minutes', exam.time_limit_minutes))
            exam.save()

            # Regenerate questions immediately so updated question count is applied
            from .exam_generator import regenerate_exam_questions
            num_created = regenerate_exam_questions(exam)

            from django.contrib import messages
            messages.success(request, f'Exam settings updated. Regenerated {num_created} questions.')
            return redirect(reverse('teacher_exam_manage', kwargs={'course_code': course_code}))

        elif action == 'toggle_release' and exam:
            # Toggle release status
            exam.is_released = not exam.is_released
            exam.save()

            from django.contrib import messages
            status = 'released' if exam.is_released else 'unreleased'
            messages.success(request, f'Exam {status}. Students can {"now" if exam.is_released else "no longer"} take it.')
            return redirect(reverse('teacher_exam_manage', kwargs={'course_code': course_code}))

        elif action == 'regenerate_questions' and exam:
            # Regenerate all questions
            from .exam_generator import regenerate_exam_questions
            num_created = regenerate_exam_questions(exam)

            from django.contrib import messages
            messages.success(request, f'Regenerated {num_created} questions.')
            return redirect(reverse('teacher_exam_manage', kwargs={'course_code': course_code}))

    questions = ExamQuestion.objects.filter(exam=exam).order_by('order') if exam else []

    # Get exam statistics
    attempts_count = 0
    pass_rate = 0
    if exam:
        attempts = ExamAttempt.objects.filter(exam=exam, submitted_at__isnull=False)
        attempts_count = attempts.count()
        if attempts_count > 0:
            passed_count = attempts.filter(passed=True).count()
            pass_rate = round((passed_count / attempts_count) * 100, 1)

    return render(request, 'teachers/exam_manage.html', {
        'teacher': teacher,
        'course': course,
        'exam': exam,
        'questions': questions,
        'attempts_count': attempts_count,
        'pass_rate': pass_rate,
    })


def student_take_exam(request, course_code):
    """Student takes the course exam - auto-graded by system."""
    if 'student_id' not in request.session:
        return redirect(reverse('login_student'))
    student = get_object_or_404(Student, student_id=request.session['student_id'])
    course = get_object_or_404(Course, course_code=course_code)

    # Check enrollment
    if not student.courses.filter(course_code=course_code).exists():
        from django.contrib import messages
        messages.error(request, 'You must be enrolled in this course to take the exam.')
        return redirect(reverse('course_detail', kwargs={'course_code': course_code}))

    # Check if exam exists
    try:
        exam = course.exam
    except Exam.DoesNotExist:
        from django.contrib import messages
        messages.info(request, 'This course has no exam yet.')
        return redirect(reverse('course_detail', kwargs={'course_code': course_code}))

    # Check if exam is released
    if not exam.is_released:
        from django.contrib import messages
        messages.info(request, 'The exam is not yet available. Please check back later.')
        return redirect(reverse('course_detail', kwargs={'course_code': course_code}))

    # Get questions
    questions = list(ExamQuestion.objects.filter(exam=exam).order_by('order'))
    if not questions:
        from django.contrib import messages
        messages.info(request, 'Exam has no questions yet.')
        return redirect(reverse('course_detail', kwargs={'course_code': course_code}))

    # Ensure there's an active attempt started when student begins the exam
    active_attempt = ExamAttempt.objects.filter(student=student, exam=exam, submitted_at__isnull=True).first()
    if request.method == 'POST':
        # Use the active attempt (created when student started); if missing, create fallback
        attempt_id = request.POST.get('attempt_id')
        attempt = None
        if attempt_id:
            try:
                attempt = ExamAttempt.objects.get(attempt_id=attempt_id, student=student, exam=exam)
            except ExamAttempt.DoesNotExist:
                attempt = None
        if attempt is None:
            attempt = active_attempt or ExamAttempt.objects.create(student=student, exam=exam)

        # Auto-grade the exam
        total_points = sum(q.points for q in questions)
        earned = 0

        for q in questions:
            key = f'q_{q.question_id}'
            ans = request.POST.get(key, '').strip()
            correct = False

            # Auto-grading logic
            if q.question_type == ExamQuestion.TYPE_MULTIPLE_CHOICE:
                # Answer should be A, B, C, or D
                correct = ans.upper() == str(q.correct_answer).upper()
            elif q.question_type == ExamQuestion.TYPE_TRUE_FALSE:
                # Answer should be True or False
                correct = ans.lower() == str(q.correct_answer).lower()

            if correct:
                earned += q.points

            # Save answer
            ExamAnswer.objects.update_or_create(
                attempt=attempt,
                question=q,
                defaults={
                    'selected_answer': ans or None,
                    'is_correct': correct,
                },
            )

        # Calculate score and pass/fail
        attempt.submitted_at = timezone.now()
        time_taken = (attempt.submitted_at - attempt.started_at).total_seconds()
        attempt.time_taken_seconds = int(time_taken)
        attempt.score = round(100 * earned / total_points, 1) if total_points else 0
        attempt.passed = attempt.score >= exam.passing_score
        attempt.save()

        # Update course completion if passed
        if attempt.passed:
            from .models import CourseCompletion
            completion, created = CourseCompletion.objects.get_or_create(
                student=student,
                course=course,
                defaults={'status': CourseCompletion.STATUS_IN_PROGRESS}
            )
            # Mark as exam passed (can be used for certificate eligibility)
            if completion.status != CourseCompletion.STATUS_COMPLETED:
                completion.status = CourseCompletion.STATUS_COMPLETED
                completion.completed_at = timezone.now()
                completion.save()
            
            # Redirect to certificate page after passing
            from django.contrib import messages
            messages.success(request, f'Congratulations! You passed with {attempt.score}%. View your certificate below.')
            return redirect(reverse('generate_certificate'))

        # If failed, redirect to exam result page
        return redirect(reverse('student_exam_result', kwargs={'attempt_id': attempt.attempt_id}))

    # Check for previous attempts
    previous_attempts = ExamAttempt.objects.filter(
        student=student,
        exam=exam,
        submitted_at__isnull=False
    ).order_by('-submitted_at')

    best_attempt = previous_attempts.filter(passed=True).first()

    # If no active attempt exists, create one now so started_at marks the start time
    if active_attempt is None:
        active_attempt = ExamAttempt.objects.create(student=student, exam=exam)

    return render(request, 'students/take_exam.html', {
        'course': course,
        'exam': exam,
        'questions': questions,
        'previous_attempts': previous_attempts[:5],  # Show last 5 attempts
        'best_attempt': best_attempt,
        'attempt': active_attempt,
    })


def student_exam_result(request, attempt_id):
    """Show exam result to student."""
    if 'student_id' not in request.session:
        return redirect(reverse('login_student'))
    attempt = get_object_or_404(ExamAttempt, attempt_id=attempt_id)
    if attempt.student_id != request.session['student_id']:
        return redirect(reverse('dashboard'))
    return render(request, 'students/exam_result.html', {
        'attempt': attempt,
        'exam': attempt.exam,
        'course': attempt.exam.course,
    })


def forgot_password(request):
    """
    Handle forgot password requests
    """
    if request.method == 'POST':
        form = ForgotPasswordForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            try:
                student = Student.objects.get(email=email)
                
                # Create password reset token (expires in 1 hour)
                reset_token = PasswordResetToken.objects.create(
                    student=student,
                    expires_at=timezone.now() + timezone.timedelta(hours=1)
                )
                
                # Send password reset email
                reset_url = request.build_absolute_uri(
                    reverse('reset_password', kwargs={'token': str(reset_token.token)})
                )
                
                subject = 'Password Reset Request - Zack Academy'
                html_message = render_to_string('students/password_reset_email.html', {
                    'student_name': student.name,
                    'reset_url': reset_url,
                    'expires_in': '1 hour'
                })
                plain_message = strip_tags(html_message)
                
                try:
                    send_mail(
                        subject,
                        plain_message,
                        settings.DEFAULT_FROM_EMAIL,
                        [email],
                        html_message=html_message,
                        fail_silently=False,
                    )
                    
                    return render(request, 'students/forgot_password_success.html', {
                        'email': email
                    })
                except Exception as e:
                    # Log the error for diagnostics; still show success for security
                    logging.getLogger(__name__).exception("Password reset email failed to send")
                    return render(request, 'students/forgot_password_success.html', {
                        'email': email
                    })
                    
            except Student.DoesNotExist:
                # For security, don't reveal if email exists or not
                return render(request, 'students/forgot_password_success.html', {
                    'email': email
                })
    else:
        form = ForgotPasswordForm()
    
    return render(request, 'students/forgot_password.html', {'form': form})


def reset_password(request, token):
    """
    Handle password reset with token validation
    """
    try:
        reset_token = PasswordResetToken.objects.get(token=token)
        
        if not reset_token.is_valid():
            return render(request, 'students/reset_password_invalid.html')
        
        if request.method == 'POST':
            form = ResetPasswordForm(request.POST)
            if form.is_valid():
                # Update student password
                student = reset_token.student
                student.password = make_password(form.cleaned_data['password'])
                student.save()
                
                # Mark token as used
                reset_token.is_used = True
                reset_token.save()
                
                return render(request, 'students/reset_password_success.html')
        else:
            form = ResetPasswordForm()
        
        return render(request, 'students/reset_password.html', {
            'form': form,
            'token': token
        })
        
    except PasswordResetToken.DoesNotExist:
        return render(request, 'students/reset_password_invalid.html')
