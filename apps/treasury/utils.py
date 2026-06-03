from .models import CashBox

def get_available_cash_boxes(user):
    """Returns queryset of cash boxes accessible to the given user.
    - Superuser: all active
    - Sales rep: their assigned cash box only
    - Other: cash boxes where they are the responsible_user
    """
    if user.is_superuser:
        return CashBox.objects.filter(is_active=True)
    if hasattr(user, 'salesrepresentative') and user.salesrepresentative:
        return CashBox.objects.filter(id=user.salesrepresentative.cash_box_id, is_active=True)
    return CashBox.objects.filter(responsible_user=user, is_active=True)
