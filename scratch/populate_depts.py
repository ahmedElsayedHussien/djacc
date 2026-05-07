import os
import sys
import django

# Add project root to path
sys.path.append(os.getcwd())

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.development')
django.setup()

from apps.hr.models import Department

departments = [
    {
        'name': 'إدارة الموارد البشرية (HR)',
        'type': Department.DepartmentType.HR,
        'description': 'مسؤولة عن التوظيف، التدريب، الأجور والمزايا، وعلاقات الموظفين.'
    },
    {
        'name': 'الإدارة المالية والمحاسبة',
        'type': Department.DepartmentType.ADMIN,
        'description': 'تسجيل المعاملات المالية، إعداد التقارير المالية، التخطيط المالي، وإدارة الضرائب.'
    },
    {
        'name': 'إدارة التسويق والمبيعات',
        'type': Department.DepartmentType.MARKETING,
        'description': 'تطوير استراتيجيات الترويج، تحديد الأسواق المستهدفة، وإدارة علاقات العملاء لتحقيق الأرباح.'
    },
    {
        'name': 'إدارة العمليات والإنتاج',
        'type': Department.DepartmentType.PRODUCTION,
        'description': 'مسؤولة عن تشغيل الشركة، كفاءة الإنتاج، ومراقبة جودة المنتجات والخدمات.'
    },
    {
        'name': 'إدارة تكنولوجيا المعلومات (IT)',
        'type': Department.DepartmentType.IT,
        'description': 'إدارة الأنظمة، الشبكات، البرمجيات، والدعم الفني.'
    },
    {
        'name': 'إدارة البحث والتطوير (R&D)',
        'type': Department.DepartmentType.RD,
        'description': 'تطوير منتجات جديدة وتحسين المنتجات الحالية لتلبية احتياجات السوق.'
    },
    {
        'name': 'إدارة المشتريات والخدمات اللوجستية',
        'type': Department.DepartmentType.PROCUREMENT,
        'description': 'تأمين المواد الخام، وإدارة المخازن وسلاسل الإمداد.'
    },
    {
        'name': 'إدارة الشؤون القانونية والعقود',
        'type': Department.DepartmentType.LEGAL,
        'description': 'تنظيم العقود والاتفاقيات وضمان الامتثال للقوانين.'
    },
    {
        'name': 'إدارة المشاريع',
        'type': Department.DepartmentType.PROJECTS,
        'description': 'دراسة وتنفيذ المشروعات الفنية.'
    },
    {
        'name': 'المكتب الفني',
        'type': Department.DepartmentType.TECH_OFFICE,
        'description': 'إعداد المخططات والتصاميم.'
    },
    {
        'name': 'العلاقات العامة (PR)',
        'type': Department.DepartmentType.PR,
        'description': 'بناء الصورة الذهنية للشركة.'
    },
]

for dept_data in departments:
    dept, created = Department.objects.get_or_create(
        name=dept_data['name'],
        defaults={
            'type': dept_data['type'],
            'description': dept_data['description']
        }
    )
    if created:
        print(f"Created: {dept.name}")
    else:
        dept.type = dept_data['type']
        dept.description = dept_data['description']
        dept.save()
        print(f"Updated: {dept.name}")

print("Done populating departments.")
