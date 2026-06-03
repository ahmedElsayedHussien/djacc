from functools import wraps
from django.contrib.auth.decorators import permission_required as dj_perm
from django.contrib.auth.mixins import PermissionRequiredMixin as DjangoPermissionRequiredMixin
from django.core.exceptions import PermissionDenied


class PermRequiredMixin(DjangoPermissionRequiredMixin):
    """Like PermissionRequiredMixin, but passes the permission name to PermissionDenied."""

    def handle_no_permission(self):
        if self.raise_exception:
            perms = self.get_permission_required()
            raise PermissionDenied(str(', '.join(str(p) for p in perms)))
        return super().handle_no_permission()


def perm_required(perm, login_url=None, raise_exception=False):
    """
    Like @permission_required, but includes the permission name in the
    PermissionDenied exception message when raise_exception=True.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if raise_exception and not request.user.has_perm(perm):
                raise PermissionDenied(str(perm))
            return dj_perm(perm, login_url=login_url, raise_exception=False)(view_func)(request, *args, **kwargs)
        return _wrapped_view
    return decorator
