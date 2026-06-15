from django.utils import timezone
from django.db import transaction

from .models import CourseMaterial, CourseCompletion, MaterialViewLog


def recalculate_course_progress(student, course):
    """
    Recalculate and persist the progress for a student/course pair
    based on distinct material views.
    """
    total_materials = CourseMaterial.objects.filter(course=course, is_visible=True).count()
    completion, _ = CourseCompletion.objects.get_or_create(
        student=student,
        course=course,
        defaults={'status': CourseCompletion.STATUS_IN_PROGRESS, 'progress_percent': 0},
    )

    if total_materials == 0:
        completion.progress_percent = 0
        if completion.status != CourseCompletion.STATUS_IN_PROGRESS:
            completion.status = CourseCompletion.STATUS_IN_PROGRESS
            completion.completed_at = None
        completion.save(update_fields=['progress_percent', 'status', 'completed_at', 'updated_at'])
        return completion, total_materials, 0

    viewed_materials = (
        MaterialViewLog.objects.filter(student=student, material__course=course)
        .values('material')
        .distinct()
        .count()
    )

    progress_percent = min(int((viewed_materials / total_materials) * 100), 99)  # max 99% until exam is passed
    completion.progress_percent = progress_percent

    # Never auto-complete based on views alone — exam pass is required for 100%
    # If somehow status was COMPLETED (e.g. no exam course), keep it
    if completion.status == CourseCompletion.STATUS_COMPLETED:
        # Already completed via exam — don't downgrade
        pass
    else:
        completion.status = CourseCompletion.STATUS_IN_PROGRESS
        completion.completed_at = None

    completion.save(update_fields=['progress_percent', 'status', 'completed_at', 'updated_at'])
    return completion, total_materials, viewed_materials


