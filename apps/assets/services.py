import logging
from datetime import date
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from apps.core.services import JournalService, AuditService
from apps.core.models import JournalEntry, Account, AccountType
from .models import Asset, AssetCategory, DepreciationLog

logger = logging.getLogger(__name__)

def _get_or_create_account(code, name, parent_code, account_type):
    """مساعد لجلب أو إنشاء حساب محاسبي للأرصدة الافتتاحية"""
    parent = Account.objects.select_for_update().get(code=parent_code)
    acc = Account.objects.filter(code=code).first()
    if acc:
        return acc
    return Account.objects.create(
        code=code,
        name=name,
        parent=parent,
        account_type=account_type,
        is_leaf=True
    )

class AssetService:

    @staticmethod
    @transaction.atomic
    def register_asset(asset: Asset, offset_account, created_by, entry_date=None) -> None:
        """
        يُنشئ القيود المحاسبية اللازمة عند تسجيل أصل ثابت:
        1. قيد شراء الأصل: DR أصل / CR نقدية أو مورد (أو ح/35 لو افتتاحي)
        2. قيد مجمع الإهلاك الافتتاحي: DR ح/35 / CR مجمع إهلاك
        """
        if entry_date is None:
            entry_date = asset.purchase_date

        asset_account = asset.category.asset_account
        acc_dep_account = asset.category.accumulated_depreciation_account

        # ── 1. قيد تسجيل الأصل ─────────────────────────────────────────
        lines = [
            {
                'account': asset_account,
                'debit': asset.purchase_value,
                'credit': 0,
                'description': f'تسجيل أصل: {asset.name} ({asset.code})'
            },
            {
                'account': offset_account,
                'debit': 0,
                'credit': asset.purchase_value,
                'description': f'مقابل تسجيل أصل: {asset.name} ({asset.code})'
            },
        ]

        JournalService.create_entry(
            date_val=entry_date,
            entry_type=JournalEntry.EntryType.MANUAL,
            description=f'قيد تسجيل أصل ثابت: {asset.name}',
            lines=lines,
            source_document=asset,
            created_by=created_by,
        )

        # ── 2. قيد مجمع الإهلاك الافتتاحي ─────────────────────────────
        if asset.initial_accumulated_depreciation > 0:
            # استخدام حساب الأرصدة الافتتاحية (ح/35 أو ح/34 أرباح مرحلة)
            opening_acc_code = getattr(settings, 'OPENING_BALANCES_ACCOUNT', '35')
            opening_acc = _get_or_create_account(opening_acc_code, 'أرصدة افتتاحية / أرباح مرحلة', '3', AccountType.EQUITY)


            JournalService.create_entry(
                date_val=entry_date,
                entry_type=JournalEntry.EntryType.MANUAL,
                description=f'مجمع إهلاك افتتاحي: {asset.name}',
                lines=[
                    {
                        'account': opening_acc,
                        'debit': asset.initial_accumulated_depreciation,
                        'credit': 0,
                        'description': f'ح/مقابل مجمع إهلاك افتتاحي - {asset.name}'
                    },
                    {
                        'account': acc_dep_account,
                        'debit': 0,
                        'credit': asset.initial_accumulated_depreciation,
                        'description': f'مجمع إهلاك افتتاحي - {asset.name}'
                    },
                ],
                source_document=asset,
                created_by=created_by,
            )


    @staticmethod
    @transaction.atomic
    def dispose_asset(asset: Asset, disposal_date: date, disposal_value: Decimal, offset_account, created_by) -> JournalEntry:
        """
        يستبعد الأصل من النظام ويولد القيد المحاسبي للاستبعاد:
        DR  مجمع الإهلاك (بالكامل)             ← total_depreciation
        DR  البنك / الصندوق (قيمة البيع)        ← disposal_value
        DR  خسائر استبعاد (إن وجدت)            ← loss
        CR  حساب الأصل (بالقيمة التاريخية)    ← purchase_value
        CR  أرباح استبعاد (إن وجدت)            ← gain
        """
        if asset.status == Asset.Status.DISPOSED:
            raise ValueError("الأصل مستبعد بالفعل.")

        total_dep = asset.total_depreciation
        book_value = asset.book_value
        gain_loss = disposal_value - book_value

        asset_account = asset.category.asset_account
        acc_dep_account = asset.category.accumulated_depreciation_account
        
        lines = []
        # 1. إقفال مجمع الإهلاك (مدين)
        if total_dep > 0:
            lines.append({
                'account': acc_dep_account,
                'debit': total_dep,
                'credit': 0,
                'description': f'إقفال مجمع إهلاك أصل مستبعد: {asset.name}'
            })

        # 2. إثبات قيمة البيع (مدين)
        if disposal_value > 0:
            lines.append({
                'account': offset_account,
                'debit': disposal_value,
                'credit': 0,
                'description': f'ثمن بيع أصل ثابت: {asset.name}'
            })

        # 3. إقفال حساب الأصل (دائن بالقيمة التاريخية)
        lines.append({
            'account': asset_account,
            'debit': 0,
            'credit': asset.purchase_value,
            'description': f'إقفال قيمة أصل مستبعد: {asset.name}'
        })

        # 4. معالجة الأرباح أو الخسائر
        if gain_loss < 0:
            # خسارة (مدين)
            loss_code = getattr(settings, 'LOSS_ON_DISPOSAL_ACCOUNT', '5261')
            loss_acc = _get_or_create_account(loss_code, 'خسائر استبعاد أصول ثابتة', '526', AccountType.EXPENSE)
            lines.append({
                'account': loss_acc,
                'debit': abs(gain_loss),
                'credit': 0,
                'description': f'خسائر استبعاد أصل: {asset.name}'
            })
        elif gain_loss > 0:
            # ربح (دائن)
            gain_code = getattr(settings, 'GAIN_ON_DISPOSAL_ACCOUNT', '4210')
            gain_acc = _get_or_create_account(gain_code, 'أرباح رأسمالية (بيع أصول)', '421', AccountType.REVENUE)
            lines.append({
                'account': gain_acc,
                'debit': 0,
                'credit': gain_loss,
                'description': f'أرباح استبعاد أصل: {asset.name}'
            })

        entry = JournalService.create_entry(
            date_val=disposal_date,
            entry_type=JournalEntry.EntryType.MANUAL,
            description=f'قيد استبعاد أصل ثابت: {asset.name}',
            lines=lines,
            source_document=asset,
            created_by=created_by
        )

        asset.status = Asset.Status.DISPOSED
        asset.save(update_fields=['status'])
        
        AuditService.log(created_by, 'Dispose', asset, f'استبعاد أصل بقيمة بيع {disposal_value}')
        return entry

    @staticmethod
    @transaction.atomic
    def run_depreciation(target_date: date, created_by) -> int:
        """
        يجرى حساب وإثبات إهلاك كافة الأصول النشطة حتى التاريخ المحدد (عادة نهاية الشهر).
        تم تحديثها لتستخدم savepoints لضمان استمرارية العملية في حال فشل أصل معين.
        """
        active_assets = Asset.objects.select_for_update().filter(status=Asset.Status.ACTIVE)
        processed_count = 0
        errors = []
        
        for asset in active_assets:
            try:
                with transaction.atomic():
                    # Check if already depreciated for this month
                    month_start = target_date.replace(day=1)
                    if DepreciationLog.objects.filter(asset=asset, date__gte=month_start, date__lte=target_date).exists():
                        continue
                        
                    # Calculate monthly amount
                    annual_rate = asset.depreciation_rate / Decimal('100')
                    monthly_amount = (asset.purchase_value - asset.salvage_value) * annual_rate / Decimal('12')
                    monthly_amount = monthly_amount.quantize(Decimal('0.01'))
                    
                    # Ensure we don't exceed book value
                    remaining_to_depreciate = asset.book_value - asset.salvage_value
                    if monthly_amount > remaining_to_depreciate:
                        monthly_amount = remaining_to_depreciate
                    
                    if monthly_amount <= 0:
                        asset.status = Asset.Status.FULLY_DEPRECIATED
                        asset.save()
                        continue

                    # 1. Create Journal Entry
                    lines = [
                        {
                            'account': asset.category.depreciation_expense_account,
                            'debit': monthly_amount,
                            'credit': 0,
                            'description': f'إهلاك شهر {target_date.month}/{target_date.year} - {asset.name}'
                        },
                        {
                            'account': asset.category.accumulated_depreciation_account,
                            'debit': 0,
                            'credit': monthly_amount,
                            'description': f'مجمع إهلاك - {asset.name}'
                        }
                    ]
                    
                    entry = JournalService.create_entry(
                        date_val=target_date,
                        entry_type=JournalEntry.EntryType.MANUAL,
                        description=f'قيد إهلاك أصول - {target_date.strftime("%B %Y")}',
                        lines=lines,
                        created_by=created_by,
                        source_document=asset
                    )
                    
                    # 2. Record Log
                    DepreciationLog.objects.create(
                        asset=asset,
                        date=target_date,
                        amount=monthly_amount,
                        journal_entry=entry
                    )
                    
                    # 3. Audit Log
                    AuditService.log(created_by, 'Depreciate', asset, f'إثبات إهلاك شهري بقيمة {monthly_amount}')
                    
                    processed_count += 1
            except Exception as e:
                errors.append(f"خطأ في إهلاك الأصل {asset.name}: {str(e)}")

        if errors:
            logger.error("\n".join(errors))
            
        return processed_count

    @staticmethod
    @transaction.atomic
    def create_category_with_accounts(name, depreciation_rate, created_by):
        """
        تنشئ تصنيف جديد مع فحص وجود الحسابات أولاً قبل إنشائها (لتجنب التكرار).
        """
        
        # 1. تحديد الحسابات الأب
        fixed_assets_parent = Account.objects.get(code='12')
        acc_dep_parent = Account.objects.get(code='129')
        try:
            dep_exp_parent = Account.objects.get(code='526')
        except Account.DoesNotExist:
            dep_exp_parent = Account.objects.filter(name__icontains='إهلاك', code__startswith='5').first()
            if not dep_exp_parent:
                dep_exp_parent = Account.objects.get(code='5')

        def get_or_create_account(parent, acc_name, acc_type, initial_type='debit'):
            parent = Account.objects.select_for_update().get(pk=parent.pk)
            existing = Account.objects.filter(parent=parent, name__icontains=acc_name).first()
            if existing:
                return existing
            
            last = Account.objects.filter(parent=parent).order_by('-code').first()
            if last:
                try:
                    suffix = last.code[len(parent.code):]
                    if not suffix:
                        new_code = parent.code + "01"
                    else:
                        suffix_len = len(suffix)
                        next_suffix = str(int(suffix) + 1).zfill(suffix_len)
                        new_code = parent.code + next_suffix
                except ValueError:
                    new_code = parent.code + "01"
            else:
                new_code = parent.code + "01"
                
            return Account.objects.create(
                code=new_code,
                name=acc_name,
                account_type=acc_type,
                parent=parent,
                is_leaf=True,
                initial_balance_type=initial_type
            )

        # 2. الحصول على الحسابات (أو إنشاؤها)
        asset_acc = get_or_create_account(fixed_assets_parent, f"أصول - {name}", AccountType.ASSET)
        acc_dep_acc = get_or_create_account(acc_dep_parent, f"مجمع إهلاك - {name}", AccountType.ASSET, 'credit')
        dep_exp_acc = get_or_create_account(dep_exp_parent, f"مصروف إهلاك - {name}", AccountType.EXPENSE)
        
        # 3. إنشاء التصنيف
        category = AssetCategory.objects.create(
            name=name,
            asset_account=asset_acc,
            accumulated_depreciation_account=acc_dep_acc,
            depreciation_expense_account=dep_exp_acc,
            default_depreciation_rate=depreciation_rate
        )
        
        return category
