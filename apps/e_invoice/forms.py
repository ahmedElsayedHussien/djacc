from django import forms
from .models import CompanySettings, EInvoiceConfig, Certificate

class CompanySettingsForm(forms.ModelForm):
    class Meta:
        model = CompanySettings
        fields = '__all__'
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
        }

class EInvoiceConfigForm(forms.ModelForm):
    class Meta:
        model = EInvoiceConfig
        fields = ['environment', 'api_base_url', 'client_id', 'client_secret', 'auto_submit', 'timeout_seconds', 'is_active']
        widgets = {
            'client_secret': forms.PasswordInput(render_value=True),
        }

class CertificateForm(forms.ModelForm):
    class Meta:
        model = Certificate
        fields = ['name', 'certificate_file', 'password_encrypted', 'valid_until', 'is_active', 'is_default']
        widgets = {
            'valid_until': forms.DateInput(attrs={'type': 'date'}),
            'password_encrypted': forms.PasswordInput(render_value=True),
        }
