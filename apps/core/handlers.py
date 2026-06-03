from django.shortcuts import render


def handler403(request, exception=None):
    """Custom 403 handler — shows which permission is missing."""
    perm_name = str(exception) if exception else ''
    return render(request, '403.html', {
        'perm_name': perm_name,
        'request_path': request.path,
    }, status=403)
