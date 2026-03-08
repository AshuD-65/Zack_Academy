from django.http import HttpResponse, Http404, HttpResponseRedirect
from django.views.decorators.http import require_http_methods
from django.shortcuts import render
from django.core.files.storage import default_storage
from pathlib import Path
import mimetypes
import urllib.parse


def _validate_file_path(file_path: str) -> str:
    """Validate user-provided media path and block path traversal."""
    normalized = file_path.replace("\\", "/").lstrip("/")
    if ".." in Path(normalized).parts:
        raise Http404("Invalid path")
    return normalized


@require_http_methods(["GET"])
def serve_file_view(request, file_path):
    """
    Serve files with proper headers for viewing instead of downloading
    """
    storage_path = _validate_file_path(file_path)
    if not default_storage.exists(storage_path):
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
        file_url = default_storage.url(storage_path)
        if file_url.startswith("/"):
            file_url = request.build_absolute_uri(file_url)
        
        # Use Microsoft Office Online viewer for Office documents
        if file_extension in ['.docx', '.doc', '.pptx', '.ppt', '.xlsx', '.xls']:
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
        raise Http404("File not found")

    file_name = Path(storage_path).name
    file_extension = Path(storage_path).suffix.lower()
    
    # Get MIME type
    mime_type, _ = mimetypes.guess_type(file_name)
    if not mime_type:
        mime_type = 'application/octet-stream'

    file_url = default_storage.url(storage_path)
    if file_url.startswith("/"):
        file_url = request.build_absolute_uri(file_url)
    
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
        'file_url': file_url,
        'file_extension': file_extension,
        'mime_type': mime_type,
        'is_viewable': file_extension in viewable_types,
        'course_code': course_code,
        'material_id': material_id,
    }
    
    return render(request, 'students/file_viewer.html', context)
