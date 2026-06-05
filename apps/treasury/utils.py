from .models import CashBox

def get_available_cash_boxes(user, exclude_rep_boxes=False):
    """Returns queryset of cash boxes accessible to the given user.
    - Superuser: all active (optionally excluding sales rep boxes)
    - Sales rep: their assigned cash box only
    - Other: cash boxes where they are the responsible_user
    """
    if user.is_superuser:
        qs = CashBox.objects.filter(is_active=True)
        if exclude_rep_boxes:
            # Exclude cash boxes that are assigned to any SalesRepresentative
            qs = qs.exclude(salesrepresentative__isnull=False)
        return qs
    if hasattr(user, 'salesrepresentative') and user.salesrepresentative:
        return CashBox.objects.filter(id=user.salesrepresentative.cash_box_id, is_active=True)
    return CashBox.objects.filter(responsible_user=user, is_active=True)
