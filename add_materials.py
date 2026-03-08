#!/usr/bin/env python
"""
Script to add materials to a specific course
Run with: python add_materials.py
"""

import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'student_registration.settings')
django.setup()

from students.models import Course, CourseMaterial

def add_materials_to_course():
    # Get the specific course (CS404: Web Development with Django)
    try:
        course = Course.objects.get(course_code='CS404')
        print(f"Found course: {course.course_name}")
        
        # Add a video material
        video_material = CourseMaterial.objects.create(
            course=course,
            title="Django Models Tutorial",
            description="Learn how to create and use Django models effectively",
            material_type=CourseMaterial.MATERIAL_TYPE_VIDEO,
            external_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # Example URL
            order=1,
            is_visible=True
        )
        print(f"✅ Added video material: {video_material.title}")
        
        # Add a PDF material
        pdf_material = CourseMaterial.objects.create(
            course=course,
            title="Django Documentation",
            description="Official Django documentation for web development",
            material_type=CourseMaterial.MATERIAL_TYPE_PDF,
            external_url="https://docs.djangoproject.com/",  # Example URL
            order=2,
            is_visible=True
        )
        print(f"✅ Added PDF material: {pdf_material.title}")
        
        # Add another video
        video_material2 = CourseMaterial.objects.create(
            course=course,
            title="Django Views and URLs",
            description="Understanding Django views and URL patterns",
            material_type=CourseMaterial.MATERIAL_TYPE_VIDEO,
            external_url="https://www.youtube.com/watch?v=example2",  # Example URL
            order=3,
            is_visible=True
        )
        print(f"✅ Added video material: {video_material2.title}")
        
        print(f"\n🎉 Successfully added materials to {course.course_name}")
        print(f"Total materials for this course: {CourseMaterial.objects.filter(course=course).count()}")
        
    except Course.DoesNotExist:
        print("❌ Course CS404 not found. Available courses:")
        for course in Course.objects.all()[:5]:
            print(f"  - {course.course_code}: {course.course_name}")

if __name__ == "__main__":
    add_materials_to_course()
