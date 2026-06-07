from datetime import date
from django import forms
from django.core.exceptions import ValidationError
from .models import CompanySettings, EInvoiceConfig, Certificate

class CompanySettingsForm(forms.ModelForm):
    class Meta:
        model = CompanySettings
        fields = [
            'is_active',
            'company_name_ar', 'company_name_en', 'tax_id',
            'commercial_register', 'VAT_number',
            'address', 'branch_code', 'governorate', 'region_city',
            'phone', 'email',
            'document_type_issue',
        ]
        labels = {
            'is_active': 'مفعلة',
            'company_name_ar': 'اسم الشركة (عربي)',
            'company_name_en': 'اسم الشركة (إنجليزي)',
            'tax_id': 'الرقم الضريبي',
            'commercial_register': 'السجل التجاري',
            'VAT_number': 'رقم تسجيل VAT',
            'address': 'العنوان',
            'branch_code': 'كود الفرع',
            'governorate': 'المحافظة',
            'region_city': 'المنطقة / المدينة',
            'phone': 'الهاتف',
            'email': 'البريد الإلكتروني',
            'document_type_issue': 'نوع إصدار المستندات',
        }
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
        }

    def clean_tax_id(self):
        tid = self.cleaned_data.get('tax_id')
        if tid and not tid.isdigit():
            raise ValidationError('الرقم الضريبي يجب أن يحتوي على أرقام فقط')
        if tid and len(tid) < 9:
            raise ValidationError('الرقم الضريبي يجب أن يكون 9 أرقام على الأقل')
        return tid

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone and not phone.strip():
            raise ValidationError('رقم الهاتف مطلوب')
        return phone

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and not email.strip():
            raise ValidationError('البريد الإلكتروني مطلوب')
        return email

    def clean(self):
        cleaned = super().clean()
        is_active = cleaned.get('is_active')
        if is_active:
            required = ['company_name_ar', 'tax_id', 'address', 'governorate', 'region_city', 'phone', 'email']
            for field in required:
                if not cleaned.get(field):
                    self.add_error(field, 'هذا الحقل مطلوب عند تفعيل الإعدادات')
        return cleaned

class EInvoiceConfigForm(forms.ModelForm):
    class Meta:
        model = EInvoiceConfig
        fields = [
            'environment', 'api_base_url', 'client_id', 'client_secret',
            'security_token', 'auto_submit', 'timeout_seconds', 'is_active',
        ]
        labels = {
            'environment': 'البيئة (تجريبي / إنتاجي)',
            'api_base_url': 'رابط API الأساسي',
            'client_id': 'معرّف العميل (Client ID)',
            'client_secret': 'المفتاح السري (Client Secret)',
            'security_token': 'رمز الأمان (Token)',
            'auto_submit': 'إرسال تلقائي للفاتورة الإلكترونية',
            'timeout_seconds': 'مهلة الاتصال (ثانية)',
            'is_active': 'مفعلة',
        }
        widgets = {
            'client_secret': forms.PasswordInput(),
            'security_token': forms.PasswordInput(),
        }

    def clean_timeout_seconds(self):
        t = self.cleaned_data.get('timeout_seconds')
        if t is not None and (t < 1 or t > 300):
            raise forms.ValidationError('مهلة الاتصال يجب أن تكون بين 1 و 300 ثانية')
        return t

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('is_active'):
            required = ['api_base_url', 'client_id', 'client_secret']
            for field in required:
                if not cleaned.get(field):
                    self.add_error(field, 'هذا الحقل مطلوب عند تفعيل الإعدادات')
        return cleaned

class CertificateForm(forms.ModelForm):
    class Meta:
        model = Certificate
        fields = [
            'name', 'certificate_file', 'password_encrypted',
            'issued_to', 'issued_by', 'valid_from', 'valid_until',
            'serial_number', 'is_active', 'is_default',
        ]
        labels = {
            'name': 'اسم الشهادة',
            'certificate_file': 'ملف الشهادة (.p12 / .pfx)',
            'password_encrypted': 'كلمة مرور الشهادة',
            'issued_to': 'صادرة إلى',
            'issued_by': 'صادرة عن',
            'valid_from': 'سارية من',
            'valid_until': 'سارية حتى',
            'serial_number': 'الرقم التسلسلي',
            'is_active': 'نشطة',
            'is_default': 'افتراضية',
        }
        widgets = {
            'valid_from': forms.DateInput(attrs={'type': 'date'}),
            'valid_until': forms.DateInput(attrs={'type': 'date'}),
            'password_encrypted': forms.PasswordInput(),
        }

    def clean_valid_from(self):
        v = self.cleaned_data.get('valid_from')
        if v and v > date.today():
            raise ValidationError('تاريخ بداية الصلاحية لا يمكن أن يكون في المستقبل')
        return v

    def clean_valid_until(self):
        v = self.cleaned_data.get('valid_until')
        if v and v < date.today():
            raise ValidationError('تاريخ انتهاء الشهادة يجب أن يكون في المستقبل')
        return v

    def clean_certificate_file(self):
        f = self.cleaned_data.get('certificate_file')
        if f and not f.name.endswith('.p12') and not f.name.endswith('.pfx'):
            raise ValidationError('يجب رفع ملف شهادة بصيغة P12 أو PFX')
        return f

    def clean(self):
        cleaned = super().clean()
        valid_from = cleaned.get('valid_from')
        valid_until = cleaned.get('valid_until')
        is_default = cleaned.get('is_default')
        is_active = cleaned.get('is_active')

        if valid_from and valid_until and valid_from >= valid_until:
            raise ValidationError('تاريخ بداية الصلاحية يجب أن يكون قبل تاريخ الانتهاء')
        if is_default and not is_active:
            raise ValidationError('الشهادة الافتراضية يجب أن تكون نشطة')
        return cleaned
