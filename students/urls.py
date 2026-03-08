# students/urls.py

from django.urls import path
from . import views
from . import payment_views
from . import file_views

urlpatterns = [
    # Student-facing URLs
    path('register/', views.register_choice, name='register_student'),
    path('register/student/', views.register_student, name='student_register'),
    path('login/', views.login_student, name='login_student'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('courses/', views.course_list, name='course_list'),
    path('enroll/', views.enroll_course, name='enroll_course'),
    path('logout/', views.logout_student, name='logout_student'),
    path('profile/edit/', views.edit_profile, name='edit_profile'),
    path('courses/<str:course_code>/', views.course_detail, name='course_detail'),
    path('courses/<str:course_code>/assignment/<uuid:material_id>/submit/', views.submit_assignment, name='submit_assignment'),
    path('courses/<str:course_code>/exam/', views.student_take_exam, name='student_take_exam'),
    path('exam/result/<uuid:attempt_id>/', views.student_exam_result, name='student_exam_result'),
    path('delete_enrollment/<str:course_code>/', views.delete_enrollment, name='delete_enrollment'),

    # Teacher dashboard URLs
    path('teacher/login/', views.teacher_login, name='teacher_login'),
    path('teacher/register/', views.register_teacher, name='register_teacher'),
    path('teacher/logout/', views.teacher_logout, name='teacher_logout'),
    path('teacher/dashboard/', views.teacher_dashboard, name='teacher_dashboard'),
    path('teacher/profile/edit/', views.teacher_edit_profile, name='teacher_edit_profile'),
    path('teacher/courses/create/', views.teacher_create_course, name='teacher_create_course'),
    path('teacher/courses/edit/', views.teacher_course_edit_list, name='teacher_course_edit_list'),
    path('teacher/courses/<str:course_code>/edit/', views.teacher_edit_course, name='teacher_edit_course'),
    path('teacher/courses/<str:course_code>/', views.teacher_course_detail, name='teacher_course_detail'),
    path('teacher/courses/<str:course_code>/delete/', views.teacher_delete_course, name='teacher_delete_course'),
    path(
        'teacher/courses/<str:course_code>/lessons/add/',
        views.teacher_add_lesson,
        name='teacher_add_lesson',
    ),
    path(
        'teacher/courses/<str:course_code>/assignments/add/',
        views.teacher_add_assignment,
        name='teacher_add_assignment',
    ),
    path(
        'teacher/courses/<str:course_code>/assignment/<uuid:material_id>/submissions/',
        views.teacher_submissions,
        name='teacher_submissions',
    ),
    path(
        'teacher/submission/<uuid:submission_id>/grade/',
        views.teacher_grade_submission,
        name='teacher_grade_submission',
    ),
    path(
        'teacher/courses/<str:course_code>/exam/',
        views.teacher_exam_manage,
        name='teacher_exam_manage',
    ),

    # Payments
    path('payment/checkout/', payment_views.checkout, name='payment_checkout'),
    path('payment/create-session/', payment_views.create_checkout_session, name='payment_create_session'),
    path('payment/success/', payment_views.payment_success, name='payment_success'),
    path('payment/create-intent/', payment_views.create_payment_intent, name='payment_create_intent'),
    path('payment/webhook/stripe/', payment_views.stripe_webhook, name='stripe_webhook'),

    # File serving
    path('files/<path:file_path>', file_views.serve_file_view, name='serve_file'),
    path('view-file/<path:file_path>', file_views.view_file, name='view_file'),

    # Progress tracking
    path('material-session/start/', views.start_material_session, name='start_material_session'),
    path('material-session/complete/', views.complete_material_session, name='complete_material_session'),
    path('track-material-view/', views.track_material_view, name='track_material_view'),

    # Certificate
    path('certificate/', views.generate_certificate, name='generate_certificate'),

    # Password Reset
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('reset-password/<uuid:token>/', views.reset_password, name='reset_password'),
]