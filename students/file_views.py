from django.http import HttpResponse, Http404, HttpResponseRedirect
from django.views.decorators.http import require_http_methods
from django.shortcuts import render
from django.conf import settings
from pathlib import Path
import mimetypes
import urllib.parse


def _safe_media_path(file_path: str) -> Path:
    """Resolve a user-provided media path and block path traversal."""
    media_root = Path(settings.MEDIA_ROOT).resolve()
    target = (media_root / file_path).resolve()
    if target != media_root and media_root not in target.parents:
        raise Http404("Invalid path")
    return target


@require_http_methods(["GET"])
def serve_file_view(request, file_path):
    """
    Serve files with proper headers for viewing instead of downloading
    """
    # Construct the full file path
    full_path = _safe_media_path(file_path)
    
    # Check if file exists
    if not full_path.exists():
        raise Http404("File not found")
    
    # Get file info
    file_size = full_path.stat().st_size
    file_name = full_path.name
    file_extension = full_path.suffix.lower()
    
    # Get MIME type
    mime_type, _ = mimetypes.guess_type(str(full_path))
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
        
        # Read file content
        with full_path.open('rb') as f:
            file_content = f.read()
        
        # Create response with proper headers for viewing
        response = HttpResponse(file_content, content_type=mime_type)
        
        # Set headers to encourage viewing instead of downloading
        response['Content-Length'] = file_size
        response['Content-Disposition'] = f'inline; filename="{file_name}"'
        response['X-Content-Type-Options'] = 'nosniff'
        
        # Allow iframe embedding for file viewer
        response['X-Frame-Options'] = 'SAMEORIGIN'
        
        # Add cache headers for better performance
        response['Cache-Control'] = 'public, max-age=3600'
        
        return response
    else:
        # For Office documents and other non-viewable files, redirect to online viewers
        relative_path = full_path.relative_to(Path(settings.MEDIA_ROOT).resolve()).as_posix()
        file_url = request.build_absolute_uri(f'/media/{relative_path}')
        
        # Use Microsoft Office Online viewer for Office documents
        if file_extension in ['.docx', '.doc', '.pptx', '.ppt', '.xlsx', '.xls']:
            office_viewer_url = (
                "https://view.officeapps.live.com/op/embed.aspx?src="
                f"{urllib.parse.quote(file_url, safe=':/?=&')}"
            )
            return HttpResponseRedirect(office_viewer_url)
        
        # For other files, try to serve with inline disposition
        # Read file content
        with full_path.open('rb') as f:
            file_content = f.read()
        
        # Create response with proper headers
        response = HttpResponse(file_content, content_type=mime_type)
        
        # Set headers to encourage viewing instead of downloading
        response['Content-Length'] = file_size
        response['Content-Disposition'] = f'inline; filename="{file_name}"'
        response['X-Content-Type-Options'] = 'nosniff'
        
        # Allow iframe embedding for file viewer
        response['X-Frame-Options'] = 'SAMEORIGIN'
        
        # Add cache headers for better performance
        response['Cache-Control'] = 'public, max-age=3600'
        
        return response

@require_http_methods(["GET"])
def view_file(request, file_path):
    """
    View file in a new tab with proper embedding
    """
    # Construct the full file path
    full_path = _safe_media_path(file_path)
    
    # Check if file exists
    if not full_path.exists():
        raise Http404("File not found")
    
    file_name = full_path.name
    file_extension = full_path.suffix.lower()
    
    # Get MIME type
    mime_type, _ = mimetypes.guess_type(str(full_path))
    if not mime_type:
        mime_type = 'application/octet-stream'
    
    # Create the file URL
    relative_path = full_path.relative_to(Path(settings.MEDIA_ROOT).resolve()).as_posix()
    file_url = request.build_absolute_uri(f'/media/{relative_path}')
    
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
