from django.db import models
from django.conf import settings
from django.core.validators import MinValueValidator
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from decimal import Decimal


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
    timeout_seconds = models.PositiveIntegerField(default=30, verbose_name="مهلة الانتظار (ثواني)")
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "إعدادات الفاتورة الإلكترونية"
        verbose_name_plural = "إعدادات الفاتورة الإلكترونية"

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
    
    # الملف المشفر
    certificate_file = models.FileField(upload_to='certificates/', verbose_name="ملف الشهادة (P12)")
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

    def __str__(self):
        return f"{self.name} - {self.valid_until}"
    
    @property
    def is_expired(self):
        from django.utils import timezone
        return self.valid_until < timezone.now().date()
    
    @property
    def days_until_expiry(self):
        from django.utils import timezone
        from datetime import date
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
    internal_id = models.CharField(max_length=50, blank=True, verbose_name="الرقم المرجعي الداخلي")
    uuid = models.CharField(max_length=100, blank=True, verbose_name="UUID")
    submission_id = models.CharField(max_length=100, blank=True, verbose_name="معرف الإرسال")
    
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.DRAFT,
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

    def __str__(self):
        return f"{self.internal_id or self.object_id} - {self.get_status_display()}"