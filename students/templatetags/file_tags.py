"""
Custom template filter to fix Cloudinary URLs for non-image files.
Cloudinary uses /image/upload/ by default but PDFs/docs need /raw/upload/.

Usage in templates:
    {% load file_tags %}
    {{ course.main_file.url|fix_cloudinary_url }}
    {{ m.file.url|fix_cloudinary_url }}
"""

from django import template
import os

register = template.Library()

IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.svg', '.webp', '.bmp', '.ico', '.tiff'}


@register.filter
def fix_cloudinary_url(url):
    """
    For non-image files on Cloudinary, prefer /raw/upload/ over /image/upload/.
    If the URL already uses /raw/upload/, return as-is.
    """
    if not url or 'cloudinary.com' not in str(url):
        return url

    url = str(url)
    if '/image/upload/' not in url:
        return url  # already /raw/upload/ or unknown

    path_part = url.split('?')[0]
    ext = os.path.splitext(path_part)[1].lower()

    if ext in IMAGE_EXTENSIONS:
        return url  # images are always fine under /image/upload/

    # Replace /image/upload/ with /raw/upload/
    return url.replace('/image/upload/', '/raw/upload/', 1)
