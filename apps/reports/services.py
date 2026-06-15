from datetime import date, timedelta
from decimal import Decimal
from django.db.models import Sum, Q, F, Func, Value, Count, Case, When, IntegerField, Max, Min, Avg
from django.db.models.functions import TruncMonth, Coalesce
from django.utils import timezone
from apps.core.models import Account, JournalLine, JournalEntry, FiscalYear, AccountType, CostCenter
from apps.sales.models import Customer, SalesInvoice, SalesInvoiceLine, SalesReturn, SalesReturnLine, CustomerReceipt, SalesRepresentative, RepDailySettlement, IntermediaryCompany, Quotation, SalesTarget
from apps.purchases.models import Supplier, PurchaseInvoice, PurchaseInvoiceLine, PurchaseReturn, PurchaseReturnLine, SupplierPayment, PurchaseOrder
from apps.hr.models import Employee, PayrollPeriod, Payslip, LeaveRequest, Loan, Department, AttendanceRecord, EmployeeAsset, EmployeeDocument, EndOfService, LeaveBalance
from apps.inventory.models import Item, ItemLedger, Warehouse, StockVoucher, StockMovement
from apps.expenses.models import Expense, Custody, CustodySettlement
from apps.treasury.models import CashBox, BankAccount, CashTransfer, BankTransaction, BankReconciliation


class ReportService:

    @staticmethod
    def trial_balance(from_date: date, to_date: date) -> list[dict]:
        """
        ميزان المراجعة بالمجاميع والأرصدة (Optimized)
        """
        # 1. Get accounts with OPENING entries to handle initial_balance logic
        # ✅ استثناء القيود الملغية (is_reversed) لمنع الازدواجية عند إعادة توليد القيد الافتتاحي
        opening_entry_accounts = set(JournalLine.objects.filter(
            entry__entry_type=JournalEntry.EntryType.OPENING,
            entry__is_posted=True,
            entry__is_reversed=False
        ).values_list('account_id', flat=True))

        # 2. Bulk aggregate movements before from_date OR explicitly OPENING entries
        # ✅ استثناء القيود الملغية لمنع تراكم أرصدة افتتاحية متعددة
        from django.db.models import Q
        pre_movements = JournalLine.objects.filter(
            entry__is_posted=True,
            entry__is_reversed=False
        ).filter(
            Q(entry__date__lt=from_date) | Q(entry__entry_type=JournalEntry.EntryType.OPENING)
        ).values('account_id').annotate(d=Sum('debit'), c=Sum('credit'))
        pre_map = {m['account_id']: (m['d'] or Decimal('0'), m['c'] or Decimal('0')) for m in pre_movements}

        # 3. Bulk aggregate movements in period (excluding OPENING and reversed entries)
        period_movements = JournalLine.objects.filter(
            entry__is_posted=True,
            entry__is_reversed=False,
            entry__date__range=[from_date, to_date]
        ).exclude(
            entry__entry_type=JournalEntry.EntryType.OPENING
        ).values('account_id').annotate(d=Sum('debit'), c=Sum('credit'))
        period_map = {m['account_id']: (m['d'] or Decimal('0'), m['c'] or Decimal('0')) for m in period_movements}

        # 4. Get all relevant leaf accounts
        accounts = Account.objects.filter(is_active=True, is_leaf=True).order_by('code')
        rows = []
        for account in accounts:
            init_debit = Decimal('0')
            init_credit = Decimal('0')
            if account.id not in opening_entry_accounts:
                if account.initial_balance_type == 'debit': init_debit = account.initial_balance
                else: init_credit = account.initial_balance
            
            pre_d, pre_c = pre_map.get(account.id, (Decimal('0'), Decimal('0')))
            op_debit = init_debit + pre_d
            op_credit = init_credit + pre_c
            
            mov_debit, mov_credit = period_map.get(account.id, (Decimal('0'), Decimal('0')))
            
            total_debit = op_debit + mov_debit
            total_credit = op_credit + mov_credit
            
            if total_debit != 0 or total_credit != 0:
                rows.append({
                    'account': account,
                    'op_debit': op_debit,
                    'op_credit': op_credit,
                    'mov_debit': mov_debit,
                    'mov_credit': mov_credit,
                    'cl_debit': total_debit - total_credit if total_debit > total_credit else 0,
                    'cl_credit': total_credit - total_debit if total_credit > total_debit else 0,
                })
        return rows

    @staticmethod
    def income_statement(from_date: date, to_date: date, cost_center_id=None) -> dict:
        """
        قائمة الدخل متعددة المراحل (Multi-Step Income Statement)
        """
        base_filter = {
            'entry__is_posted': True,
            'entry__is_reversed': False,
            'entry__date__range': [from_date, to_date]
        }
        if cost_center_id:
            base_filter['cost_center_id'] = cost_center_id

        def get_balance(code_prefix, normal_balance):
            data = JournalLine.objects.filter(
                account__code__startswith=code_prefix,
                **base_filter
            ).aggregate(d=Sum('debit'), c=Sum('credit'))
            d = data['d'] or Decimal('0')
            c = data['c'] or Decimal('0')
            if normal_balance == 'credit':
                return c - d
            else:
                return d - c
        
        # Helper function to dynamically get balances for all sub-accounts of a specific parent
        def get_dynamic_section(parent_code, normal_balance):
            try:
                parent_acc = Account.objects.get(code=parent_code)
                children = parent_acc.children.all().order_by('code')
            except Account.DoesNotExist:
                return [], Decimal('0')
            
            items = []
            section_total = Decimal('0')
            for child in children:
                bal = get_balance(child.code, normal_balance)
                if bal != 0:
                    items.append({'name': child.name, 'balance': bal})
                    section_total += bal
            return items, section_total

        # 1. إيرادات المبيعات
        sales = get_balance('411', 'credit') + get_balance('412', 'credit')
        sales_returns = get_balance('413', 'debit') 
        sales_discount = get_balance('414', 'debit') 
        net_sales = sales - sales_returns - sales_discount

        # 2. تكلفة البضاعة المباعة
        cogs_items, cogs_total = get_dynamic_section('51', 'debit')
        gross_profit = net_sales - cogs_total
        
        # 3. مصروفات التشغيل (ديناميكي بالكامل)
        op_expenses_items, total_op_expenses = get_dynamic_section('52', 'debit')
        operating_profit = gross_profit - total_op_expenses
        
        # 4. إيرادات ومصروفات أخرى (ديناميكي بالكامل)
        other_rev_items, total_other_rev = get_dynamic_section('42', 'credit')
        finance_exp_items, total_finance_exp = get_dynamic_section('53', 'debit')
        other_exp_items, total_other_exp = get_dynamic_section('54', 'debit')
        
        net_other = total_other_rev - total_finance_exp - total_other_exp
        net_profit_before_tax = operating_profit + net_other
        
        # 5. الضرائب - مصروف ضريبة الدخل من حساب المصروفات (55)
        tax_exp = get_balance('55', 'debit')
        net_income = net_profit_before_tax - tax_exp
        
        return {
            'sales': sales,
            'sales_returns': sales_returns,
            'sales_discount': sales_discount,
            'net_sales': net_sales,
            
            'cogs_items': cogs_items,
            'cogs_total': cogs_total,
            'gross_profit': gross_profit,
            
            'op_expenses_items': op_expenses_items,
            'total_op_expenses': total_op_expenses,
            'operating_profit': operating_profit,
            
            'other_rev_items': other_rev_items,
            'total_other_rev': total_other_rev,
            
            'finance_exp_items': finance_exp_items,
            'total_finance_exp': total_finance_exp,
            
            'other_exp_items': other_exp_items,
            'total_other_exp': total_other_exp,
            
            'net_other': net_other,
            'net_profit_before_tax': net_profit_before_tax,
            'tax_exp': tax_exp,
            'net_income': net_income,
            
            # توافق مع الشفرة القديمة
            'revenue': net_sales + total_other_rev,
            'expenses': cogs_total + total_op_expenses + total_finance_exp + total_other_exp + tax_exp,
        }

    @staticmethod
    def balance_sheet(as_of_date: date, cost_center_id=None) -> dict:
        """
        المركز المالي (Balance Sheet) - Optimized
        Assets = Liabilities + Equity
        """
        base_filter = {'entry__is_posted': True, 'entry__is_reversed': False, 'entry__date__lte': as_of_date}
        if cost_center_id:
            base_filter['cost_center_id'] = cost_center_id

        # 1. Aggregated movements for all accounts
        movements = JournalLine.objects.filter(**base_filter).values('account_id').annotate(d=Sum('debit'), c=Sum('credit'))
        mov_map = {m['account_id']: (m['d'] or Decimal('0'), m['c'] or Decimal('0')) for m in movements}

        # 2. Get accounts with OPENING entries
        opening_entry_accounts = set(JournalLine.objects.filter(
            entry__entry_type=JournalEntry.EntryType.OPENING,
            entry__is_posted=True,
            entry__is_reversed=False
        ).values_list('account_id', flat=True))

        # Helper to process a group of accounts
        def process_accounts(account_list, is_asset=True):
            result = []
            for acc in account_list:
                debit, credit = mov_map.get(acc.id, (Decimal('0'), Decimal('0')))
                if acc.id not in opening_entry_accounts:
                    if acc.initial_balance_type == 'debit': debit += acc.initial_balance
                    else: credit += acc.initial_balance
                
                # Assets/Expenses: Debit - Credit | Liabilities/Equity/Revenue: Credit - Debit
                balance = (debit - credit) if is_asset else (credit - debit)
                if balance != 0:
                    result.append({'name': acc.name, 'balance': balance})
            return result

        assets = process_accounts(Account.objects.filter(account_type=AccountType.ASSET, is_leaf=True), is_asset=True)
        liabilities = process_accounts(Account.objects.filter(account_type=AccountType.LIABILITY, is_leaf=True), is_asset=False)
        equity = process_accounts(Account.objects.filter(account_type=AccountType.EQUITY, is_leaf=True), is_asset=False)

        # Add Current Period Net Income to Equity
        # Get start date of current fiscal year
        fiscal_year = FiscalYear.objects.filter(start_date__lte=as_of_date, end_date__gte=as_of_date).first()
        start_date = fiscal_year.start_date if fiscal_year else date(as_of_date.year, 1, 1)
        
        income_stmt = ReportService.income_statement(start_date, as_of_date, cost_center_id=cost_center_id)
        net_income = income_stmt['net_income']
        
        if net_income != 0:
            equity.append({'name': 'أرباح/خسائر العام الحالي (غير مقفلة)', 'balance': net_income})

        total_assets = sum(a['balance'] for a in assets)
        total_liabilities = sum(l['balance'] for l in liabilities)
        total_equity = sum(e['balance'] for e in equity)
        
        return {
            'assets': assets,
            'total_assets': total_assets,
            'liabilities': liabilities,
            'total_liabilities': total_liabilities,
            'equity': equity,
            'total_equity': total_equity,
            'is_balanced': total_assets == (total_liabilities + total_equity)
        }

    @staticmethod
    def customer_statement(customer_id: int, from_date: date, to_date: date) -> dict:
        """
        كشف حساب عميل
        """
        customer = Customer.objects.get(id=customer_id)
        account = customer.account
        
        # 1. Check for opening entry
        has_opening = JournalLine.objects.filter(
            account=account,
            entry__entry_type=JournalEntry.EntryType.OPENING,
            entry__is_posted=True,
            entry__is_reversed=False
        ).exists()

        init_debit = Decimal(0)
        init_credit = Decimal(0)
        if not has_opening:
            if account.initial_balance_type == 'debit': init_debit = account.initial_balance
            else: init_credit = account.initial_balance

        # 2. Add movements before from_date
        pre_movements = JournalLine.objects.filter(
            account=account, 
            entry__is_posted=True, 
            entry__is_reversed=False,
            entry__date__lt=from_date
        ).aggregate(d=Sum('debit'), c=Sum('credit'))
        
        opening_balance = (init_debit + (pre_movements['d'] or 0)) - (init_credit + (pre_movements['c'] or 0))
        
        # Movements in period
        movements = JournalLine.objects.filter(
            account=account,
            entry__is_posted=True,
            entry__is_reversed=False,
            entry__date__range=[from_date, to_date]
        ).select_related('entry').order_by('entry__date', 'id')
        
        statement_lines = []
        running_balance = opening_balance
        for mov in movements:
            running_balance += (mov.debit - mov.credit)
            statement_lines.append({
                'date': mov.entry.date,
                'number': str(mov.entry.source_document) if mov.entry.source_document else mov.entry.number,
                'description': mov.description or mov.entry.description,
                'debit': mov.debit,
                'credit': mov.credit,
                'balance': running_balance,
                'entry_id': mov.entry_id,
                'source_url': mov.entry.source_document.get_absolute_url() if mov.entry.source_document and hasattr(mov.entry.source_document, 'get_absolute_url') else (mov.entry.get_absolute_url() if hasattr(mov.entry, 'get_absolute_url') else None)
            })
            
        return {
            'customer': customer,
            'opening_balance': opening_balance,
            'lines': statement_lines,
            'closing_balance': running_balance
        }

    @staticmethod
    def rep_statement(rep_id: int, from_date: date, to_date: date) -> dict:
        """
        كشف حساب مندوب
        """
        rep = SalesRepresentative.objects.get(id=rep_id)
        accounts = []
        if rep.account:
            accounts.append(rep.account)
        if hasattr(rep, 'cash_box') and rep.cash_box and rep.cash_box.account:
            accounts.append(rep.cash_box.account)
            
        if not accounts:
            return {
                'rep': rep,
                'opening_balance': Decimal(0),
                'lines': [],
                'closing_balance': Decimal(0)
            }
        
        init_debit = Decimal(0)
        init_credit = Decimal(0)
        
        for acc in accounts:
            has_opening = JournalLine.objects.filter(
                account=acc,
                entry__entry_type=JournalEntry.EntryType.OPENING,
                entry__is_posted=True,
                entry__is_reversed=False
            ).exists()

            if not has_opening:
                if acc.initial_balance_type == 'debit': init_debit += acc.initial_balance
                else: init_credit += acc.initial_balance

        # 2. Add movements before from_date
        pre_movements = JournalLine.objects.filter(
            account__in=accounts, 
            entry__is_posted=True, 
            entry__is_reversed=False,
            entry__date__lt=from_date
        ).aggregate(d=Sum('debit'), c=Sum('credit'))
        
        opening_balance = (init_debit + (pre_movements['d'] or 0)) - (init_credit + (pre_movements['c'] or 0))
        
        # Movements in period
        movements = JournalLine.objects.filter(
            account__in=accounts,
            entry__is_posted=True,
            entry__is_reversed=False,
            entry__date__range=[from_date, to_date]
        ).select_related('entry').order_by('entry__date', 'id')
        
        statement_lines = []
        running_balance = opening_balance
        for mov in movements:
            running_balance += (mov.debit - mov.credit)
            statement_lines.append({
                'date': mov.entry.date,
                'description': mov.description or mov.entry.description,
                'debit': mov.debit,
                'credit': mov.credit,
                'balance': running_balance,
                'entry_id': mov.entry_id
            })
            
        return {
            'rep': rep,
            'opening_balance': opening_balance,
            'lines': statement_lines,
            'closing_balance': running_balance
        }

    @staticmethod
    def stock_status(warehouse_id=None) -> list[dict]:
        """
        تقرير حالة المخزون
        """
        qs = ItemLedger.objects.select_related('item', 'warehouse', 'item__base_unit', 'item__category')
        
        if warehouse_id:
            qs = qs.filter(warehouse_id=warehouse_id)
            
        total_value = qs.aggregate(total=Sum('total_value'))['total'] or Decimal('0')
        return {
            'items': qs.order_by('warehouse__name', 'item__name'),
            'total_value': total_value
        }


    @staticmethod
    def rep_commission_report(from_date: date, to_date: date) -> list[dict]:
        """
        تقرير عمولات المناديب بناءً على المبيعات (أو التحصيلات)
        """
        reps = SalesRepresentative.objects.filter(is_active=True)
        rows = []
        for rep in reps:
            # Sales for this rep in period
            sales = SalesInvoice.objects.filter(
                sales_rep=rep,
                status='posted',
                date__range=[from_date, to_date]
            ).aggregate(total=Sum('total'))['total'] or 0
            
            commission = (sales * rep.commission_rate / 100)
            
            if sales > 0:
                rows.append({
                    'rep': rep,
                    'total_sales': sales,
                    'commission_rate': rep.commission_rate,
                    'commission_amount': commission})
        return rows

    @staticmethod
    def cost_center_statement(cost_center_id: int, from_date: date, to_date: date) -> dict:
        """
        كشف حساب مركز تكلفة (المصروفات والإيرادات المحملة عليه)
        """
        cost_center = CostCenter.objects.get(id=cost_center_id)
        
        movements = JournalLine.objects.filter(
            cost_center=cost_center,
            entry__is_posted=True,
            entry__is_reversed=False,
            entry__date__range=[from_date, to_date]
        ).select_related('entry', 'account').order_by('entry__date', 'id')
        
        total_debit = Decimal('0')
        total_credit = Decimal('0')
        lines = []
        
        for mov in movements:
            total_debit += mov.debit
            total_credit += mov.credit
            lines.append({
                'date': mov.entry.date,
                'account': mov.account.name,
                'description': mov.description or mov.entry.description,
                'debit': mov.debit,
                'credit': mov.credit,
            })
            
        return {
            'cost_center': cost_center,
            'lines': lines,
            'total_debit': total_debit,
            'total_credit': total_credit,
            'net': total_debit - total_credit # Usually positive means expense, negative means revenue
        }

    @staticmethod
    def account_statement(account_id: int, from_date: date, to_date: date) -> dict:
        """
        كشف حساب (دفتر أستاذ مساعد) لأي حساب في دليل الحسابات
        """
        account = Account.objects.get(id=account_id)
        
        # 1. Opening balance (sum before from_date)
        # Check if there's an OPENING entry for this account
        has_opening_entry = JournalLine.objects.filter(
            account=account,
            entry__entry_type=JournalEntry.EntryType.OPENING,
            entry__is_posted=True,
            entry__is_reversed=False
        ).exists()

        init_debit = Decimal('0')
        init_credit = Decimal('0')
        
        if not has_opening_entry:
            init_debit = account.initial_balance if account.initial_balance_type == 'debit' else Decimal('0')
            init_credit = account.initial_balance if account.initial_balance_type == 'credit' else Decimal('0')

        pre_movements = JournalLine.objects.filter(
            account=account, 
            entry__is_posted=True, 
            entry__is_reversed=False,
            entry__date__lt=from_date
        ).aggregate(d=Sum('debit'), c=Sum('credit'))
        
        op_debit = init_debit + (pre_movements['d'] or Decimal('0'))
        op_credit = init_credit + (pre_movements['c'] or Decimal('0'))
        opening_balance = op_debit - op_credit
        
        # 2. Movements in period
        movements = JournalLine.objects.filter(
            account=account,
            entry__is_posted=True,
            entry__is_reversed=False,
            entry__date__range=[from_date, to_date]
        ).select_related('entry').order_by('entry__date', 'id')
        
        statement_lines = []
        running_balance = opening_balance
        for mov in movements:
            running_balance += (mov.debit - mov.credit)
            statement_lines.append({
                'date': mov.entry.date,
                'entry_number': mov.entry.number,
                'entry_id': mov.entry.id,
                'description': mov.description or mov.entry.description,
                'debit': mov.debit,
                'credit': mov.credit,
                'balance': running_balance
            })
            
        return {
            'account': account,
            'opening_balance': opening_balance,
            'lines': statement_lines,
            'closing_balance': running_balance,
            'net_movement': running_balance - opening_balance
        }

    @staticmethod
    def vat_report(from_date: date, to_date: date, cost_center_id=None) -> dict:
        """
        تقرير ضريبة القيمة المضافة (VAT Report)
        يُظهر: المبيعات + المشتريات + صافي الضريبة المستحقة
        """
        
        base_filter = {
            'entry__is_posted': True,
            'entry__date__range': [from_date, to_date]
        }
        if cost_center_id:
            base_filter['cost_center_id'] = cost_center_id
        
        # 1. Output VAT (المبيعات - ضريبة القيمة المضافة)
        # ضريبة المبيعات = credit - debit (في حسابات ضريبة القيمة المضافة للعمليات البيعية)
        output_vat = JournalLine.objects.filter(
            account__code__startswith='2121',
            entry__entry_type__in=['sale', 'receipt'],
            **base_filter
        ).aggregate(
            credit=Sum('credit'),
            debit=Sum('debit')
        )
        output_vat_amount = (output_vat['credit'] or 0) - (output_vat['debit'] or 0)
        
        # 2. Input VAT (المشتريات - ضريبة القيمة المضافة)
        # ضريبة المشتريات = debit - credit (في عمليات الشراء والمصروفات)
        input_vat = JournalLine.objects.filter(
            account__code__startswith='2121',
            entry__entry_type__in=['purchase', 'payment', 'expense'],
            **base_filter
        ).aggregate(
            debit=Sum('debit'),
            credit=Sum('credit')
        )
        input_vat_amount = (input_vat['debit'] or 0) - (input_vat['credit'] or 0)
        
        # 3. VAT على المبيعات (Output) - تفاصيل (أعداد الفواتير)
        sales_vat = JournalLine.objects.filter(
            account__code__startswith='2121',
            entry__entry_type__in=['sale', 'receipt'],
            **base_filter
        ).values('entry_id').distinct().count()
        
        # 4. VAT على المشتريات (Input) - تفاصيل (أعداد الفواتير)
        purchases_vat = JournalLine.objects.filter(
            account__code__startswith='2121',
            entry__entry_type__in=['purchase', 'payment', 'expense'],
            **base_filter
        ).values('entry_id').distinct().count()
        
        # 5. صافي الضريبة المستحقة (مخرجات - مدخلات)
        net_vat = output_vat_amount - input_vat_amount
        
        return {
            'from_date': from_date,
            'to_date': to_date,
            'output_vat': output_vat_amount,  # ضريبة المبيعات
            'output_vat_count': sales_vat,
            'input_vat': input_vat_amount,     # ضريبة المشتريات
            'input_vat_count': purchases_vat,
            'net_vat': net_vat,                 # الصافي
            'is_payable': net_vat > 0,         # مستحق للضرائب
        }

    @staticmethod
    def wht_report(from_date: date, to_date: date, cost_center_id=None) -> dict:
        """
        تقرير ضريبة الخصم والتحصيل (WHT Report)
        يُظهر: WHT على المبيعات + WHT على المشتريات + صافي القيمة
        """
        
        base_filter = {
            'entry__is_posted': True,
            'entry__date__range': [from_date, to_date]
        }
        if cost_center_id:
            base_filter['cost_center_id'] = cost_center_id
        
        # 1. WHT on Sales (حساب 1122 - مدينة)
        wht_on_sales = JournalLine.objects.filter(
            account__code='1122',
            account__account_type=AccountType.ASSET,
            **base_filter
        ).aggregate(total=Sum('debit'))
        
        # 2. WHT on Purchases (حساب 2123 - دائنة)
        wht_on_purchases = JournalLine.objects.filter(
            account__code='2123',
            account__account_type=AccountType.LIABILITY,
            **base_filter
        ).aggregate(total=Sum('credit'))
        
        sales_amount = wht_on_sales['total'] or 0
        purchases_amount = wht_on_purchases['total'] or 0
        
        # 3. صافي WHT (المبيعات - المشتريات)
        net_wht = sales_amount - purchases_amount
        
        return {
            'from_date': from_date,
            'to_date': to_date,
            'wht_on_sales': sales_amount,
            'wht_on_sales_account': '1122 - ضريبة خصم وتحصيل - مدينة',
            'wht_on_purchases': purchases_amount,
            'wht_on_purchases_account': '2123 - ضريبة خصم وتحصيل - دائنة',
            'net_wht': net_wht,
            'is_receivable': net_wht > 0,  # إذا كان موجب -> مستحق من الضرائب
        }

    @staticmethod
    def inventory_valuation(warehouse_id=None) -> dict:
        """
        تقرير تقييم المخزون المالي
        """
        qs = ItemLedger.objects.select_related('item', 'warehouse', 'item__category')
        if warehouse_id:
            qs = qs.filter(warehouse_id=warehouse_id)
        
        items = qs.order_by('item__name')
        total_value = qs.aggregate(total=Sum('total_value'))['total'] or Decimal('0')
        return {
            'items': items,
            'total_value': total_value,
        }


    @staticmethod
    def reorder_alert_report() -> list[dict]:
        """
        تقرير نواقص المخزون (الأصناف التي وصلت لحد الطلب)
        """
        
        # Annotate items with total current stock
        items = Item.objects.filter(is_active=True).annotate(
            current_stock=Coalesce(Sum('itemledger__quantity_on_hand'), Decimal('0'))
        ).filter(current_stock__lte=F('minimum_stock')).order_by('current_stock')
        
        return items

    @staticmethod
    def item_ledger_report(item_id: int, warehouse_id: int = None, from_date: date = None, to_date: date = None) -> dict:
        """
        كارت الصنف التفصيلي (Stock Card)
        """
        item = Item.objects.get(id=item_id)
        
        qs = StockMovement.objects.filter(item=item).select_related('warehouse')
        if warehouse_id:
            qs = qs.filter(warehouse_id=warehouse_id)
        if from_date:
            qs = qs.filter(date__gte=from_date)
        if to_date:
            qs = qs.filter(date__lte=to_date)
            
        movements = qs.order_by('date', 'id')
        
        # Opening balance logic
        # For a truly accurate item ledger, we need to calculate opening balance before from_date
        opening_qty = Decimal('0')
        if from_date:
            pre_qs = StockMovement.objects.filter(item=item, date__lt=from_date)
            if warehouse_id:
                pre_qs = pre_qs.filter(warehouse_id=warehouse_id)
            opening_qty = pre_qs.aggregate(total=Sum('quantity'))['total'] or Decimal('0')
            
        return {
            'item': item,
            'opening_qty': opening_qty,
            'movements': movements,
        }

    @staticmethod
    def wastage_adjustments_report(from_date: date, to_date: date) -> list[dict]:
        """
        تقرير التوالف والتسويات المخزنية
        """
        vouchers = StockVoucher.objects.filter(
            status='posted',
            date__range=[from_date, to_date]
        ).select_related('warehouse', 'offset_account', 'created_by').prefetch_related('lines__item')
        
        return vouchers

    @staticmethod
    def van_inventory_report(rep_id: int) -> dict:
        """
        تقرير العهدة الحالية للمندوب (جرد السيارة)
        """
        rep = SalesRepresentative.objects.select_related('warehouse').get(id=rep_id)
        
        if not rep.warehouse:
            raise ValueError("هذا المندوب ليس لديه مستودع مرتبط به")
            
        items = ItemLedger.objects.filter(warehouse=rep.warehouse).select_related('item', 'item__category').order_by('item__name')
        total_value = items.aggregate(total=Sum('total_value'))['total'] or Decimal('0')
        
        return {
            'rep': rep,
            'items': items,
            'total_value': total_value
        }


    @staticmethod
    def inventory_turnover_report(from_date: date, to_date: date) -> list[dict]:
        """
        تقرير معدل دوران المخزون
        Turnover = COGS / Average Inventory
        """
        
        # 1. Total COGS per item (from Sales Issues)
        # Assuming movement_type.SALES_ISSUE or calculation based on StockMovement
        cogs_data = StockMovement.objects.filter(
            movement_type=StockMovement.MovementType.SALES_ISSUE,
            date__range=[from_date, to_date]
        ).values('item_id').annotate(total_cogs=Sum('total_cost'), total_qty=Sum('quantity'))
        
        cogs_map = {c['item_id']: abs(c['total_cogs']) for c in cogs_data}
        
        # 2. Average Inventory (Simplified: (Opening + Closing) / 2)
        items = Item.objects.filter(is_active=True)
        results = []
        for item in items:
            cogs = cogs_map.get(item.id, Decimal('0'))
            if cogs == 0: continue # Skip items with no sales
            
            # Closing inventory value
            closing_val = ItemLedger.objects.filter(item=item).aggregate(total=Sum('total_value'))['total'] or Decimal('0')
            
            # Simple turnover
            avg_inv = closing_val # Proxy
            if avg_inv > 0:
                turnover = cogs / avg_inv
                results.append({
                    'item': item,
                    'cogs': cogs,
                    'avg_inventory': avg_inv,
                    'turnover_ratio': turnover
                })
        
        return sorted(results, key=lambda x: x['turnover_ratio'], reverse=True)

    @staticmethod
    def net_sales_profitability_report(from_date, to_date):
        from apps.pos.models import POSOrder
        from apps.inventory.models import StockMovement
        from django.contrib.contenttypes.models import ContentType

        # Gross Sales & Discounts
        sales_data = SalesInvoice.objects.filter(
            status=SalesInvoice.Status.POSTED,
            date__range=[from_date, to_date]
        ).aggregate(
            gross_sales=Sum('subtotal'),
            total_discounts=Sum('discount_amount')
        )
        
        # Returns
        returns_data = SalesReturn.objects.filter(
            status=SalesReturn.Status.POSTED,
            date__range=[from_date, to_date]
        ).aggregate(
            total_returns=Sum('subtotal')
        )
        
        gross_sales = sales_data['gross_sales'] or Decimal('0')
        discounts = sales_data['total_discounts'] or Decimal('0')
        returns = returns_data['total_returns'] or Decimal('0')

        # POS Orders
        pos_orders = POSOrder.objects.filter(
            status__in=[POSOrder.Status.PAID, POSOrder.Status.POSTED],
            date__date__range=[from_date, to_date]
        )
        pos_sales_agg = pos_orders.filter(is_return=False).aggregate(
            gross=Sum('subtotal'),
            discount=Sum('discount')
        )
        pos_returns_agg = pos_orders.filter(is_return=True).aggregate(
            returns=Sum('subtotal')
        )

        pos_gross = pos_sales_agg['gross'] or Decimal('0')
        pos_discount = pos_sales_agg['discount'] or Decimal('0')
        pos_returns = pos_returns_agg['returns'] or Decimal('0')

        gross_sales += pos_gross
        discounts += pos_discount
        returns += pos_returns
        net_sales = gross_sales - discounts - returns
        
        # COGS (from Invoice Lines)
        cogs = SalesInvoiceLine.objects.filter(
            invoice__status=SalesInvoice.Status.POSTED,
            invoice__date__range=[from_date, to_date]
        ).aggregate(
            total_cogs=Sum(F('quantity') * F('cost'))
        )['total_cogs'] or Decimal('0')

        # POS COGS (from StockMovements)
        pos_order_ct = ContentType.objects.get_for_model(POSOrder)
        pos_order_ids = list(pos_orders.values_list('id', flat=True))
        
        pos_cogs_sales = StockMovement.objects.filter(
            content_type=pos_order_ct,
            object_id__in=pos_order_ids,
            movement_type=StockMovement.MovementType.SALES_ISSUE
        ).aggregate(total=Sum('total_cost'))['total'] or Decimal('0')
        
        pos_cogs_returns = StockMovement.objects.filter(
            content_type=pos_order_ct,
            object_id__in=pos_order_ids,
            movement_type=StockMovement.MovementType.SALE_RETURN
        ).aggregate(total=Sum('total_cost'))['total'] or Decimal('0')

        pos_cogs = abs(pos_cogs_sales) - abs(pos_cogs_returns)
        cogs += pos_cogs
        
        gross_profit = net_sales - cogs
        profit_margin = (gross_profit / net_sales * 100) if net_sales > 0 else 0
        
        return {
            'gross_sales': gross_sales,
            'total_discounts': discounts,
            'total_returns': returns,
            'net_sales': net_sales,
            'cogs': cogs,
            'gross_profit': gross_profit,
            'profit_margin': profit_margin
        }

    @staticmethod
    def product_profitability_report(from_date, to_date):
        from apps.pos.models import POSOrder, POSOrderLine
        from apps.inventory.models import StockMovement
        from django.contrib.contenttypes.models import ContentType
        from apps.sales.models import SalesReturnLine
        from django.db.models import ExpressionWrapper, DecimalField
        
        # 1. ERP Invoices (excluding tax)
        lines = SalesInvoiceLine.objects.filter(
            invoice__status=SalesInvoice.Status.POSTED,
            invoice__date__range=[from_date, to_date]
        ).values(
            'item__code', 'item__name', 'item__category__name'
        ).annotate(
            total_qty=Sum('quantity'),
            total_revenue=Sum(F('quantity') * F('unit_price') * (1 - ExpressionWrapper(F('discount_percent') / 100.0, output_field=DecimalField()))),
            total_cost=Sum(F('quantity') * F('cost')),
        )

        # 2. ERP Returns (excluding tax)
        returns = SalesReturnLine.objects.filter(
            sales_return__status=SalesReturn.Status.POSTED,
            sales_return__date__range=[from_date, to_date]
        ).values(
            'item__code'
        ).annotate(
            total_qty=Sum('quantity'),
            total_revenue=Sum(F('quantity') * F('unit_price') * (1 - ExpressionWrapper(F('discount_percent') / 100.0, output_field=DecimalField()))),
            total_cost=Sum(F('quantity') * F('cost')),
        )

        # Get POS orders
        pos_orders = POSOrder.objects.filter(
            status__in=[POSOrder.Status.PAID, POSOrder.Status.POSTED],
            date__date__range=[from_date, to_date]
        )
        pos_order_ids = list(pos_orders.values_list('id', flat=True))

        pos_product_data = {}
        if pos_order_ids:
            # Query POS lines (excluding tax)
            pos_lines = POSOrderLine.objects.filter(
                order_id__in=pos_order_ids
            ).values(
                'item_id', 'item__code', 'item__name', 'item__category__name', 'order__is_return'
            ).annotate(
                total_qty=Sum('qty'),
                subtotal=Sum(F('qty') * F('price') - F('discount'))
            )

            for line in pos_lines:
                item_id = line['item_id']
                if item_id not in pos_product_data:
                    pos_product_data[item_id] = {
                        'item__code': line['item__code'],
                        'item__name': line['item__name'],
                        'item__category__name': line['item__category__name'] or '',
                        'total_qty': Decimal('0'),
                        'total_revenue': Decimal('0'),
                        'total_cost': Decimal('0'),
                    }
                
                coef = Decimal('-1') if line['order__is_return'] else Decimal('1')
                pos_product_data[item_id]['total_qty'] += line['total_qty'] * coef
                pos_product_data[item_id]['total_revenue'] += line['subtotal'] * coef

            # Query POS costs (StockMovements)
            pos_order_ct = ContentType.objects.get_for_model(POSOrder)
            movs = StockMovement.objects.filter(
                content_type=pos_order_ct,
                object_id__in=pos_order_ids,
                movement_type__in=[StockMovement.MovementType.SALES_ISSUE, StockMovement.MovementType.SALE_RETURN]
            ).values('item_id', 'movement_type').annotate(total_cost=Sum('total_cost'))

            pos_costs = {}
            for m in movs:
                item_id = m['item_id']
                if item_id not in pos_costs:
                    pos_costs[item_id] = Decimal('0')
                if m['movement_type'] == StockMovement.MovementType.SALES_ISSUE:
                    pos_costs[item_id] += abs(m['total_cost'])
                elif m['movement_type'] == StockMovement.MovementType.SALE_RETURN:
                    pos_costs[item_id] -= abs(m['total_cost'])

            for item_id, cost_val in pos_costs.items():
                if item_id in pos_product_data:
                    pos_product_data[item_id]['total_cost'] = cost_val

        # Merge ERP Invoices, subtract ERP Returns, and merge POS
        merged_report = {}
        for line in lines:
            code = line['item__code']
            merged_report[code] = {
                'item__code': code,
                'item__name': line['item__name'],
                'item__category__name': line['item__category__name'] or '',
                'total_qty': line['total_qty'],
                'total_revenue': line['total_revenue'] or Decimal('0'),
                'total_cost': line['total_cost'] or Decimal('0'),
            }

        for ret in returns:
            code = ret['item__code']
            if code in merged_report:
                merged_report[code]['total_qty'] -= ret['total_qty']
                merged_report[code]['total_revenue'] -= ret['total_revenue'] or Decimal('0')
                merged_report[code]['total_cost'] -= ret['total_cost'] or Decimal('0')

        for item_id, pdata in pos_product_data.items():
            code = pdata['item__code']
            if code in merged_report:
                merged_report[code]['total_qty'] += pdata['total_qty']
                merged_report[code]['total_revenue'] += pdata['total_revenue']
                merged_report[code]['total_cost'] += pdata['total_cost']
            else:
                merged_report[code] = pdata

        # Recompute profit and sort
        final_list = []
        for code, data in merged_report.items():
            data['profit'] = data['total_revenue'] - data['total_cost']
            final_list.append(data)

        final_list.sort(key=lambda x: x['profit'], reverse=True)
        return final_list

    @staticmethod
    def sales_by_sector_report(from_date, to_date):
        from apps.pos.models import POSOrder
        
        sectors = SalesInvoice.objects.filter(
            status=SalesInvoice.Status.POSTED,
            date__range=[from_date, to_date]
        ).values('customer__sector__name').annotate(
            invoice_count=Count('id'),
            total_sales=Sum('total'),
            total_paid=Sum('paid_amount'),
        ).annotate(
            balance=F('total_sales') - F('total_paid')
        ).order_by('-total_sales')

        # Get POS orders
        pos_orders = POSOrder.objects.filter(
            status__in=[POSOrder.Status.PAID, POSOrder.Status.POSTED],
            date__date__range=[from_date, to_date]
        ).select_related('customer', 'customer__sector')

        pos_sectors = {}
        for order in pos_orders:
            sector_name = None
            if order.customer and order.customer.sector:
                sector_name = order.customer.sector.name
            
            if not sector_name:
                sector_name = "نقاط البيع (مبيعات طيار)"

            if sector_name not in pos_sectors:
                pos_sectors[sector_name] = {
                    'customer__sector__name': sector_name,
                    'invoice_count': 0,
                    'total_sales': Decimal('0'),
                    'total_paid': Decimal('0'),
                }

            coef = Decimal('-1') if order.is_return else Decimal('1')
            pos_sectors[sector_name]['invoice_count'] += 1
            pos_sectors[sector_name]['total_sales'] += order.grand_total * coef
            pos_sectors[sector_name]['total_paid'] += order.grand_total * coef

        # Merge ERP and POS
        merged_sectors = {}
        for sec in sectors:
            name = sec['customer__sector__name'] or "غير محدد"
            merged_sectors[name] = {
                'customer__sector__name': name,
                'invoice_count': sec['invoice_count'],
                'total_sales': sec['total_sales'] or Decimal('0'),
                'total_paid': sec['total_paid'] or Decimal('0'),
            }

        for name, psec in pos_sectors.items():
            if name in merged_sectors:
                merged_sectors[name]['invoice_count'] += psec['invoice_count']
                merged_sectors[name]['total_sales'] += psec['total_sales']
                merged_sectors[name]['total_paid'] += psec['total_paid']
            else:
                merged_sectors[name] = psec

        # Recompute balance and convert to list
        final_list = []
        for name, data in merged_sectors.items():
            data['balance'] = data['total_sales'] - data['total_paid']
            final_list.append(data)

        final_list.sort(key=lambda x: x['total_sales'], reverse=True)
        return final_list

    @staticmethod
    def rep_performance_report_enhanced(from_date, to_date):
        from apps.pos.models import POSOrder
        
        reps = SalesRepresentative.objects.filter(is_active=True)
        results = []
        for rep in reps:
            sales_data = SalesInvoice.objects.filter(
                sales_rep=rep, status=SalesInvoice.Status.POSTED, date__range=[from_date, to_date]
            ).aggregate(
                subtotal=Sum('subtotal'),
                discount=Sum('discount_amount')
            )
            sales = (sales_data['subtotal'] or Decimal('0')) - (sales_data['discount'] or Decimal('0'))
            
            returns = SalesReturn.objects.filter(
                sales_rep=rep, status=SalesReturn.Status.POSTED, date__range=[from_date, to_date]
            ).aggregate(total=Sum('subtotal'))['total'] or Decimal('0')

            # Aggregate POS sales and returns for this rep's user (excluding tax, net of discounts)
            pos_sales_data = POSOrder.objects.filter(
                session__user=rep.user,
                status__in=[POSOrder.Status.PAID, POSOrder.Status.POSTED],
                is_return=False,
                date__date__range=[from_date, to_date]
            ).aggregate(
                subtotal=Sum('subtotal'),
                discount=Sum('discount')
            )
            pos_sales = (pos_sales_data['subtotal'] or Decimal('0')) - (pos_sales_data['discount'] or Decimal('0'))

            pos_returns = POSOrder.objects.filter(
                session__user=rep.user,
                status__in=[POSOrder.Status.PAID, POSOrder.Status.POSTED],
                is_return=True,
                date__date__range=[from_date, to_date]
            ).aggregate(total=Sum('subtotal'))['total'] or Decimal('0')

            sales += pos_sales
            returns += pos_returns
            
            net_sales = sales - returns
            
            target = SalesTarget.objects.filter(
                sales_rep=rep, start_date__lte=to_date, end_date__gte=from_date
            ).aggregate(total=Sum('target_amount'))['total'] or Decimal('0')
            
            achievement = (net_sales / target * 100) if target > 0 else 0
            commission = net_sales * (rep.commission_rate / 100)
            
            results.append({
                'rep': rep,
                'net_sales': net_sales,
                'target': target,
                'achievement': achievement,
                'commission': commission
            })
        return sorted(results, key=lambda x: x['net_sales'], reverse=True)

    @staticmethod
    def customer_aging_summary_report(customer_id=None):
        
        today = timezone.now().date()
        
        customers = Customer.objects.all()
        if customer_id:
            customers = customers.filter(id=customer_id)
            
        aging_results = []
        for cust in customers:
            # Optimized query to find unpaid invoices
            unpaid_invoices = SalesInvoice.objects.filter(
                customer=cust, status=SalesInvoice.Status.POSTED
            ).annotate(
                allocated=Coalesce(Sum('receiptallocation__amount'), Decimal('0'))
            ).annotate(
                remaining=F('total') - F('allocated')
            ).filter(remaining__gt=0)
            
            buckets = {
                'current': Decimal('0'),
                '1_30': Decimal('0'),
                '31_60': Decimal('0'),
                '61_90': Decimal('0'),
                '90_plus': Decimal('0'),
                'total': Decimal('0')
            }
            
            for inv in unpaid_invoices:
                due_date = inv.due_date if inv.due_date else inv.date
                age = (today - due_date).days
                amount = inv.remaining
                buckets['total'] += amount
                if age <= 0: buckets['current'] += amount
                elif age <= 30: buckets['1_30'] += amount
                elif age <= 60: buckets['31_60'] += amount
                elif age <= 90: buckets['61_90'] += amount
                else: buckets['90_plus'] += amount
            
            # Account for unallocated balances (e.g. opening balance, advance receipts)
            unallocated = cust.balance - buckets['total']
            
            if unallocated > 0:
                # Positive unallocated usually means Opening Balance, which is old debt.
                buckets['90_plus'] += unallocated
            else:
                # Negative unallocated usually means Advance Payments or Unapplied Returns.
                buckets['current'] += unallocated
                
            buckets['total'] = cust.balance
            
            if buckets['total'] != 0 or unpaid_invoices.exists():
                aging_results.append({
                    'customer': cust,
                    'buckets': buckets,
                    'balance': cust.balance
                })
        return aging_results

    @staticmethod
    def quotation_analysis_report(from_date, to_date):
        
        qs = Quotation.objects.filter(start_date__range=[from_date, to_date])
        total_count = qs.count()
        total_value = qs.aggregate(total=Sum('total'))['total'] or Decimal('0')
        
        converted_qs = qs.filter(status='invoiced')
        converted_count = converted_qs.count()
        converted_value = converted_qs.aggregate(total=Sum('total'))['total'] or Decimal('0')
        
        cancelled_count = qs.filter(status='cancelled').count()
        
        conversion_rate = (converted_count / total_count * 100) if total_count > 0 else 0
        
        return {
            'total_count': total_count,
            'total_value': total_value,
            'converted_count': converted_count,
            'converted_value': converted_value,
            'cancelled_count': cancelled_count,
            'conversion_rate': conversion_rate
        }
    @staticmethod
    def purchases_summary_report(from_date, to_date):
        
        # Gross Purchases & Discounts
        purchases_data = PurchaseInvoice.objects.filter(
            status=PurchaseInvoice.Status.POSTED,
            date__range=[from_date, to_date]
        ).aggregate(
            gross_purchases=Sum('subtotal'),
            total_discounts=Sum('discount_amount'),
            tax_amount=Sum('tax_amount')
        )
        
        # Returns
        returns_data = PurchaseReturn.objects.filter(
            status=PurchaseReturn.Status.POSTED,
            date__range=[from_date, to_date]
        ).aggregate(
            total_returns=Sum('subtotal'),
            tax_returns=Sum('tax_amount')
        )
        
        gross_purchases = purchases_data['gross_purchases'] or Decimal('0')
        discounts = purchases_data['total_discounts'] or Decimal('0')
        returns = returns_data['total_returns'] or Decimal('0')
        net_purchases = gross_purchases - discounts - returns
        
        input_tax = (purchases_data['tax_amount'] or Decimal('0')) - (returns_data['tax_returns'] or Decimal('0'))
        
        return {
            'gross_purchases': gross_purchases,
            'total_discounts': discounts,
            'total_returns': returns,
            'net_purchases': net_purchases,
            'input_tax': input_tax
        }

    @staticmethod
    def item_purchase_cost_report(from_date, to_date):
        
        report = PurchaseInvoiceLine.objects.filter(
            invoice__status=PurchaseInvoice.Status.POSTED,
            invoice__date__range=[from_date, to_date]
        ).values(
            'item__code', 'item__name', 'item__category__name'
        ).annotate(
            total_qty=Sum('quantity'),
            total_cost=Sum('total'),
            max_price=Max('unit_cost'),
            min_price=Min('unit_cost'),
            avg_price=Avg('unit_cost')
        ).order_by('-total_cost')
        
        return report

    @staticmethod
    def item_price_fluctuation_report(item_id, from_date, to_date):
        from apps.pos.models import POSOrder, POSOrderLine

        if not item_id:
            return []

        purchases = PurchaseInvoiceLine.objects.filter(
            item_id=item_id,
            invoice__status=PurchaseInvoice.Status.POSTED,
            invoice__date__range=[from_date, to_date]
        ).select_related('invoice').order_by('invoice__date', 'id')

        periods = []
        current_period = None

        for line in purchases:
            cost = line.unit_cost
            date_val = line.invoice.date

            if current_period is None:
                current_period = {
                    'start_date': date_val,
                    'cost': cost,
                    'lines': [line]
                }
            elif current_period['cost'] == cost:
                # Same cost, extend the period implicitly by just recording the line
                current_period['lines'].append(line)
            else:
                # Cost changed, close the current period
                current_period['end_date'] = date_val
                periods.append(current_period)
                # Start new period
                current_period = {
                    'start_date': date_val,
                    'cost': cost,
                    'lines': [line]
                }

        if current_period is not None:
            # The last period extends to the end of the report date range
            current_period['end_date'] = to_date
            periods.append(current_period)

        results = []
        for p in periods:
            # Determine Sales during this period
            # If the end_date is the same as the start of the next period, we filter by < end_date for exclusivity,
            # except for the last period where we include the to_date (<= end_date)
            is_last = p is periods[-1]
            end_date_filter = Q(invoice__date__lte=p['end_date']) if is_last else Q(invoice__date__lt=p['end_date'])
            
            sales_data = SalesInvoiceLine.objects.filter(
                Q(item_id=item_id) &
                Q(invoice__status=SalesInvoice.Status.POSTED) &
                Q(invoice__date__gte=p['start_date']) &
                end_date_filter
            ).aggregate(
                total_qty=Sum('quantity'),
                total_revenue=Sum(F('quantity') * F('unit_price'))
            )

            # Query POS Order Lines for the same period
            pos_end_date_filter = Q(order__date__date__lte=p['end_date']) if is_last else Q(order__date__date__lt=p['end_date'])
            pos_lines = POSOrderLine.objects.filter(
                Q(item_id=item_id) &
                Q(order__status__in=[POSOrder.Status.PAID, POSOrder.Status.POSTED]) &
                Q(order__date__date__gte=p['start_date']) &
                pos_end_date_filter
            ).select_related('order')

            erp_qty = sales_data['total_qty'] or Decimal('0')
            erp_rev = sales_data['total_revenue'] or Decimal('0')

            pos_qty = Decimal('0')
            pos_rev = Decimal('0')
            for pl in pos_lines:
                coef = Decimal('-1') if pl.order.is_return else Decimal('1')
                pos_qty += pl.qty * coef
                pos_rev += (pl.qty * pl.price) * coef

            qty = erp_qty + pos_qty
            rev = erp_rev + pos_rev
            avg_selling_price = (rev / qty).quantize(Decimal('0.00')) if qty > 0 else Decimal('0')
            
            unit_profit = avg_selling_price - p['cost'] if qty > 0 else Decimal('0')
            profit_percentage = ((unit_profit / avg_selling_price) * 100).quantize(Decimal('0.00')) if avg_selling_price > 0 else Decimal('0')

            results.append({
                'start_date': p['start_date'],
                'end_date': p['end_date'],
                'purchase_cost': p['cost'],
                'avg_selling_price': avg_selling_price,
                'sales_quantity': qty,
                'unit_profit': unit_profit,
                'profit_percentage': profit_percentage,
                'is_current': is_last
            })

        # Reverse the results so the newest periods appear first
        results.reverse()
        return results

    @staticmethod
    def supplier_balances_report(from_date, to_date):
        
        suppliers = Supplier.objects.all()
        results = []
        for sup in suppliers:
            period_purchases = PurchaseInvoice.objects.filter(
                supplier=sup, status=PurchaseInvoice.Status.POSTED, date__range=[from_date, to_date]
            ).aggregate(total=Sum('total'))['total'] or Decimal('0')
            
            period_paid = SupplierPayment.objects.filter(
                supplier=sup, date__range=[from_date, to_date]
            ).aggregate(total=Sum('amount'))['total'] or Decimal('0')
            
            results.append({
                'supplier': sup,
                'balance': sup.balance,
                'period_purchases': period_purchases,
                'period_paid': period_paid
            })
        return results

    @staticmethod
    def supplier_aging_report(supplier_id=None):
        
        today = timezone.now().date()
        suppliers = Supplier.objects.all()
        if supplier_id:
            suppliers = suppliers.filter(id=supplier_id)
            
        aging_results = []
        for sup in suppliers:
            # Unpaid purchase invoices
            unpaid_invoices = PurchaseInvoice.objects.filter(
                supplier=sup, status=PurchaseInvoice.Status.POSTED
            ).annotate(
                remaining=F('total') - F('paid_amount')
            ).filter(remaining__gt=0)
            
            buckets = {
                'current': Decimal('0'),
                '1_30': Decimal('0'),
                '31_60': Decimal('0'),
                'over_60': Decimal('0'),
                'total': Decimal('0')
            }
            
            for inv in unpaid_invoices:
                age = (today - (inv.due_date or inv.date)).days
                amount = inv.remaining
                buckets['total'] += amount
                if age <= 0: buckets['current'] += amount
                elif age <= 30: buckets['1_30'] += amount
                elif age <= 60: buckets['31_60'] += amount
                else: buckets['over_60'] += amount
                
            # Account for unallocated balances (e.g. opening balance, unapplied payments)
            # Make sure the total matches the actual supplier balance
            unallocated = sup.balance - buckets['total']
            
            if unallocated > 0:
                # Positive unallocated usually means Opening Balance, which is old debt.
                buckets['over_60'] += unallocated
            else:
                # Negative unallocated usually means Advance Payments or Unapplied Returns.
                buckets['current'] += unallocated
                
            buckets['total'] = sup.balance
                
            if buckets['total'] != 0 or unpaid_invoices.exists():
                aging_results.append({
                    'supplier': sup,
                    'buckets': buckets,
                    'balance': sup.balance
                })
        return aging_results

    @staticmethod
    def open_purchase_orders_report():
        return PurchaseOrder.objects.filter(
            status__in=[PurchaseOrder.Status.APPROVED, PurchaseOrder.Status.RECEIVED]
        ).select_related('supplier').order_by('date')

    @staticmethod
    def purchase_returns_analysis_report(from_date, to_date):
        
        suppliers = Supplier.objects.all()
        results = []
        for sup in suppliers:
            total_purchases = PurchaseInvoice.objects.filter(
                supplier=sup, status=PurchaseInvoice.Status.POSTED, date__range=[from_date, to_date]
            ).aggregate(total=Sum('total'))['total'] or Decimal('0')
            
            total_returns = PurchaseReturn.objects.filter(
                supplier=sup, status=PurchaseReturn.Status.POSTED, date__range=[from_date, to_date]
            ).aggregate(total=Sum('total'))['total'] or Decimal('0')
            
            return_rate = (total_returns / total_purchases * 100) if total_purchases > 0 else 0
            
            if total_returns > 0 or total_purchases > 0:
                results.append({
                    'supplier': sup,
                    'total_purchases': total_purchases,
                    'total_returns': total_returns,
                    'return_rate': return_rate
                })
        return sorted(results, key=lambda x: x['total_returns'], reverse=True)
    @staticmethod
    def supplier_statement(supplier_id, from_date, to_date):
        supplier = Supplier.objects.get(id=supplier_id)
        account = supplier.account

        init_debit = Decimal('0')
        init_credit = Decimal('0')
        has_opening_entry = JournalLine.objects.filter(
            account=account,
            entry__entry_type=JournalEntry.EntryType.OPENING,
            entry__is_posted=True
        ).exists()
        if not has_opening_entry:
            if account.initial_balance_type == 'debit':
                init_debit = account.initial_balance
            else:
                init_credit = account.initial_balance

        pre_movements = JournalLine.objects.filter(
            account=account,
            entry__date__lt=from_date,
            entry__is_posted=True
        ).aggregate(d=Sum('debit'), c=Sum('credit'))
        op_debit = init_debit + (pre_movements['d'] or Decimal('0'))
        op_credit = init_credit + (pre_movements['c'] or Decimal('0'))
        op_balance = op_debit - op_credit
        
        # 2. Movements
        lines = JournalLine.objects.filter(
            account=account,
            entry__date__range=[from_date, to_date],
            entry__is_posted=True
        ).select_related('entry').order_by('entry__date', 'entry__id')
        
        movements = []
        running_bal = op_balance
        for l in lines:
            running_bal += (l.debit - l.credit)
            movements.append({
                'date': l.entry.date,
                'number': str(l.entry.source_document) if l.entry.source_document else l.entry.number,
                'reference': l.entry.reference,
                'description': l.description or l.entry.description,
                'debit': l.debit,
                'credit': l.credit,
                'balance': running_bal,
                'source_url': l.entry.source_document.get_absolute_url() if l.entry.source_document and hasattr(l.entry.source_document, 'get_absolute_url') else (l.entry.get_absolute_url() if hasattr(l.entry, 'get_absolute_url') else None)
            })
            
        return {
            'supplier': supplier,
            'op_balance': op_balance,
            'movements': movements,
            'cl_balance': running_bal
        }

    @staticmethod
    def live_liquidity_position():
        
        cash_boxes = CashBox.objects.filter(is_active=True).select_related('responsible_user', 'account')
        bank_accounts = BankAccount.objects.filter(is_active=True).select_related('account')
        
        liquidity_data = {
            'cash_boxes': [],
            'bank_accounts': [],
            'total_by_currency': {}
        }
        
        for cb in cash_boxes:
            bal = cb.current_balance
            liquidity_data['cash_boxes'].append({
                'obj': cb,
                'balance': bal
            })
            curr = cb.currency
            liquidity_data['total_by_currency'][curr] = liquidity_data['total_by_currency'].get(curr, Decimal('0')) + bal
            
        for ba in bank_accounts:
            bal = ba.current_balance
            liquidity_data['bank_accounts'].append({
                'obj': ba,
                'balance': bal
            })
            curr = ba.currency
            liquidity_data['total_by_currency'][curr] = liquidity_data['total_by_currency'].get(curr, Decimal('0')) + bal
            
        return liquidity_data

    @staticmethod
    def cash_in_transit_report():
        
        pending_transfers = CashTransfer.objects.filter(
            status=CashTransfer.Status.PENDING
        ).select_related('from_cash_box', 'from_bank', 'to_cash_box', 'to_bank')
        
        report = []
        now = timezone.now().date()
        for t in pending_transfers:
            days_in_transit = (now - t.date).days
            report.append({
                'transfer': t,
                'days': days_in_transit
            })
        return report

    @staticmethod
    def internal_transfers_summary(from_date, to_date):
        
        transfers = CashTransfer.objects.filter(
            status=CashTransfer.Status.COMPLETED,
            date__range=[from_date, to_date]
        ).select_related('from_cash_box', 'from_bank', 'to_cash_box', 'to_bank')
        
        return transfers

    @staticmethod
    def bank_reconciliation_report(reconciliation_id):
        recon = BankReconciliation.objects.get(id=reconciliation_id)
        
        unreconciled_transactions = BankTransaction.objects.filter(
            bank_account=recon.bank_account,
            date__lte=recon.statement_date,
            is_reconciled=False
        )
        
        return {
            'recon': recon,
            'unreconciled': unreconciled_transactions
        }

    @staticmethod
    def bank_charges_interest_report(from_date, to_date):
        
        report = BankTransaction.objects.filter(
            date__range=[from_date, to_date],
            transaction_type__in=[
                BankTransaction.TransactionType.ACCOUNT_FEE,
                BankTransaction.TransactionType.TRANSFER_FEE,
                BankTransaction.TransactionType.BOUNCE_FEE,
                BankTransaction.TransactionType.STOP_CHEQUE_FEE,
                BankTransaction.TransactionType.CHEQUEBOOK_FEE,
                BankTransaction.TransactionType.CARD_FEE,
                BankTransaction.TransactionType.LOAN_INTEREST,
                BankTransaction.TransactionType.INTEREST_REV,
            ]
        ).select_related('bank_account').order_by('-date', '-id')
        
        return report

    @staticmethod
    def expenses_by_category(from_date, to_date):
        
        report = Expense.objects.filter(
            date__range=[from_date, to_date],
            status=Expense.Status.POSTED
        ).values('category__name').annotate(
            invoice_count=Count('id'),
            total_subtotal=Sum('subtotal'),
            total_tax=Sum('tax_amount'),
            total_final=Sum('total')
        ).order_by('-total_final')
        
        return report

    @staticmethod
    def expenses_by_cost_center(from_date, to_date):
        
        report = Expense.objects.filter(
            date__range=[from_date, to_date],
            status=Expense.Status.POSTED
        ).values('cost_center__name').annotate(
            total_amount=Sum('total')
        ).order_by('-total_amount')
        
        return report

    @staticmethod
    def expense_tax_report(from_date, to_date):
        
        report = Expense.objects.filter(
            date__range=[from_date, to_date],
            status=Expense.Status.POSTED,
            tax_amount__gt=0
        ).select_related('category', 'tax_type', 'tax_type2')
        
        return report

    @staticmethod
    def outstanding_custodies_summary():
        
        report = Custody.objects.filter(
            status__in=[Custody.Status.OPEN, Custody.Status.PARTIALLY_SETTLED]
        ).select_related('employee').annotate(
            remaining_balance=F('amount') - F('settled_amount')
        ).order_by('date')
        
        return report

    @staticmethod
    def custody_settlement_detail(settlement_id):
        settlement = CustodySettlement.objects.select_related('custody', 'custody__employee', 'cash_box').get(id=settlement_id)
        expenses = Expense.objects.filter(settlement=settlement)
        
        return {
            'settlement': settlement,
            'expenses': expenses
        }

    @staticmethod
    def aged_custodies_report():
        
        now = timezone.now().date()
        report = Custody.objects.filter(
            status=Custody.Status.OPEN
        ).select_related('employee')
        
        aged_data = []
        for c in report:
            days = (now - c.date).days
            aged_data.append({
                'custody': c,
                'days': days
            })
        return aged_data

    @staticmethod
    def expenses_by_payment_method(from_date, to_date):
        
        report = Expense.objects.filter(
            date__range=[from_date, to_date],
            status=Expense.Status.POSTED
        ).values('payment_method').annotate(
            count=Count('id'),
            total_sum=Sum('total')
        ).order_by('-total_sum')
        
        return report

    @staticmethod
    def hr_org_chart_summary():
        
        report = Department.objects.annotate(
            employee_count=Count('employees', filter=Q(employees__status='active')),
            total_basic_salary=Sum('employees__basic_salary', filter=Q(employees__status='active'))
        ).order_by('-employee_count')
        
        contract_distribution = Employee.objects.filter(status='active').values('contract_type').annotate(
            count=Count('id')
        )
        
        return {
            'department_stats': report,
            'contract_distribution': contract_distribution
        }

    @staticmethod
    def hr_document_expiry_report(days=30):
        
        limit_date = timezone.now().date() + timedelta(days=days)
        report = EmployeeDocument.objects.filter(
            expiry_date__lte=limit_date,
            expiry_date__gte=timezone.now().date()
        ).select_related('employee')
        
        return report

    @staticmethod
    def hr_attendance_summary(from_date, to_date):
        
        report = AttendanceRecord.objects.filter(
            date__range=[from_date, to_date]
        ).values('employee__first_name', 'employee__last_name').annotate(
            absent_count=Count('id', filter=Q(status='absent')),
            late_count=Count('id', filter=Q(status='late')),
            total_overtime=Sum('overtime_hours')
        )
        
        return report

    @staticmethod
    def hr_leave_balances_report():
        
        report = LeaveBalance.objects.select_related('employee', 'leave_type').order_by('employee__first_name')
        return report

    @staticmethod
    def payroll_register_report(period_id):
        report = Payslip.objects.filter(period_id=period_id).select_related('employee', 'employee__department', 'employee__job_title')
        return report

    @staticmethod
    def payroll_by_cost_center_report(period_id):
        
        report = Payslip.objects.filter(period_id=period_id).values(
            'employee__department__cost_center__name'
        ).annotate(
            total_gross=Sum('basic_salary') + Sum('total_allowances') + Sum('other_additions'),
            total_insurance=Sum('social_insurance'),
            total_net=Sum('net_salary')
        )
        return report

    @staticmethod
    def payroll_tax_insurance_report(period_id):
        
        report = Payslip.objects.filter(period_id=period_id).aggregate(
            total_social_insurance=Sum('social_insurance'),
            total_income_tax=Sum('income_tax')
        )
        return report

    @staticmethod
    def hr_loans_balance_report():
        
        report = Loan.objects.filter(
            status__in=['approved', 'paid']
        ).select_related('employee').annotate(
            paid_amount=Sum('installments__amount')
        ).annotate(
            remaining_balance=F('amount') - F('paid_amount')
        )
        return report

    @staticmethod
    def hr_employee_assets_report():
        report = EmployeeAsset.objects.filter(is_returned=False).select_related('employee')
        return report

    @staticmethod
    def hr_eos_settlements_report():
        report = EndOfService.objects.select_related('employee').order_by('-termination_date')
        return report

    @staticmethod
    def cash_flow_statement_report(from_date: date, to_date: date) -> dict:
        """
        قائمة التدفقات النقدية (الطريقة المباشرة)
        """
        from django.conf import settings
        
        # 1. Get all cash/bank related accounts based on chart of accounts parent codes
        cash_parent_code = getattr(settings, 'CASH_PARENT_ACCOUNT', '1111')
        bank_parent_code = getattr(settings, 'BANK_PARENT_ACCOUNT', '1112')
        
        all_cash_account_ids = set(Account.objects.filter(
            Q(code__startswith=cash_parent_code) | Q(code__startswith=bank_parent_code),
            is_leaf=True
        ).values_list('id', flat=True))
        
        # 2. Opening Balance (Before from_date)
        pre_movements = JournalLine.objects.filter(
            account_id__in=all_cash_account_ids,
            entry__is_posted=True,
            entry__is_reversed=False,
            entry__date__lt=from_date
        ).aggregate(d=Sum('debit'), c=Sum('credit'))
        
        init_balance = Decimal('0')
        accounts_obj = Account.objects.filter(id__in=all_cash_account_ids)
        for acc in accounts_obj:
            has_opening = JournalLine.objects.filter(
                account=acc,
                entry__entry_type=JournalEntry.EntryType.OPENING,
                entry__is_posted=True,
                entry__is_reversed=False
            ).exists()
            if not has_opening:
                if acc.initial_balance_type == 'debit':
                    init_balance += acc.initial_balance
                else:
                    init_balance -= acc.initial_balance
                    
        opening_balance = init_balance + (pre_movements['d'] or Decimal('0')) - (pre_movements['c'] or Decimal('0'))

        # 3. Process Period Movements
        cash_lines = JournalLine.objects.filter(
            account_id__in=all_cash_account_ids,
            entry__is_posted=True,
            entry__is_reversed=False,
            entry__date__range=[from_date, to_date],
        ).exclude(
            entry__entry_type=JournalEntry.EntryType.OPENING
        ).select_related('entry')

        # Categories
        operating_inflow = Decimal('0')
        operating_outflow = Decimal('0')
        investing_inflow = Decimal('0')
        investing_outflow = Decimal('0')
        financing_inflow = Decimal('0')
        financing_outflow = Decimal('0')
        
        details = {
            'operating': [],
            'investing': [],
            'financing': []
        }

        # Analyze each cash line based on the other lines in the same entry
        for line in cash_lines:
            entry = line.entry
            is_inflow = line.debit > 0
            amount = line.debit if is_inflow else line.credit
            
            # Find the opposite lines in this entry to classify
            opposite_lines = entry.lines.exclude(account_id__in=all_cash_account_ids)
            if not opposite_lines.exists():
                # Internal transfer between cash accounts -> ignore for cash flow
                continue
                
            # Take the primary opposite account to classify
            main_opp_line = opposite_lines.order_by('-debit', '-credit').first()
            opp_acc_type = main_opp_line.account.account_type
            opp_code = main_opp_line.account.code
            
            # Classification Logic
            category = 'operating'
            label = "عمليات أخرى"
            
            # Operating
            if opp_acc_type in [AccountType.REVENUE, AccountType.EXPENSE]:
                category = 'operating'
                label = "مبيعات وإيرادات نقدية" if is_inflow else "مصروفات نقدية"
            elif opp_code.startswith('112') or opp_code.startswith('212'):  # العملاء والموردين والضرائب
                category = 'operating'
                label = "مقبوضات من العملاء" if is_inflow else "مدفوعات للموردين / ضرائب"
                
            # Investing (الأصول الثابتة)
            elif opp_code.startswith('12'):
                category = 'investing'
                label = "بيع أصول ثابتة" if is_inflow else "شراء أصول ثابتة"
                
            # Financing (القروض ورأس المال)
            elif opp_acc_type == AccountType.EQUITY or opp_code.startswith('22'): # الخصوم طويلة الأجل أو حقوق الملكية
                category = 'financing'
                label = "زيادة رأس المال / قروض" if is_inflow else "توزيعات أرباح / سداد قروض"
            
            # Record
            if category == 'operating':
                if is_inflow: operating_inflow += amount
                else: operating_outflow += amount
            elif category == 'investing':
                if is_inflow: investing_inflow += amount
                else: investing_outflow += amount
            elif category == 'financing':
                if is_inflow: financing_inflow += amount
                else: financing_outflow += amount
                
            # Add to details
            details[category].append({
                'date': entry.date,
                'number': entry.number,
                'description': entry.description or line.description,
                'amount': amount,
                'is_inflow': is_inflow,
                'label': label
            })

        net_operating = operating_inflow - operating_outflow
        net_investing = investing_inflow - investing_outflow
        net_financing = financing_inflow - financing_outflow
        net_change = net_operating + net_investing + net_financing
        closing_balance = opening_balance + net_change

        return {
            'opening_balance': opening_balance,
            
            'operating_inflow': operating_inflow,
            'operating_outflow': operating_outflow,
            'net_operating': net_operating,
            
            'investing_inflow': investing_inflow,
            'investing_outflow': investing_outflow,
            'net_investing': net_investing,
            
            'financing_inflow': financing_inflow,
            'financing_outflow': financing_outflow,
            'net_financing': net_financing,
            
            'net_change': net_change,
            'closing_balance': closing_balance,
            
            'details': details
        }

