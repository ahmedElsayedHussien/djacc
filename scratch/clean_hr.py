import os
import sys

# Set up path to workspace root
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

import django
django.setup()

from apps.hr.models import Department, JobTitle, Employee

def main():
    print("Starting HR data cleanup...")
    print(f"BASE_DIR: {BASE_DIR}")
    
    # 1. Fetch target department for existing employees
    try:
        dept_target = Department.objects.get(name='حسابات')
        print(f"Target department found: {dept_target.name}")
    except Department.DoesNotExist:
        print("Error: Target department 'حسابات' not found!")
        return

    # 2. Reassign all existing employees to 'حسابات'
    employees = Employee.objects.all()
    print(f"Found {employees.count()} employees to reassign.")
    for emp in employees:
        emp.department = dept_target
        emp.save()
        print(f"Reassigned employee {emp.first_name} {emp.last_name} to department 'حسابات'.")

    # 3. Define the list of official departments and job titles to KEEP
    depts_to_keep = [
        'سوبر ادمن', 'مدير حسابات', 'حسابات', 'مدير مبيعات', 'مبيعات',
        'مدير مخازن', 'مخازن', 'مدير it', 'it', 'مدير اداري', 'اداريين',
        'مدير مشتريات', 'مشتريات'
    ]

    jobs_to_keep = [
        'سوبر ادمن', 'مدير حسابات', 'محاسب', 'مدير مبيعات', 'مندوب مبيعات',
        'مدير مخازن', 'أمين مخزن', 'مدير IT', 'تقني IT', 'مدير إداري',
        'موظف إداري', 'مدير مشتريات', 'مسؤول مشتريات'
    ]

    # 4. Delete old departments
    old_depts = Department.objects.exclude(name__in=depts_to_keep)
    old_depts_count = old_depts.count()
    print(f"Deleting {old_depts_count} old departments...")
    for d in old_depts:
        print(f"Deleting department: {d.name}")
        d.delete()

    # 5. Delete old job titles
    old_jobs = JobTitle.objects.exclude(name__in=jobs_to_keep)
    old_jobs_count = old_jobs.count()
    print(f"Deleting {old_jobs_count} old job titles...")
    for j in old_jobs:
        print(f"Deleting job title: {j.name}")
        j.delete()

    print("HR data cleanup completed successfully!")

if __name__ == "__main__":
    main()
