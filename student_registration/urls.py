# student_registration/urls.py

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from student_registration import views  # This line imports the views module

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home, name='home'),
    path('students/', include('students.urls')),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-dashboard/logout/', views.admin_logout, name='admin_logout'),
    path('admin-dashboard/staff-ids/', views.admin_staff_ids, name='admin_staff_ids'),
    # Students (CRUD)
    path('admin-dashboard/students/', views.admin_all_students, name='admin_all_students'),
    path('admin-dashboard/students/add/', views.admin_student_create, name='admin_student_create'),
    path('admin-dashboard/students/<str:student_id>/edit/', views.admin_student_edit, name='admin_student_edit'),
    path('admin-dashboard/students/<str:student_id>/delete/', views.admin_student_delete, name='admin_student_delete'),
    # All Users (view-only: Students + Teachers)
    path('admin-dashboard/users/', views.admin_all_users, name='admin_all_users'),
    # Courses
    path('admin-dashboard/courses/', views.admin_all_courses, name='admin_all_courses'),
    path('admin-dashboard/courses/add/', views.admin_course_create, name='admin_course_create'),
    path('admin-dashboard/courses/<str:course_code>/edit/', views.admin_course_edit, name='admin_course_edit'),
    path('admin-dashboard/courses/<str:course_code>/materials/', views.admin_course_materials, name='admin_course_materials'),
    path('admin-dashboard/courses/<str:course_code>/delete/', views.admin_course_delete, name='admin_course_delete'),
    path('admin-dashboard/courses/<str:course_code>/release/', views.admin_course_release, name='admin_course_release'),
    # Teachers
    path('admin-dashboard/teachers/', views.admin_all_teachers, name='admin_all_teachers'),
    path('admin-dashboard/teachers/add/', views.admin_teacher_create, name='admin_teacher_create'),
    path('admin-dashboard/teachers/<str:teacher_id>/edit/', views.admin_teacher_edit, name='admin_teacher_edit'),
    path('admin-dashboard/teachers/<str:teacher_id>/delete/', views.admin_teacher_delete, name='admin_teacher_delete'),
]

# Serve static and media files in development
if settings.DEBUG:
    from django.contrib.staticfiles.urls import staticfiles_urlpatterns
    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
