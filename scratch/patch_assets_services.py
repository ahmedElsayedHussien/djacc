import re

def main():
    file_path = 'apps/assets/services.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    # 1. _get_or_create_account lock
    old_get_create = """def _get_or_create_account(code, name, parent_code, account_type):
    \"\"\"مساعد لجلب أو إنشاء حساب محاسبي للأرصدة الافتتاحية\"\"\"
    parent = Account.objects.select_for_update().get(code=parent_code)
    
    acc = Account.objects.filter(code=code).first()
    if not acc:
        acc = Account.objects.create(
            code=code,
            name=name,
            parent=parent,
            account_type=account_type,
            is_leaf=True
        )
    return acc"""
    new_get_create = """def _get_or_create_account(code, name, parent_code, account_type):
    \"\"\"مساعد لجلب أو إنشاء حساب محاسبي للأرصدة الافتتاحية\"\"\"
    parent = Account.objects.get(code=parent_code)
    
    acc, created = Account.objects.get_or_create(
        code=code,
        defaults={
            'name': name,
            'parent': parent,
            'account_type': account_type,
            'is_leaf': True
        }
    )
    return acc"""
    content = content.replace(old_get_create, new_get_create)

    # 2. register_asset duplicate check
    old_register = """    @staticmethod
    @transaction.atomic
    def register_asset(asset: Asset, offset_account, created_by, entry_date=None) -> None:
        \"\"\"
        إنشاء القيد الافتتاحي للأصل وتفعيل حالته.
        - مدين: حساب الأصل (بتكلفة الشراء)
        - دائن: حساب المقابل (offset_account) بتكلفة الشراء
        - مدين: حساب المقابل (بمجمع الإهلاك الافتتاحي إن وجد)
        - دائن: حساب مجمع الإهلاك (بمجمع الإهلاك الافتتاحي إن وجد)
        \"\"\"
        if entry_date is None:"""
    new_register = """    @staticmethod
    @transaction.atomic
    def register_asset(asset: Asset, offset_account, created_by, entry_date=None) -> None:
        \"\"\"
        إنشاء القيد الافتتاحي للأصل وتفعيل حالته.
        - مدين: حساب الأصل (بتكلفة الشراء)
        - دائن: حساب المقابل (offset_account) بتكلفة الشراء
        - مدين: حساب المقابل (بمجمع الإهلاك الافتتاحي إن وجد)
        - دائن: حساب مجمع الإهلاك (بمجمع الإهلاك الافتتاحي إن وجد)
        \"\"\"
        from django.contrib.contenttypes.models import ContentType
        from apps.core.models import JournalEntry
        ctype = ContentType.objects.get_for_model(asset)
        
        if JournalEntry.objects.filter(
            content_type=ctype, 
            object_id=asset.pk, 
            description__startswith='قيد تسجيل أصل ثابت'
        ).exists():
            raise ValueError("تم تسجيل القيود المحاسبية لهذا الأصل مسبقاً.")

        if entry_date is None:"""
    content = content.replace(old_register, new_register)

    # 3. dispose_asset negative value check and select_for_update
    old_dispose = """    @staticmethod
    @transaction.atomic
    def dispose_asset(asset: Asset, disposal_date: date, disposal_value: Decimal, offset_account, created_by) -> JournalEntry:
        \"\"\"
        إهلاك أو استبعاد الأصل (البيع أو التخريد).
        يتم إقفال حساب الأصل ومجمع الإهلاك، وإثبات قيمة البيع (إن وجدت) وحساب الأرباح/الخسائر الرأسمالية.
        \"\"\"
        if asset.status == Asset.Status.DISPOSED:
            raise ValueError("الأصل مستبعد بالفعل.")"""
    new_dispose = """    @staticmethod
    @transaction.atomic
    def dispose_asset(asset: Asset, disposal_date: date, disposal_value: Decimal, offset_account, created_by) -> JournalEntry:
        \"\"\"
        إهلاك أو استبعاد الأصل (البيع أو التخريد).
        يتم إقفال حساب الأصل ومجمع الإهلاك، وإثبات قيمة البيع (إن وجدت) وحساب الأرباح/الخسائر الرأسمالية.
        \"\"\"
        asset = Asset.objects.select_for_update().get(pk=asset.pk)
        if asset.status == Asset.Status.DISPOSED:
            raise ValueError("الأصل مستبعد بالفعل.")
            
        if disposal_value < Decimal('0'):
            raise ValueError("قيمة الاستبعاد (البيع) لا يمكن أن تكون سالبة.")"""
    content = content.replace(old_dispose, new_dispose)

    # 4. run_depreciation target date check
    old_run_dep = """    @staticmethod
    @transaction.atomic
    def run_depreciation(target_date: date, created_by) -> int:
        \"\"\"
        تنفيذ عملية الإهلاك حتى التاريخ المحدد لكل الأصول النشطة.
        \"\"\"
        active_assets = Asset.objects.select_for_update().filter(status=Asset.Status.ACTIVE)"""
    new_run_dep = """    @staticmethod
    @transaction.atomic
    def run_depreciation(target_date: date, created_by) -> int:
        \"\"\"
        تنفيذ عملية الإهلاك حتى التاريخ المحدد لكل الأصول النشطة.
        \"\"\"
        from django.utils import timezone
        if target_date > timezone.now().date():
            raise ValueError("لا يمكن تشغيل الإهلاك لتاريخ في المستقبل.")
        
        active_assets = Asset.objects.select_for_update().filter(status=Asset.Status.ACTIVE)"""
    content = content.replace(old_run_dep, new_run_dep)

    # 5. create_category_with_accounts missing account exception handling
    old_create_cat = """        # 1. تحديد الحسابات الأب
        fixed_assets_parent = Account.objects.get(code='12')
        acc_dep_parent = Account.objects.get(code='129')
        # حساب المصروف (الإهلاك) في شجرة المصروفات مثلا (51)
        expense_parent = Account.objects.get(code='51')"""
    new_create_cat = """        # 1. تحديد الحسابات الأب
        try:
            fixed_assets_parent = Account.objects.get(code='12')
            acc_dep_parent = Account.objects.get(code='129')
            # حساب المصروف (الإهلاك) في شجرة المصروفات مثلا (51)
            expense_parent = Account.objects.get(code='51')
        except Account.DoesNotExist:
            raise ValueError("الحسابات الرئيسية للأصول الثابتة (12) ومجمع الإهلاك (129) أو المصروفات (51) غير موجودة. يرجى تهيئة شجرة الحسابات أولاً.")"""
    content = content.replace(old_create_cat, new_create_cat)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Services patched.")

if __name__ == '__main__':
    main()
