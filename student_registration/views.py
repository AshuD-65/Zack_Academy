# student_registration/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import logout
from django.views.decorators.http import require_POST
from django.urls import reverse
from django.contrib import messages
from django.db.models import Count
from django.contrib.auth import get_user_model

from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings

from students.models import Student, Course, Teacher, CourseMaterial, StaffIDInvitation
from students.forms import CourseForm, AdminStudentForm, AdminTeacherForm
from django.contrib.auth.hashers import make_password


def home(request):
    """
    A simple view for the project's home page with real statistics.
    """
    import random
    
    # Get real data from database
    total_students = Student.objects.count()
    total_courses = Course.objects.count()
    total_instructors = Course.objects.values('instructor').distinct().count()
    
    # Calculate success rate (students who completed at least one course)
    students_with_completions = Student.objects.filter(
        course_completions__status='COMPLETED'
    ).distinct().count()
    
    if total_students > 0:
        success_rate = int((students_with_completions / total_students) * 100)
    else:
        success_rate = 0
    
    
    value_props = [
        {
            'title': f"{max(total_courses, 1)}+ Courses",
            'description': 'Explore a wide catalog that spans technology, business, and more.',
            'icon': 'fa-graduation-cap',
        },
        {
            'title': 'Self-paced Learning',
            'description': 'Flexible schedules let you learn anytime on any device.',
            'icon': 'fa-clock',
        },
        {
            'title': 'Top Instructors',
            'description': f'Learn directly from {max(total_instructors, 1)}+ experienced mentors.',
            'icon': 'fa-chalkboard-teacher',
        },
    ]

    highlighted_courses = list(
        Course.objects.annotate(enrolled_count=Count('students')).order_by('-enrolled_count', 'course_name')[:6]
    )
    
    # Function to get course icon based on course name
    def get_course_icon(course):
        """Get appropriate icon for course based on name"""
        course_lower = course.course_name.lower()
        
        # Map course types to icons
        if 'psychology' in course_lower:
            return 'brain'
        elif 'sociology' in course_lower:
            return 'users'
        elif 'religion' in course_lower:
            return 'book-open'
        elif 'software' in course_lower or 'computer' in course_lower:
            return 'code'
        elif 'engineering' in course_lower:
            return 'cog'
        elif 'science' in course_lower:
            return 'flask'
        elif 'math' in course_lower:
            return 'calculator'
        elif 'business' in course_lower:
            return 'briefcase'
        elif 'art' in course_lower:
            return 'palette'
        elif 'history' in course_lower:
            return 'scroll'
        elif 'language' in course_lower:
            return 'language'
        else:
            return 'graduation-cap'
    
    # Add icons to popular courses
    popular_courses_with_images = []
    for course in highlighted_courses[:4]:
        popular_courses_with_images.append({
            'course': course,
            'icon': get_course_icon(course),
        })
    
    icon_pool = ['fa-book', 'fa-lightbulb', 'fa-chart-line', 'fa-laptop-code', 'fa-robot', 'fa-globe-africa']
    category_cards = [
        {
            'label': course.course_name,
            'code': course.course_code,
            'icon': icon_pool[index % len(icon_pool)],
            'lessons': course.duration_weeks,
        }
        for index, course in enumerate(highlighted_courses)
    ]

    popular_courses = highlighted_courses[:4]

    testimonial_students = list(Student.objects.prefetch_related('courses')[:3])
    testimonials = [
        {
            'name': student.name,
            'major': student.major,
            'quote': f'"Zack Academy gave me the structure and flexibility I needed to excel in {student.major}."',
        }
        for student in testimonial_students
    ]
    if not testimonials:
        testimonials = [
            {
                'name': 'Future Graduate',
                'major': 'Computer Science',
                'quote': '"Zack Academy keeps my learning organized and engaging."',
            }
        ]

    articles = [
        {
            'title': course.course_name,
            'summary': f"{course.course_name} now open for enrollment.",
            'code': course.course_code,
        }
        for course in highlighted_courses[:3]
    ]

    partners = [
        {
            'name': 'Ministry of Innovation & Technology',
            'logo': 'https://upload.wikimedia.org/wikipedia/commons/5/5c/Emblem_of_Ethiopia.svg',
        },
        {'name': 'UNDP', 'logo': 'https://upload.wikimedia.org/wikipedia/commons/0/02/UNDP_logo.svg'},
        {'name': 'European Union', 'logo': 'https://upload.wikimedia.org/wikipedia/commons/b/b7/Flag_of_Europe.svg'},
    ]

    context = {
        'total_students': total_students,
        'total_courses': total_courses,
        'total_instructors': total_instructors,
        'success_rate': success_rate,
        'value_props': value_props,
        'category_cards': category_cards,
        'popular_courses': popular_courses,
        'popular_courses_with_images': popular_courses_with_images,
        'testimonials': testimonials,
        'articles': articles,
        'partners': partners,
    }

    return render(request, 'home.html', context)


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
    return f'STF{max(nums) + 1:03d}' if nums else 'STF001'


def _send_staff_id_invitation_email(invitation):
    """Send staff ID to teacher's email."""
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


@staff_member_required
def admin_dashboard(request):
    """
    Custom admin dashboard. Shows overview and Staff ID creation.
    """
    total_students = Student.objects.count()
    total_teachers = Teacher.objects.count()
    total_courses = Course.objects.count()
    total_enrollments = Student.objects.filter(courses__isnull=False).count()

    top_courses = (
        Course.objects.annotate(enrolled_count=Count('students'))
        .order_by('-enrolled_count', 'course_name')[:5]
    )
    pending_courses = Course.objects.filter(is_approved=False).count()
    recent_students = Student.objects.all().order_by('-student_id')[:5]
    recent_teachers = Teacher.objects.all().order_by('-teacher_id')[:5]

    context = {
        'total_students': total_students,
        'total_teachers': total_teachers,
        'total_courses': total_courses,
        'total_enrollments': total_enrollments,
        'pending_courses': pending_courses,
        'recent_students': recent_students,
        'recent_teachers': recent_teachers,
        'top_courses': top_courses,
    }
    return render(request, 'admin_dashboard.html', context)


@staff_member_required
def admin_logout(request):
    logout(request)
    return redirect('home')


@staff_member_required
def admin_staff_ids(request):
    """Create and manage Staff ID invitations."""
    recent_invitations = StaffIDInvitation.objects.order_by('-created_at')[:50]
    if request.method == 'POST' and 'create_staff_id' in request.POST:
        email = (request.POST.get('email') or '').strip()
        staff_id = (request.POST.get('staff_id') or '').strip()
        if not email:
            messages.error(request, 'Email is required.')
        elif StaffIDInvitation.objects.filter(email__iexact=email, used_at__isnull=True).exists():
            messages.warning(request, f'An unused invitation already exists for {email}.')
        else:
            if not staff_id:
                staff_id = _generate_staff_id()
            if StaffIDInvitation.objects.filter(staff_id=staff_id).exists() or Teacher.objects.filter(staff_id=staff_id).exists():
                messages.error(request, f'Staff ID {staff_id} is already in use.')
            else:
                inv = StaffIDInvitation.objects.create(staff_id=staff_id, email=email)
                inv.sent_at = timezone.now()
                inv.save()
                _send_staff_id_invitation_email(inv)
                messages.success(request, f'Staff ID {staff_id} sent to {email}.')
                return redirect('admin_staff_ids')
    return render(request, 'admin/staff_ids.html', {'recent_invitations': recent_invitations})


# ----- Students -----

@staff_member_required
def admin_all_students(request):
    """List of all students with CRUD operations."""
    students = Student.objects.all().order_by('student_id')
    return render(request, 'admin/students_list.html', {
        'students': students,
        'students_count': students.count(),
    })


# ----- All Users (view-only: Students + Teachers + Admins) -----

@staff_member_required
def admin_all_users(request):
    """View-only list of all users (Students, Teachers, Django staff)."""
    all_users = []
    for s in Student.objects.all().order_by('student_id'):
        all_users.append({
            'type': 'Student',
            'id': s.student_id,
            'name': s.name,
            'email': s.email,
            'detail': f'Major: {s.major}',
            'profile_picture_url': s.profile_picture.url if s.profile_picture else None,
        })
    for t in Teacher.objects.all().order_by('teacher_id'):
        all_users.append({
            'type': 'Teacher',
            'id': t.teacher_id,
            'name': t.name,
            'email': t.email,
            'detail': f'Staff ID: {t.staff_id or "-"}',
            'profile_picture_url': t.profile_picture.url if t.profile_picture else None,
        })
    User = get_user_model()
    for u in User.objects.filter(is_staff=True).order_by('username'):
        display_name = (u.get_full_name() or u.username).strip()
        all_users.append({
            'type': 'Admin',
            'id': u.username,
            'name': display_name,
            'email': u.email or '-',
            'detail': 'Django staff account',
            'profile_picture_url': None,
        })
    return render(request, 'admin/users_list.html', {
        'all_users': all_users,
        'all_users_count': len(all_users),
    })


@staff_member_required
def admin_student_create(request):
    form = AdminStudentForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.password = make_password(form.cleaned_data['password'])
        obj.save()
        messages.success(request, 'Student created.')
        return redirect('admin_all_students')
    return render(request, 'admin/student_form.html', {'form': form, 'is_edit': False})


@staff_member_required
def admin_student_edit(request, student_id):
    student = get_object_or_404(Student, student_id=student_id)
    form = AdminStudentForm(request.POST or None, request.FILES or None, instance=student)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Student updated.')
        return redirect('admin_all_students')
    return render(request, 'admin/student_form.html', {'form': form, 'student': student, 'is_edit': True})


@staff_member_required
@require_POST
def admin_student_delete(request, student_id):
    student = get_object_or_404(Student, student_id=student_id)
    student.delete()
    messages.success(request, 'Student deleted.')
    return redirect('admin_all_students')


# ----- Courses CRUD (admin sets price, release/approve) -----

@staff_member_required
def admin_all_courses(request):
    courses = Course.objects.select_related('teacher').all().order_by('course_code')
    return render(request, 'admin/courses_list.html', {'courses': courses})


@staff_member_required
def admin_course_create(request):
    form = CourseForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Course created.')
        return redirect('admin_all_courses')
    return render(request, 'admin/course_form.html', {'form': form, 'is_edit': False})


@staff_member_required
def admin_course_edit(request, course_code):
    course = get_object_or_404(Course, course_code=course_code)
    form = CourseForm(request.POST or None, instance=course)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Course updated.')
        return redirect('admin_all_courses')
    return render(request, 'admin/course_form.html', {'form': form, 'course': course, 'is_edit': True})


@staff_member_required
@require_POST
def admin_course_delete(request, course_code):
    course = get_object_or_404(Course, course_code=course_code)
    course.delete()
    messages.success(request, 'Course deleted.')
    return redirect('admin_all_courses')


@staff_member_required
def admin_course_materials(request, course_code):
    """Admin view to see all course materials (lessons and assignments) posted by teacher."""
    course = get_object_or_404(Course, course_code=course_code)
    materials = CourseMaterial.objects.filter(course=course).order_by('kind', 'order', 'created_at')
    lessons = materials.filter(kind=CourseMaterial.KIND_LESSON)
    assignments = materials.filter(kind=CourseMaterial.KIND_ASSIGNMENT)
    return render(request, 'admin/course_materials.html', {
        'course': course,
        'materials': materials,
        'lessons': lessons,
        'assignments': assignments,
    })


@staff_member_required
@require_POST
def admin_course_release(request, course_code):
    course = get_object_or_404(Course, course_code=course_code)
    course.is_approved = not course.is_approved
    course.save()
    status = 'approved and released' if course.is_approved else 'unreleased'
    messages.success(request, f'Course {status}.')
    return redirect('admin_all_courses')


# ----- Teachers CRUD (no approval workflow) -----

@staff_member_required
def admin_all_teachers(request):
    teachers = Teacher.objects.all().order_by('teacher_id')
    return render(request, 'admin/teachers_list.html', {'teachers': teachers})


@staff_member_required
def admin_teacher_create(request):
    form = AdminTeacherForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.password = make_password(form.cleaned_data['password'])
        obj.save()
        messages.success(request, 'Teacher created. Share the Staff ID and password with the teacher.')
        return redirect('admin_all_teachers')
    return render(request, 'admin/teacher_form.html', {'form': form, 'is_edit': False})


@staff_member_required
def admin_teacher_edit(request, teacher_id):
    teacher = get_object_or_404(Teacher, teacher_id=teacher_id)
    form = AdminTeacherForm(request.POST or None, instance=teacher)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Teacher updated.')
        return redirect('admin_all_teachers')
    return render(request, 'admin/teacher_form.html', {'form': form, 'teacher': teacher, 'is_edit': True})


@staff_member_required
@require_POST
def admin_teacher_delete(request, teacher_id):
    teacher = get_object_or_404(Teacher, teacher_id=teacher_id)
    teacher.delete()
    messages.success(request, 'Teacher deleted.')
    return redirect('admin_all_teachers')

