from django import forms
from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import ValidationError

PROTECTED_ROLES = ['مدير النظام', 'admin', 'Administrator', 'مدير مالي', 'مدير مبيعات']
ROLE_PERM_FILTER = {'codename__startswith': 'view_'}

class RoleForm(forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.filter(**ROLE_PERM_FILTER),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        required=False,
        label="الصلاحيات (صلاحيات مشاهدة فقط — يتم منح صلاحيات الإضافة والتعديل والحذف لكل مستخدم على حدة)"
    )

    class Meta:
        model = Group
        fields = ['name', 'permissions']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'اسم الدور (مثال: مدير الموارد البشرية)'}),
        }
        labels = {
            'name': 'اسم الدور / الإدارة',
        }

    def clean_name(self):
        name = self.cleaned_data.get('name')
        if name and name.strip() == '':
            raise ValidationError('اسم الدور لا يمكن أن يكون فارغاً')
        return name

ALLOWED_APPS = ['core', 'sales', 'purchases', 'inventory', 'treasury', 'expenses', 'reports', 'hr', 'users', 'auth', 'pos', 'assets', 'e_invoice']

class UserRoleForm(forms.ModelForm):
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        required=False,
        label="الأدوار والصلاحيات الممنوحة"
    )

    user_permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.filter(content_type__app_label__in=ALLOWED_APPS),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        required=False,
        label="صلاحيات فردية إضافية"
    )

    class Meta:
        model = User
        fields = ['groups', 'user_permissions', 'is_active', 'is_staff']
        labels = {
            'is_active': 'حساب مفعل',
            'is_staff': 'موظف (له صلاحية دخول لوحة التحكم)',
        }
        widgets = {
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_staff': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        cleaned = super().clean()
        is_active = cleaned.get('is_active')
        is_staff = cleaned.get('is_staff')
        groups = cleaned.get('groups')
        user_permissions = cleaned.get('user_permissions')

        if is_staff and not is_active:
            raise ValidationError('لا يمكن جعل المستخدم موظف (staff) وحسابه غير مفعل في نفس الوقت')

        if is_staff and not groups and not user_permissions:
            raise ValidationError('الموظف (staff) يجب أن يكون له دور أو صلاحية فردية واحدة على الأقل')

        if not is_staff and not groups and not user_permissions:
            raise ValidationError('المستخدم يجب أن يكون له دور أو صلاحية فردية واحدة على الأقل')

        return cleaned
