from datetime import date
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from decimal import Decimal
from .encrypt import encrypt_value, decrypt_value


class CompanySettings(models.Model):
    """
    إعدادات الشركة للفاتورة الإلكترونية (ETA)
    Tax ID, Commercial Register, Address, Branch info
    """
    class DocumentType(models.TextChoices):
        INVOICE = 'invoice', 'فاتورة'
        CREDIT_NOTE = 'credit_note', 'إشعار دائن'
        DEBIT_NOTE = 'debit_note', 'إشعار مدين'

    is_active = models.BooleanField(default=True, verbose_name="نشط")
    
    # بيانات الشركة الأساسية
    company_name_ar = models.CharField(max_length=200, verbose_name="اسم الشركة (عربي)")
    company_name_en = models.CharField(max_length=200, verbose_name="اسم الشركة (إنجليزي)")
    tax_id = models.CharField(max_length=50, unique=True, verbose_name="الرقم الضريبي")
    commercial_register = models.CharField(max_length=50, verbose_name="السجل التجاري")
    VAT_number = models.CharField(max_length=50, verbose_name="الرقم المرجعي للضريبة")
    
    # العنوان
    address = models.TextField(verbose_name="العنوان")
    branch_code = models.CharField(max_length=10, default='0', verbose_name="كود الفرع")
    governorate = models.CharField(max_length=50, verbose_name="المحافظة")
    region_city = models.CharField(max_length=50, verbose_name="المنطقة/المدينة")
    
    # معلومات الاتصال
    phone = models.CharField(max_length=20, verbose_name="الهاتف")
    email = models.EmailField(verbose_name="البريد الإلكتروني")
    
    # إعدادات الوثيقة
    document_type_issue = models.CharField(
        max_length=20, 
        choices=DocumentType.choices,
        default=DocumentType.INVOICE,
        verbose_name="نوع الوثيقة"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "إعدادات الشركة"
        verbose_name_plural = "إعدادات الشركات"

    def clean(self):
        if self.tax_id and not self.tax_id.isdigit():
            raise ValidationError({'tax_id': 'الرقم الضريبي يجب أن يحتوي على أرقام فقط'})
        if self.tax_id and len(self.tax_id) < 9:
            raise ValidationError({'tax_id': 'الرقم الضريبي يجب أن يكون 9 أرقام على الأقل'})
        if self.is_active:
            required = ['company_name_ar', 'company_name_en', 'tax_id', 'address', 'governorate', 'region_city', 'phone', 'email']
            for field in required:
                val = getattr(self, field, None)
                if not val or (isinstance(val, str) and not val.strip()):
                    raise ValidationError({field: 'هذا الحقل مطلوب عند تفعيل الإعدادات'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.company_name_ar} - {self.tax_id}"


class EInvoiceConfig(models.Model):
    """
    إعدادات الاتصال بـ API مصلحة الضرائب
    """
    class EnvType(models.TextChoices):
        PRODUCTION = 'production', 'إنتاج'
        TEST = 'test', 'اختبار'

    company = models.OneToOneField(
        CompanySettings, 
        on_delete=models.CASCADE,
        related_name='e_invoice_config',
        verbose_name="الشركة"
    )
    
    environment = models.CharField(
        max_length=20,
        choices=EnvType.choices,
        default=EnvType.TEST,
        verbose_name="البيئة"
    )
    
    # API Credentials
    api_base_url = models.URLField(verbose_name="رابط API")
    client_id = models.CharField(max_length=100, verbose_name="Client ID")
    client_secret = models.CharField(max_length=200, verbose_name="Client Secret")
    security_token = models.CharField(max_length=500, blank=True, verbose_name="Security Token")
    
    # إعدادات إضافية
    auto_submit = models.BooleanField(default=False, verbose_name="إرسال تلقائي عند الترحيل")
    timeout_seconds = models.PositiveIntegerField(default=30, verbose_name="مهلة الانتظار (ثواني)", validators=[MinValueValidator(1), MaxValueValidator(300)])
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "إعدادات الفاتورة الإلكترونية"
        verbose_name_plural = "إعدادات الفاتورة الإلكترونية"

    def clean(self):
        if self.is_active:
            if not self.api_base_url:
                raise ValidationError({'api_base_url': 'رابط API مطلوب عند تفعيل الإعدادات'})
            if not self.client_id:
                raise ValidationError({'client_id': 'معرّف العميل مطلوب عند تفعيل الإعدادات'})
            if not self.client_secret:
                raise ValidationError({'client_secret': 'المفتاح السري مطلوب عند تفعيل الإعدادات'})

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.client_secret and not self.client_secret.startswith('gAAAAA'):
            self.client_secret = encrypt_value(self.client_secret)
        if self.security_token and not self.security_token.startswith('gAAAAA'):
            self.security_token = encrypt_value(self.security_token)
        super().save(*args, **kwargs)

    def decrypt_client_secret(self) -> str:
        return decrypt_value(self.client_secret)

    def decrypt_security_token(self) -> str:
        return decrypt_value(self.security_token)

    def __str__(self):
        return f"{self.company.company_name_ar} - {self.get_environment_display()}"


class Certificate(models.Model):
    """
    إدارة الشهادة الرقمية للتوقيع (P12)
    """
    company = models.ForeignKey(
        CompanySettings,
        on_delete=models.CASCADE,
        related_name='certificates',
        verbose_name="الشركة"
    )
    
    name = models.CharField(max_length=100, verbose_name="اسم الشهادة")
    serial_number = models.CharField(max_length=100, blank=True, verbose_name="الرقم التسلسلي")
    
    # الملف المشفر (مخفي عن التحميل العام)
    from django.core.files.storage import FileSystemStorage
    import os
    private_storage = FileSystemStorage(location=os.path.join(settings.BASE_DIR, 'private_media'))
    
    certificate_file = models.FileField(upload_to='certificates/', storage=private_storage, verbose_name="ملف الشهادة (P12)")
    password_encrypted = models.CharField(max_length=500, verbose_name="كلمة المرور (مشفرة)")
    
    # معلومات الشهادة
    issued_to = models.CharField(max_length=200, verbose_name="صادرة لـ")
    issued_by = models.CharField(max_length=200, verbose_name="جهة الإصدار")
    valid_from = models.DateField(verbose_name="صالحة من")
    valid_until = models.DateField(verbose_name="صالحة حتى")
    
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    is_default = models.BooleanField(default=False, verbose_name="افتراضية")
    
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "شهادة رقمية"
        verbose_name_plural = "الشهادات الرقمية"
        constraints = [
            models.UniqueConstraint(
                fields=['company'],
                condition=models.Q(is_default=True),
                name='unique_default_cert_per_company'
            ),
        ]

    def clean(self):
        if self.valid_from and self.valid_until and self.valid_from > self.valid_until:
            raise ValidationError({'valid_from': 'تاريخ بداية الصلاحية يجب أن يكون قبل تاريخ الانتهاء'})
        if self.is_default and not self.is_active:
            raise ValidationError({'is_default': 'الشهادة الافتراضية يجب أن تكون نشطة'})

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.password_encrypted and not self.password_encrypted.startswith('gAAAAA'):
            self.password_encrypted = encrypt_value(self.password_encrypted)
        super().save(*args, **kwargs)

    def decrypt_password(self) -> str:
        return decrypt_value(self.password_encrypted)

    def __str__(self):
        return f"{self.name} - {self.valid_until}"
    
    @property
    def is_expired(self):
        return self.valid_until < timezone.now().date()
    
    @property
    def days_until_expiry(self):
        if self.valid_until:
            return (self.valid_until - date.today()).days
        return 0


class EInvoiceLog(models.Model):
    """
    سجل الفواتير المرسلة للضريبة
    """
    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'
        SUBMITTED = 'submitted', 'مرسلة'
        VALID = 'valid', 'صحيحة'
        INVALID = 'invalid', 'غير صحيحة'
        CANCELLED = 'cancelled', 'ملغاة'
        CANCELLED_CORRECT = 'cancelled_correct', 'ملغاة بتصحيح'

    # العلاقة بالوثيقة المحلية
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    document = GenericForeignKey('content_type', 'object_id')
    
    # البيانات من مصلحة الضرائب
    internal_id = models.CharField(max_length=50, blank=True, db_index=True, verbose_name="الرقم المرجعي الداخلي")
    uuid = models.CharField(max_length=100, blank=True, db_index=True, verbose_name="UUID")
    submission_id = models.CharField(max_length=100, blank=True, verbose_name="معرف الإرسال")
    
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
        verbose_name="الحالة"
    )
    
    # QR Code
    qr_code = models.ImageField(upload_to='qr_codes/', null=True, blank=True, verbose_name="QR Code")
    
    # بيانات إضافية
    raw_request = models.JSONField(null=True, blank=True, verbose_name="الطلب الأصلي")
    raw_response = models.JSONField(null=True, blank=True, verbose_name="الاستجابة")
    error_message = models.TextField(blank=True, verbose_name="رسالة الخطأ")
    
    # التوقيت
    submitted_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت الإرسال")
    validated_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت التحقق")
    
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='e_invoice_logs'
    )

    class Meta:
        verbose_name = "سجل الفاتورة الإلكترونية"
        verbose_name_plural = "سجلات الفاتورة الإلكترونية"
        ordering = ['-created_at']

    def clean(self):
        if self.submitted_at and self.validated_at and self.submitted_at > self.validated_at:
            raise ValidationError({'validated_at': 'وقت التحقق يجب أن يكون بعد وقت الإرسال'})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.internal_id or self.object_id} - {self.get_status_display()}"