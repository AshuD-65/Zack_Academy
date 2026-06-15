"""
Management command to fix files uploaded to Cloudinary with the wrong
resource_type (image instead of raw).

Affects:
  - Course.main_file
  - CourseMaterial.file
  - CourseMaterialFile.file
  - AssignmentSubmission.file

For each file whose Cloudinary public_id sits under /image/upload/, this
command:
  1. Downloads the file bytes from Cloudinary
  2. Re-uploads with resource_type='raw'
  3. Deletes the old /image/ asset from Cloudinary
  4. Updates the Django model field to point at the new public_id

Usage:
    python manage.py fix_cloudinary_resource_type
    python manage.py fix_cloudinary_resource_type --dry-run
"""

import io
import urllib.request

from django.core.management.base import BaseCommand

import cloudinary
import cloudinary.uploader
import cloudinary.api


def _is_image_upload_url(url: str) -> bool:
    return url and 'cloudinary.com' in url and '/image/upload/' in url


def _public_id_from_url(url: str) -> str:
    """
    Extract the public_id from a Cloudinary URL.
    e.g. .../image/upload/v1/media/course_materials/main_files/foo.pdf
    -> media/course_materials/main_files/foo.pdf   (no extension for raw)
    Actually for raw resources the public_id includes the extension.
    """
    # Everything after /upload/vNNN/ or /upload/
    marker = '/upload/'
    idx = url.find(marker)
    if idx == -1:
        return ''
    after_upload = url[idx + len(marker):]
    # Strip version token like v1234567890/
    parts = after_upload.split('/', 1)
    if parts[0].startswith('v') and parts[0][1:].isdigit():
        after_upload = parts[1] if len(parts) > 1 else ''
    return after_upload


def _download_bytes(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read()


def _fix_field(obj, field_name: str, dry_run: bool, log) -> bool:
    """
    Re-upload a single FileField value if its URL is under /image/upload/.
    Returns True if a change was made (or would be made in dry-run).
    """
    field = getattr(obj, field_name, None)
    if not field or not field.name:
        return False

    try:
        url = field.url
    except Exception:
        return False

    if not _is_image_upload_url(url):
        return False

    original_name = field.name  # storage path / public_id stored in DB
    log(f'  Found: {url}')

    if dry_run:
        log(f'  [DRY-RUN] Would re-upload {original_name} as raw resource.')
        return True

    # Download from Cloudinary
    try:
        file_bytes = _download_bytes(url)
    except Exception as exc:
        log(f'  ERROR downloading {url}: {exc}')
        return False

    # Re-upload with resource_type=raw, keeping same folder/filename
    public_id = _public_id_from_url(url)
    # Remove extension from public_id for cloudinary (it's added automatically)
    # Actually for raw uploads cloudinary stores the full filename including ext
    try:
        result = cloudinary.uploader.upload(
            io.BytesIO(file_bytes),
            resource_type='raw',
            public_id=public_id,
            overwrite=True,
            use_filename=False,
        )
    except Exception as exc:
        log(f'  ERROR re-uploading {original_name}: {exc}')
        return False

    new_public_id = result.get('public_id', '')
    log(f'  Re-uploaded as raw: {new_public_id}')

    # Delete old image resource
    try:
        cloudinary.uploader.destroy(
            _public_id_from_url(url).rsplit('.', 1)[0],  # public_id without ext for image
            resource_type='image',
            invalidate=True,
        )
    except Exception as exc:
        log(f'  WARNING: could not delete old image asset: {exc}')

    # Update the model field to the new public_id
    # django-cloudinary-storage stores the public_id (with extension) as the name
    setattr(obj, field_name, new_public_id)
    obj.save(update_fields=[field_name])
    log(f'  Saved new public_id to DB: {new_public_id}')
    return True


class Command(BaseCommand):
    help = 'Re-upload files stored under Cloudinary /image/upload/ to /raw/upload/'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='Print what would be changed without making any changes.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        # Import here to avoid issues when cloudinary is not installed
        from students.models import Course, CourseMaterial, CourseMaterialFile, AssignmentSubmission

        def log(msg):
            self.stdout.write(msg)

        if dry_run:
            log('=== DRY RUN — no changes will be made ===\n')

        total_fixed = 0

        # --- Course.main_file ---
        log('Checking Course.main_file ...')
        for course in Course.objects.exclude(main_file='').exclude(main_file__isnull=True):
            log(f'Course {course.course_code}:')
            if _fix_field(course, 'main_file', dry_run, log):
                total_fixed += 1

        # --- CourseMaterial.file ---
        log('\nChecking CourseMaterial.file ...')
        for mat in CourseMaterial.objects.exclude(file='').exclude(file__isnull=True):
            log(f'CourseMaterial {mat.material_id} ({mat.title}):')
            if _fix_field(mat, 'file', dry_run, log):
                total_fixed += 1

        # --- CourseMaterialFile.file ---
        log('\nChecking CourseMaterialFile.file ...')
        for mf in CourseMaterialFile.objects.all():
            log(f'CourseMaterialFile {mf.file_id}:')
            if _fix_field(mf, 'file', dry_run, log):
                total_fixed += 1

        # --- AssignmentSubmission.file ---
        log('\nChecking AssignmentSubmission.file ...')
        for sub in AssignmentSubmission.objects.exclude(file='').exclude(file__isnull=True):
            log(f'AssignmentSubmission {sub.submission_id}:')
            if _fix_field(sub, 'file', dry_run, log):
                total_fixed += 1

        action = 'Would fix' if dry_run else 'Fixed'
        log(f'\n=== Done. {action} {total_fixed} file(s). ===')
