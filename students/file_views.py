from django.conf import settings
from django.http import HttpResponse, Http404, HttpResponseRedirect
from django.views.decorators.http import require_http_methods
from django.shortcuts import render
from django.core.files.storage import default_storage
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
from urllib.parse import urlparse
import ipaddress
import mimetypes
import urllib.parse

OFFICE_VIEWER_EXTENSIONS = {'.docx', '.doc', '.pptx', '.ppt', '.xlsx', '.xls'}


def _validate_file_path(file_path: str) -> str:
    """Validate user-provided media path and block path traversal."""
    normalized = file_path.replace("\\", "/").lstrip("/")

    media_prefix = settings.MEDIA_URL.lstrip("/")
    if normalized.startswith(media_prefix):
        normalized = normalized[len(media_prefix):].lstrip("/")

    if ".." in Path(normalized).parts:
        raise Http404("Invalid path")
    return normalized


def _build_public_file_url(request, storage_path: str) -> str:
    file_url = default_storage.url(storage_path)
    if file_url.startswith("/"):
        file_url = request.build_absolute_uri(file_url)
    return file_url


def _is_publicly_accessible_url(file_url: str) -> bool:
    parsed = urlparse(file_url)
    hostname = parsed.hostname

    if not hostname:
        return False

    localhost_names = {'localhost', '127.0.0.1', '0.0.0.0'}
    if hostname in localhost_names:
        return False

    try:
        ip = ipaddress.ip_address(hostname)
        return ip.is_global
    except ValueError:
        return True


def _get_local_storage_path(storage_path: str) -> str | None:
    try:
        return default_storage.path(storage_path)
    except (AttributeError, NotImplementedError):
        return None


def _find_alternative_storage_path(storage_path: str) -> str | None:
    local_path = _get_local_storage_path(storage_path)
    if not local_path:
        return None
    if os.path.exists(local_path):
        return storage_path
    directory = os.path.dirname(local_path)
    if not os.path.isdir(directory):
        return None

    requested_name = os.path.basename(local_path)
    base_name, ext = os.path.splitext(requested_name)
    matches = []
    for candidate_name in os.listdir(directory):
        if candidate_name == requested_name:
            continue
        if not candidate_name.lower().endswith(ext.lower()):
            continue
        if candidate_name.startswith(base_name) or base_name.startswith(candidate_name):
            matches.append(candidate_name)

    if len(matches) == 1:
        return os.path.relpath(os.path.join(directory, matches[0]), settings.MEDIA_ROOT).replace(os.sep, '/')
    return None


def _preview_cache_path(storage_path: str) -> str:
    source = Path(storage_path)
    return str(Path("generated_previews") / source.with_suffix(".pdf"))


def _convert_office_to_pdf(storage_path: str) -> str | None:
    source_path = _get_local_storage_path(storage_path)
    if not source_path or not os.path.exists(source_path):
        return None

    soffice_path = shutil.which("soffice")
    if not soffice_path:
        return None

    preview_rel_path = _preview_cache_path(storage_path)
    preview_abs_path = _get_local_storage_path(preview_rel_path)
    if not preview_abs_path:
        return None

    os.makedirs(os.path.dirname(preview_abs_path), exist_ok=True)

    if os.path.exists(preview_abs_path):
        try:
            if os.path.getmtime(preview_abs_path) >= os.path.getmtime(source_path):
                return preview_rel_path
        except OSError:
            pass

    with tempfile.TemporaryDirectory() as temp_dir:
        copy_name = Path(source_path).name
        temp_source_path = os.path.join(temp_dir, copy_name)
        shutil.copy2(source_path, temp_source_path)

        command = [
            soffice_path,
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            temp_dir,
            temp_source_path,
        ]

        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            return None

        converted_pdf_path = os.path.join(temp_dir, f"{Path(copy_name).stem}.pdf")
        if not os.path.exists(converted_pdf_path):
            return None

        shutil.copy2(converted_pdf_path, preview_abs_path)

    return preview_rel_path


@require_http_methods(["GET"])
def serve_file_view(request, file_path):
    """
    Serve files with proper headers for viewing instead of downloading
    """
    storage_path = _validate_file_path(file_path)
    if not default_storage.exists(storage_path):
        alternative = _find_alternative_storage_path(storage_path)
        if alternative and default_storage.exists(alternative):
            storage_path = alternative
        else:
            raise Http404("File not found")

    file_name = Path(storage_path).name
    file_extension = Path(storage_path).suffix.lower()

    # Get MIME type
    mime_type, _ = mimetypes.guess_type(file_name)
    if not mime_type:
        mime_type = 'application/octet-stream'
    
    # Define file types that can be viewed in browser
    viewable_types = {
        '.pdf': 'application/pdf',
        '.txt': 'text/plain',
        '.html': 'text/html',
        '.htm': 'text/html',
        '.css': 'text/css',
        '.js': 'application/javascript',
        '.json': 'application/json',
        '.xml': 'application/xml',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.svg': 'image/svg+xml',
        '.webp': 'image/webp',
        '.mp4': 'video/mp4',
        '.webm': 'video/webm',
        '.ogg': 'video/ogg',
        '.mp3': 'audio/mpeg',
        '.wav': 'audio/wav',
        '.csv': 'text/csv',
    }
    
    # Check if file can be viewed in browser
    if file_extension in viewable_types:
        # Force correct MIME type for viewable files
        mime_type = viewable_types[file_extension]
        
        with default_storage.open(storage_path, 'rb') as f:
            file_content = f.read()
        response = HttpResponse(file_content, content_type=mime_type)

        try:
            response['Content-Length'] = default_storage.size(storage_path)
        except Exception:
            pass
        response['Content-Disposition'] = f'inline; filename="{file_name}"'
        response['X-Content-Type-Options'] = 'nosniff'
        
        # Allow iframe embedding for file viewer
        response['X-Frame-Options'] = 'SAMEORIGIN'
        
        response['Cache-Control'] = 'public, max-age=3600'
        return response
    else:
        file_url = _build_public_file_url(request, storage_path)
        
        # Use Microsoft Office Online viewer for Office documents
        if file_extension in OFFICE_VIEWER_EXTENSIONS and _is_publicly_accessible_url(file_url):
            office_viewer_url = (
                "https://view.officeapps.live.com/op/embed.aspx?src="
                f"{urllib.parse.quote(file_url, safe=':/?=&')}"
            )
            return HttpResponseRedirect(office_viewer_url)
        
        with default_storage.open(storage_path, 'rb') as f:
            file_content = f.read()
        response = HttpResponse(file_content, content_type=mime_type)

        try:
            response['Content-Length'] = default_storage.size(storage_path)
        except Exception:
            pass
        response['Content-Disposition'] = f'inline; filename="{file_name}"'
        response['X-Content-Type-Options'] = 'nosniff'
        
        # Allow iframe embedding for file viewer
        response['X-Frame-Options'] = 'SAMEORIGIN'
        
        response['Cache-Control'] = 'public, max-age=3600'
        return response

@require_http_methods(["GET"])
def view_file(request, file_path):
    """
    View file in a new tab with proper embedding
    """
    storage_path = _validate_file_path(file_path)
    if not default_storage.exists(storage_path):
        alternative = _find_alternative_storage_path(storage_path)
        if alternative and default_storage.exists(alternative):
            storage_path = alternative
        else:
            raise Http404("File not found")

    file_name = Path(storage_path).name
    file_extension = Path(storage_path).suffix.lower()
    
    # Get MIME type
    mime_type, _ = mimetypes.guess_type(file_name)
    if not mime_type:
        mime_type = 'application/octet-stream'

    file_url = _build_public_file_url(request, storage_path)
    
    # Define file types that can be viewed in browser
    viewable_types = {
        '.pdf': 'application/pdf',
        '.txt': 'text/plain',
        '.html': 'text/html',
        '.htm': 'text/html',
        '.css': 'text/css',
        '.js': 'application/javascript',
        '.json': 'application/json',
        '.xml': 'application/xml',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.svg': 'image/svg+xml',
        '.webp': 'image/webp',
        '.mp4': 'video/mp4',
        '.webm': 'video/webm',
        '.ogg': 'video/ogg',
        '.mp3': 'audio/mpeg',
        '.wav': 'audio/wav',
        '.csv': 'text/csv',
    }
    
    office_viewer_url = None
    office_viewer_available = False
    local_preview_path = None
    if file_extension in OFFICE_VIEWER_EXTENSIONS:
        office_viewer_available = _is_publicly_accessible_url(file_url)
        if office_viewer_available:
            office_viewer_url = (
                "https://view.officeapps.live.com/op/embed.aspx?src="
                f"{urllib.parse.quote(file_url, safe=':/?=&')}"
            )
        else:
            local_preview_path = _convert_office_to_pdf(storage_path)

    # Extract course code from file path
    course_code = None
    if 'course_materials/' in file_path:
        path_parts = file_path.split('/')
        if len(path_parts) >= 2:
            course_code = path_parts[1]  # course_materials/COURSE_CODE/...
    
    # Get material ID from database if possible
    material_id = None
    if course_code:
        try:
            from .models import CourseMaterial
            material = CourseMaterial.objects.filter(
                file__icontains=file_name,
                course__course_code=course_code
            ).first()
            if material:
                material_id = str(material.material_id)
        except:
            pass
    
    context = {
        'file_name': file_name,
        'file_path': file_path,
        'file_url': file_url,
        'file_extension': file_extension,
        'mime_type': mime_type,
        'is_viewable': file_extension in viewable_types,
        'is_office_document': file_extension in OFFICE_VIEWER_EXTENSIONS,
        'office_viewer_available': office_viewer_available,
        'office_viewer_url': office_viewer_url,
        'local_preview_path': local_preview_path,
        'course_code': course_code,
        'material_id': material_id,
    }
    
    return render(request, 'students/file_viewer.html', context)
