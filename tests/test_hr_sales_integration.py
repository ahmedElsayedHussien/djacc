from django.test import TransactionTestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from apps.core.models import Account, AccountType
from apps.hr.models import Employee, Department, JobTitle
from apps.sales.models import SalesRepresentative
from apps.inventory.models import Warehouse
from apps.treasury.models import CashBox
from django.utils import timezone

User = get_user_model()

class HRSalesIntegrationTest(TransactionTestCase):
    def setUp(self):
        # 1. Setup default groups
        self.sales_group = Group.objects.create(name='مبيعات')
        
        # 2. Setup standard superuser/user
        self.user = User.objects.create_superuser(username='admin_test', password='password', email='admin_test@test.com')
        
        # 3. Setup parent accounts
        Account.objects.get_or_create(code='1111', name='Cash Boxes Parent', account_type=AccountType.ASSET, is_leaf=False)
        Account.objects.get_or_create(code='1134', name='Rep Inventories Parent', account_type=AccountType.ASSET, is_leaf=False)
        Account.objects.get_or_create(code='1141', name='Rep Receivables Parent', account_type=AccountType.ASSET, is_leaf=False)
        
        # 4. Setup Department and JobTitle
        self.department = Department.objects.create(name='المبيعات')
        self.rep_job_title = JobTitle.objects.create(name='مندوب مبيعات', department=self.department)
        self.other_job_title = JobTitle.objects.create(name='محاسب', department=self.department)
        
    def test_employee_creation_auto_creates_sales_representative(self):
        """Test that creating a 'مندوب مبيعات' employee with a user automatically creates a SalesRepresentative, Warehouse, CashBox, and adds them to the 'مبيعات' group."""
        # Create a user for the employee
        rep_user = User.objects.create_user(username='rep_user_1', password='password', email='rep1@test.com')
        
        # Create employee
        employee = Employee.objects.create(
            user=rep_user,
            first_name='Ahmad',
            last_name='Elsayed',
            national_id='12345678901234',
            phone='01012345678',
            department=self.department,
            job_title=self.rep_job_title,
            hiring_date=timezone.now().date(),
            basic_salary=5000,
        )
        
        # Verify SalesRepresentative exists
        self.assertTrue(SalesRepresentative.objects.filter(employee=employee).exists())
        rep = SalesRepresentative.objects.get(employee=employee)
        
        # Verify Warehouse and CashBox are created and linked
        self.assertIsNotNone(rep.warehouse)
        self.assertIsNotNone(rep.cash_box)
        self.assertIn(employee.first_name, rep.warehouse.name)
        self.assertIn(employee.first_name, rep.cash_box.name)
        
        # Verify user is assigned to the sales group and has is_staff
        self.assertTrue(rep_user.groups.filter(name='مبيعات').exists())
        self.assertTrue(rep_user.is_staff)

    def test_employee_without_user_does_not_create_sales_representative_until_linked(self):
        """Test that an employee without a user is NOT auto-created as a SalesRepresentative, but once linked, they are."""
        employee = Employee.objects.create(
            first_name='Samer',
            last_name='Hassan',
            national_id='12345678901235',
            phone='01012345679',
            department=self.department,
            job_title=self.rep_job_title,
            hiring_date=timezone.now().date(),
            basic_salary=5000,
        )
        
        # No representative should be created yet
        self.assertFalse(SalesRepresentative.objects.filter(employee=employee).exists())
        
        # Now create and link user
        rep_user = User.objects.create_user(username='rep_user_2', password='password', email='rep2@test.com')
        employee.user = rep_user
        employee.save()
        
        # Now the SalesRepresentative must exist!
        self.assertTrue(SalesRepresentative.objects.filter(employee=employee).exists())
        rep = SalesRepresentative.objects.get(employee=employee)
        self.assertTrue(rep_user.groups.filter(name='مبيعات').exists())
        self.assertTrue(rep_user.is_staff)

    def test_non_sales_representative_employee_is_not_auto_created(self):
        """Test that an employee with another job title (e.g. 'محاسب') does NOT trigger representative creation."""
        other_user = User.objects.create_user(username='accountant_user', password='password', email='acc@test.com')
        employee = Employee.objects.create(
            user=other_user,
            first_name='Maged',
            last_name='Nabil',
            national_id='12345678901236',
            phone='01012345680',
            department=self.department,
            job_title=self.other_job_title,
            hiring_date=timezone.now().date(),
            basic_salary=6000,
        )
        
        # No representative should be created
        self.assertFalse(SalesRepresentative.objects.filter(employee=employee).exists())
