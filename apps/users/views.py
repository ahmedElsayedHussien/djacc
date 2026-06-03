from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse_lazy
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth.models import Group, User, Permission
from django.contrib.contenttypes.models import ContentType
from .forms import RoleForm, UserRoleForm

def get_grouped_permissions():
    """تجميع الصلاحيات حسب التطبيق (App) لتسهيل العرض في الواجهة"""
    permissions = Permission.objects.select_related('content_type').all()
    grouped = {}
    for perm in permissions:
        app_label = perm.content_type.app_label
        # نعرض فقط التطبيقات الخاصة بنا زائد بعض تطبيقات النظام الهامة
        allowed_apps = ['core', 'sales', 'purchases', 'inventory', 'treasury', 'expenses', 'reports', 'hr', 'users', 'auth','pos']
        if app_label not in allowed_apps:
            continue
            
        if app_label not in grouped:
            grouped[app_label] = []
        grouped[app_label].append(perm)
    return grouped

# ==========================================
# 1. إدارة الأدوار والصلاحيات (Roles / Groups)
# ==========================================
class RoleListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = Group
    template_name = 'users/roles/list.html'
    context_object_name = 'roles'
    permission_required = 'auth.view_group'
    paginate_by = 25

class RoleCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Group
    form_class = RoleForm
    template_name = 'users/roles/form.html'
    success_url = reverse_lazy('users:role-list')
    permission_required = 'auth.add_group'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['grouped_permissions'] = get_grouped_permissions()
        return context

    def form_valid(self, form):
        messages.success(self.request, 'تم إنشاء الدور بنجاح.')
        return super().form_valid(form)

class RoleUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Group
    form_class = RoleForm
    template_name = 'users/roles/form.html'
    success_url = reverse_lazy('users:role-list')
    permission_required = 'auth.change_group'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['grouped_permissions'] = get_grouped_permissions()
        context['role_permissions'] = list(self.object.permissions.values_list('id', flat=True))
        return context

    def form_valid(self, form):
        messages.success(self.request, 'تم تحديث الدور بنجاح.')
        return super().form_valid(form)

class RoleDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Group
    template_name = 'users/roles/confirm_delete.html'
    success_url = reverse_lazy('users:role-list')
    permission_required = 'auth.delete_group'

    def dispatch(self, request, *args, **kwargs):
        role = self.get_object()
        protected = ['مدير النظام', 'admin', 'Administrator', 'مدير مالي', 'مدير مبيعات']
        if role.name in protected:
            messages.error(request, f'لا يمكن حذف الدور المحمي "{role.name}".')
            return redirect('users:role-list')
        return super().dispatch(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        messages.success(request, 'تم حذف الدور بنجاح.')
        return super().delete(request, *args, **kwargs)

# ==========================================
# 2. إدارة مستخدمي النظام والصلاحيات
# ==========================================
class UserListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    model = User
    template_name = 'users/users/list.html'
    context_object_name = 'users'
    permission_required = 'auth.view_user'
    paginate_by = 25

    def get_queryset(self):
        return User.objects.filter(is_superuser=False).prefetch_related('groups').order_by('username')

class UserRoleUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = User
    form_class = UserRoleForm
    template_name = 'users/users/role_form.html'
    success_url = reverse_lazy('users:user-list')
    permission_required = 'auth.change_user'

    def form_valid(self, form):
        messages.success(self.request, 'تم تحديث أدوار وصلاحيات المستخدم بنجاح.')
        return super().form_valid(form)
