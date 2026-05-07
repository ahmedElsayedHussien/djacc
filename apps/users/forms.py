from django import forms
from django.contrib.auth.models import Group, Permission, User

class RoleForm(forms.ModelForm):
    permissions = forms.ModelMultipleChoiceField(
        queryset=Permission.objects.all(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        required=False,
        label="الصلاحيات (الرجاء اختيار الصلاحيات المطلوبة لهذا الدور)"
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

class UserRoleForm(forms.ModelForm):
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        required=False,
        label="الأدوار والصلاحيات الممنوحة"
    )

    class Meta:
        model = User
        fields = ['groups', 'is_active', 'is_staff']
        labels = {
            'is_active': 'حساب مفعل',
            'is_staff': 'موظف (له صلاحية دخول لوحة التحكم)',
        }
        widgets = {
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_staff': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
