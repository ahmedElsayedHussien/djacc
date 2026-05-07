from django.core.management.base import BaseCommand
from apps.hr.models import Department, JobTitle, LeaveType

class Command(BaseCommand):
    help = 'Setup default HR data (Departments, Job Titles, Leave Types)'

    def handle(self, *args, **options):
        # 1. Departments
        depts = ['الإدارة العامة', 'قسم المحاسبة', 'قسم المبيعات', 'الموارد البشرية', 'تقنية المعلومات']
        for name in depts:
            Department.objects.get_or_create(name=name)
        self.stdout.write(self.style.SUCCESS('Successfully created departments'))

        # 2. Job Titles
        titles = ['مدير عام', 'محاسب', 'مندوب مبيعات', 'أخصائي HR', 'مبرمج', 'مدير مالي']
        for name in titles:
            JobTitle.objects.get_or_create(name=name)
        self.stdout.write(self.style.SUCCESS('Successfully created job titles'))

        # 3. Leave Types
        leaves = [
            ('إجازة سنوية', 21),
            ('إجازة مرضية', 90),
            ('إجازة عارضة', 7),
            ('إجازة وضع', 90),
            ('إجازة بدون مرتب', 0),
        ]
        for name, days in leaves:
            LeaveType.objects.get_or_create(name=name)
        self.stdout.write(self.style.SUCCESS('Successfully created leave types'))
