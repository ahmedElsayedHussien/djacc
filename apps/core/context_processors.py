from apps.core.models import SystemNotification

def notifications_processor(request):
    """
    Globally context-inject system notifications for the authenticated user.
    """
    if request.user.is_authenticated:
        unread_notifications = request.user.system_notifications.filter(is_read=False).order_by('-created_at')[:8]
        unread_count = request.user.system_notifications.filter(is_read=False).count()
        return {
            'unread_notifications': unread_notifications,
            'unread_notifications_count': unread_count,
        }
    return {
        'unread_notifications': [],
        'unread_notifications_count': 0,
    }
