from django.db import models
from django.conf import settings
from datetime import date

class Department(models.Model):
    """البيانات الأساسية: الهيكل التنظيمي (الإدارات)"""
    class DepartmentType(models.TextChoices):
        PRODUCTION = 'production', 'إنتاج وعمليات'
        SERVICE = 'service', 'خدمات وفني'
        MARKETING = 'marketing', 'تسويق ومبيعات'
        ADMIN = 'admin', 'إداري ومالي'
        HR = 'hr', 'موارد بشرية'
        IT = 'it', 'تكنولوجيا معلومات'
        RD = 'rd', 'بحث وتطوير'
        LEGAL = 'legal', 'شؤون قانونية'
        PROCUREMENT = 'procurement', 'مشتريات ولوجستيات'
        PROJECTS = 'projects', 'إدارة مشاريع'
        TECH_OFFICE = 'technical', 'المكتب الفني'
        PR = 'pr', 'العلاقات العامة'
        OTHER = 'other', 'أخرى'

    name = models.CharField(max_length=100, unique=True, verbose_name="اسم الإدارة")
    type = models.CharField(
        max_length=20, 
        choices=DepartmentType.choices, 
        default=DepartmentType.OTHER,
        verbose_name="نوع القسم/الإدارة"
    )
    description = models.TextField(blank=True, verbose_name="وصف المهام والمسؤوليات")
    manager = models.ForeignKey('Employee', on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_departments', verbose_name="مدير الإدارة")
    parent = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='sub_departments', verbose_name="الإدارة الرئيسية")
    
    # ربط كل إدارة/فرع بمركز تكلفة محاسبي مخصص لها
    cost_center = models.ForeignKey(
        'core.CostCenter',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='departments',
        verbose_name="مركز التكلفة المرتبط"
    )

    class Meta:
        verbose_name = "إدارة"
        verbose_name_plural = "الإدارات"

    def __str__(self):
        return self.name


class JobTitle(models.Model):
    """البيانات الأساسية: المسميات الوظيفية"""
    name = models.CharField(max_length=100, unique=True, verbose_name="المسمى الوظيفي")
    description = models.TextField(blank=True, verbose_name="الوصف الوظيفي")

    class Meta:
        verbose_name = "مسمى وظيفي"
        verbose_name_plural = "المسميات الوظيفية"

    def __str__(self):
        return self.name

class Employee(models.Model):
    """ملف الموظف الشامل: الأساس الذي تبنى عليه كافة العمليات"""
    class ContractType(models.TextChoices):
        FULL_TIME = 'full_time', 'دوام كامل'
        PART_TIME = 'part_time', 'دوام جزئي'
        CONTRACT = 'contract', 'عقد محدد المدة'
        PROBATION = 'probation', 'فترة اختبار'

    class Status(models.TextChoices):
        ACTIVE = 'active', 'على رأس العمل'
        ON_LEAVE = 'on_leave', 'في إجازة'
        SUSPENDED = 'suspended', 'موقوف'
        TERMINATED = 'terminated', 'منهى خدمته'

    # ربط اختياري بمستخدم النظام لتسجيل الدخول وبوابة الخدمة الذاتية (ESS)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='employee_profile')
    
    # البيانات الشخصية
    first_name = models.CharField(max_length=50, verbose_name="الاسم الأول")
    last_name = models.CharField(max_length=50, verbose_name="اسم العائلة")
    national_id = models.CharField(max_length=20, unique=True, verbose_name="الرقم القومي / الإقامة")
    date_of_birth = models.DateField(null=True, blank=True, verbose_name="تاريخ الميلاد")
    phone = models.CharField(max_length=20, blank=True, verbose_name="رقم الهاتف")
    address = models.TextField(blank=True, verbose_name="العنوان")
    
    # البيانات الوظيفية (Org Chart)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name='employees', verbose_name="الإدارة")
    job_title = models.ForeignKey(JobTitle, on_delete=models.PROTECT, related_name='employees', verbose_name="المسمى الوظيفي")
    reports_to = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='subordinates', verbose_name="المدير المباشر")
    
    # تفاصيل العقد
    hiring_date = models.DateField(verbose_name="تاريخ التعيين")
    contract_type = models.CharField(max_length=20, choices=ContractType.choices, default=ContractType.FULL_TIME, verbose_name="نوع العقد")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, verbose_name="الحالة")
    
    # الرواتب
    basic_salary = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="الراتب الأساسي")
    bank_account_number = models.CharField(max_length=50, blank=True, verbose_name="رقم الحساب البنكي (IBAN)")

    # التأمينات الاجتماعية
    has_social_insurance = models.BooleanField(default=True, verbose_name="خاضع للتأمينات الاجتماعية")
    social_insurance_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=11.00,
        verbose_name="نسبة التأمينات (حصة الموظف %)",
        help_text="مثال: 11 تعني 11% — تختلف حسب نوع التأمين (أجر متغير / ثابت / أصحاب أعمال)"
    )

    # ضريبة كسب العمل
    has_taxes = models.BooleanField(default=True, verbose_name="خاضع لضريبة كسب العمل")
    income_tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, default=10.00,
        verbose_name="نسبة ضريبة كسب العمل (%)",
        help_text="النسبة الفعلية للضريبة. في حال تطبيق الشرائح يتم تعديلها يدوياً في قسيمة الراتب."
    )

    class Meta:
        verbose_name = "موظف"
        verbose_name_plural = "الموظفين"

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.job_title})"

class EmployeeDocument(models.Model):
    """إدارة الوثائق: مسوغات التعيين وتنبيهات الصلاحية"""
    class DocumentType(models.TextChoices):
        ID = 'id', 'بطاقة رقم قومي / هوية'
        PASSPORT = 'passport', 'جواز سفر'
        CONTRACT = 'contract', 'عقد العمل'
        CRIMINAL_RECORD = 'criminal_record', 'فيش وتشبيه'
        MEDICAL = 'medical', 'شهادة طبية'
        CERTIFICATE = 'certificate', 'شهادة تخرج / خبرة'
        OTHER = 'other', 'أخرى'

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=20, choices=DocumentType.choices, verbose_name="نوع المستند")
    title = models.CharField(max_length=100, verbose_name="عنوان المستند")
    file = models.FileField(upload_to='hr/documents/', verbose_name="ملف المستند")
    issue_date = models.DateField(null=True, blank=True, verbose_name="تاريخ الإصدار")
    expiry_date = models.DateField(null=True, blank=True, verbose_name="تاريخ الانتهاء")
    is_verified = models.BooleanField(default=False, verbose_name="تمت المراجعة")

    class Meta:
        verbose_name = "مستند الموظف"
        verbose_name_plural = "مستندات الموظفين"

    def __str__(self):
        return f"{self.title} - {self.employee}"

    @property
    def is_expired(self):
        if self.expiry_date:
            return self.expiry_date < date.today()
        return False

# ==========================================
# 2. الحضور والانصراف (Time & Attendance)
# ==========================================

class Shift(models.Model):
    """سياسات الدوام والورديات"""
    name = models.CharField(max_length=100, verbose_name="اسم الوردية")
    start_time = models.TimeField(verbose_name="وقت الحضور")
    end_time = models.TimeField(verbose_name="وقت الانصراف")
    grace_period_minutes = models.PositiveIntegerField(default=15, verbose_name="فترة السماح (دقائق)")
    
    class Meta:
        verbose_name = "وردية عمل"
        verbose_name_plural = "ورديات العمل"

    def __str__(self):
        return f"{self.name} ({self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')})"

class AttendanceRecord(models.Model):
    """سجل الحضور والانصراف اليومي (يمكن ربطه بجهاز البصمة)"""
    class Status(models.TextChoices):
        PRESENT = 'present', 'حاضر'
        ABSENT = 'absent', 'غائب'
        LATE = 'late', 'متأخر'
        EARLY_LEAVE = 'early_leave', 'انصراف مبكر'
        ON_LEAVE = 'on_leave', 'إجازة'

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='attendance_records', verbose_name="الموظف")
    date = models.DateField(verbose_name="التاريخ")
    check_in = models.TimeField(null=True, blank=True, verbose_name="وقت الحضور الفعلي")
    check_out = models.TimeField(null=True, blank=True, verbose_name="وقت الانصراف الفعلي")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PRESENT, verbose_name="الحالة")
    overtime_hours = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="ساعات العمل الإضافي")
    notes = models.CharField(max_length=255, blank=True, verbose_name="ملاحظات")

    class Meta:
        unique_together = ['employee', 'date']
        verbose_name = "سجل حضور وانصراف"
        verbose_name_plural = "سجلات الحضور والانصراف"

    def __str__(self):
        return f"{self.employee} - {self.date}"


# ==========================================
# 4. إدارة الإجازات والمغادرات (Leave Management)
# ==========================================

class LeaveType(models.Model):
    """أنواع الإجازات (اعتيادي، مرضي، عارضة...)"""
    name = models.CharField(max_length=100, verbose_name="نوع الإجازة")
    days_allowed = models.PositiveIntegerField(default=21, verbose_name="الرصيد السنوي (أيام)")
    is_paid = models.BooleanField(default=True, verbose_name="مدفوعة الأجر")
    requires_approval = models.BooleanField(default=True, verbose_name="تتطلب موافقة")

    class Meta:
        verbose_name = "نوع إجازة"
        verbose_name_plural = "أنواع الإجازات"

    def __str__(self):
        return self.name

class LeaveBalance(models.Model):
    """أرصدة الإجازات السنوية لكل موظف"""
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_balances', verbose_name="الموظف")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.CASCADE, verbose_name="نوع الإجازة")
    year = models.PositiveIntegerField(verbose_name="السنة")
    total_days = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="إجمالي الرصيد")
    used_days = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name="الأيام المستهلكة")

    class Meta:
        unique_together = ['employee', 'leave_type', 'year']
        verbose_name = "رصيد إجازات"
        verbose_name_plural = "أرصدة الإجازات"

    @property
    def remaining_days(self):
        return self.total_days - self.used_days

    def __str__(self):
        return f"{self.employee} - {self.leave_type} ({self.year})"

class LeaveRequest(models.Model):
    """طلبات الإجازات من الموظفين"""
    class Status(models.TextChoices):
        PENDING = 'pending', 'قيد الانتظار'
        APPROVED = 'approved', 'موافق عليها'
        REJECTED = 'rejected', 'مرفوضة'
        CANCELLED = 'cancelled', 'ملغاة'

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='leave_requests', verbose_name="الموظف")
    leave_type = models.ForeignKey(LeaveType, on_delete=models.PROTECT, verbose_name="نوع الإجازة")
    start_date = models.DateField(verbose_name="تاريخ البداية")
    end_date = models.DateField(verbose_name="تاريخ النهاية")
    total_days = models.DecimalField(max_digits=5, decimal_places=2, verbose_name="عدد الأيام")
    reason = models.TextField(verbose_name="سبب الإجازة")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name="حالة الطلب")
    
    # سلسلة الموافقات
    applied_on = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ التقديم")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="تمت الموافقة/الرفض بواسطة")
    manager_notes = models.TextField(blank=True, verbose_name="ملاحظات المدير")

    class Meta:
        verbose_name = "طلب إجازة"
        verbose_name_plural = "طلبات الإجازات"

    def __str__(self):
        return f"{self.employee} - {self.leave_type} ({self.start_date})"


# ==========================================
# 3. إدارة الرواتب والأجور (Payroll)
# ==========================================

class PayrollPeriod(models.Model):
    """فترة الرواتب (عادة تكون شهرية)"""
    class Status(models.TextChoices):
        DRAFT = 'draft', 'مسودة'
        APPROVED = 'approved', 'معتمد'
        POSTED = 'posted', 'مرحل (محاسبياً)'

    name = models.CharField(max_length=50, verbose_name="اسم الفترة (مثال: راتب مايو 2026)")
    start_date = models.DateField(verbose_name="تاريخ بداية الفترة")
    end_date = models.DateField(verbose_name="تاريخ نهاية الفترة")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, verbose_name="الحالة")
    journal_entry = models.OneToOneField('core.JournalEntry', null=True, blank=True, on_delete=models.SET_NULL, verbose_name="قيد الرواتب")

    class Meta:
        verbose_name = "فترة رواتب"
        verbose_name_plural = "فترات الرواتب"

    def __str__(self):
        return self.name

class Payslip(models.Model):
    """قسيمة الراتب لكل موظف في فترة معينة"""
    period = models.ForeignKey(PayrollPeriod, on_delete=models.CASCADE, related_name='payslips', verbose_name="فترة الراتب")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='payslips', verbose_name="الموظف")
    
    # تفاصيل الراتب
    basic_salary = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="الراتب الأساسي")
    total_allowances = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="بدلات ثابتة")
    other_additions = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="إضافات أخرى (مكافآت، إلخ)")
    
    total_deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="خصم سلف")
    other_deductions = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="استقطاعات أخرى (جزاءات، غياب)")
    
    # الضرائب والتأمينات
    social_insurance = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="تأمينات اجتماعية (حصة الموظف)")
    income_tax = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="ضريبة كسب العمل")
    
    net_salary = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="صافي الراتب")
    note = models.CharField(max_length=255, blank=True, verbose_name="ملاحظات")
    
    class Meta:
        unique_together = ['period', 'employee']
        verbose_name = "قسيمة راتب"
        verbose_name_plural = "قسائم الرواتب"

    def __str__(self):
        return f"راتب {self.employee} - {self.period.name}"

class PayslipItem(models.Model):
    """بنود إضافية متغيرة لقسيمة الراتب (مكافآت، جزاءات، إلخ)"""
    class ItemType(models.TextChoices):
        ADDITION = 'addition', 'إضافة (استحقاق)'
        DEDUCTION = 'deduction', 'خصم (استقطاع)'

    payslip = models.ForeignKey(Payslip, on_delete=models.CASCADE, related_name='items', verbose_name="قسيمة الراتب")
    name = models.CharField(max_length=100, verbose_name="اسم البند")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="المبلغ")
    item_type = models.CharField(max_length=10, choices=ItemType.choices, verbose_name="نوع البند")

    class Meta:
        verbose_name = "بند قسيمة راتب"
        verbose_name_plural = "بنود قسائم الرواتب"

    def __str__(self):
        return f"{self.get_item_type_display()}: {self.name} - {self.amount}"


# ==========================================
# 6. السلف والعهد العينية (Loans & Assets)
# ==========================================

class Loan(models.Model):
    """طلبات السلف وجدولتها"""
    class Status(models.TextChoices):
        PENDING = 'pending', 'قيد الانتظار'
        APPROVED = 'approved', 'موافق عليها'
        REJECTED = 'rejected', 'مرفوضة'
        PAID = 'paid', 'مسددة بالكامل'

    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='loans', verbose_name="الموظف")
    request_date = models.DateField(auto_now_add=True, verbose_name="تاريخ الطلب")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="مبلغ السلفة")
    installments_count = models.PositiveIntegerField(verbose_name="عدد شهور السداد")
    monthly_installment = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="القسط الشهري")
    start_month = models.DateField(verbose_name="تاريخ بداية الخصم")
    reason = models.TextField(blank=True, verbose_name="سبب السلفة")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name="الحالة")

    class Meta:
        verbose_name = "سلفة"
        verbose_name_plural = "السلف"

    def __str__(self):
        return f"سلفة {self.amount} - {self.employee}"

class LoanInstallment(models.Model):
    """سجل سداد أقساط السلف المرتبط بقسائم الرواتب"""
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name='installments', verbose_name="السلفة")
    payslip = models.ForeignKey('Payslip', on_delete=models.CASCADE, related_name='loan_installments', verbose_name="قسيمة الراتب")
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="المبلغ المخصوم")
    month = models.DateField(verbose_name="شهر القسط")

    class Meta:
        verbose_name = "قسط سلفة"
        verbose_name_plural = "أقساط السلف"
        unique_together = ['loan', 'payslip']

    def __str__(self):
        return f"قسط {self.amount} من {self.loan}"


class EmployeeAsset(models.Model):
    """العهد العينية المسلمة للموظف (لابتوب، سيارة، إلخ)"""
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='assets', verbose_name="الموظف")
    asset_name = models.CharField(max_length=100, verbose_name="اسم العهدة")
    serial_number = models.CharField(max_length=100, blank=True, verbose_name="الرقم التسلسلي")
    delivery_date = models.DateField(verbose_name="تاريخ التسليم")
    return_date = models.DateField(null=True, blank=True, verbose_name="تاريخ الرد")
    is_returned = models.BooleanField(default=False, verbose_name="تم الرد")
    notes = models.TextField(blank=True, verbose_name="ملاحظات وحالة العهدة")

    class Meta:
        verbose_name = "عهدة عينية"
        verbose_name_plural = "العهد العينية"

    def __str__(self):
        return f"{self.asset_name} - {self.employee}"


# ==========================================
# 7. نهاية الخدمة (End of Service - EOS)
# ==========================================

class EndOfService(models.Model):
    """نموذج إخلاء الطرف وحساب نهاية الخدمة"""
    employee = models.OneToOneField(Employee, on_delete=models.CASCADE, related_name='eos_record', verbose_name="الموظف")
    termination_date = models.DateField(verbose_name="تاريخ إنهاء الخدمة")
    reason = models.CharField(max_length=100, verbose_name="سبب الإنهاء (استقالة، إقالة، تقاعد...)")
    
    # Clearance
    assets_returned = models.BooleanField(default=False, verbose_name="تم رد العهد العينية")
    loans_settled = models.BooleanField(default=False, verbose_name="تم تسوية السلف")
    
    # Financials
    severance_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="مكافأة نهاية الخدمة")
    leave_encashment = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="بدل رصيد إجازات")
    total_settlement = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="إجمالي التسوية النهائية")
    
    is_processed = models.BooleanField(default=False, verbose_name="تمت التسوية والمخالصة")

    class Meta:
        verbose_name = "نهاية خدمة"
        verbose_name_plural = "نهاية الخدمة"

    def __str__(self):
        return f"مخالصة {self.employee}"

