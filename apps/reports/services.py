from datetime import date
from decimal import Decimal
from django.db.models import Sum
from apps.core.models import Account, JournalLine, JournalEntry, FiscalYear, AccountType

class ReportService:

    @staticmethod
    def trial_balance(from_date: date, to_date: date) -> list[dict]:
        """
        ميزان المراجعة بالمجاميع والأرصدة (Optimized)
        """
        # 1. Get accounts with OPENING entries to handle initial_balance logic
        opening_entry_accounts = set(JournalLine.objects.filter(
            entry__entry_type=JournalEntry.EntryType.OPENING,
            entry__is_posted=True
        ).values_list('account_id', flat=True))

        # 2. Bulk aggregate movements before from_date
        pre_movements = JournalLine.objects.filter(
            entry__is_posted=True,
            entry__date__lt=from_date
        ).values('account_id').annotate(d=Sum('debit'), c=Sum('credit'))
        pre_map = {m['account_id']: (m['d'] or Decimal('0'), m['c'] or Decimal('0')) for m in pre_movements}

        # 3. Bulk aggregate movements in period
        period_movements = JournalLine.objects.filter(
            entry__is_posted=True,
            entry__date__range=[from_date, to_date]
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
        قائمة الدخل (Income Statement / P&L)
        Net Revenue - Net Expense = Net Income
        """
        base_filter = {
            'entry__is_posted': True,
            'entry__date__range': [from_date, to_date]
        }
        if cost_center_id:
            base_filter['cost_center_id'] = cost_center_id

        # Net Revenue (Credit - Debit)
        revenue_data = JournalLine.objects.filter(
            account__account_type=AccountType.REVENUE,
            **base_filter
        ).aggregate(d=Sum('debit'), c=Sum('credit'))
        revenue_total = (revenue_data['c'] or Decimal('0')) - (revenue_data['d'] or Decimal('0'))
        
        # Net Expense (Debit - Credit)
        expense_data = JournalLine.objects.filter(
            account__account_type=AccountType.EXPENSE,
            **base_filter
        ).aggregate(d=Sum('debit'), c=Sum('credit'))
        expense_total = (expense_data['d'] or Decimal('0')) - (expense_data['c'] or Decimal('0'))
        
        return {
            'revenue': revenue_total,
            'expenses': expense_total,
            'net_income': revenue_total - expense_total
        }

    @staticmethod
    def balance_sheet(as_of_date: date, cost_center_id=None) -> dict:
        """
        المركز المالي (Balance Sheet) - Optimized
        Assets = Liabilities + Equity
        """
        base_filter = {'entry__is_posted': True, 'entry__date__lte': as_of_date}
        if cost_center_id:
            base_filter['cost_center_id'] = cost_center_id

        # 1. Aggregated movements for all accounts
        movements = JournalLine.objects.filter(**base_filter).values('account_id').annotate(d=Sum('debit'), c=Sum('credit'))
        mov_map = {m['account_id']: (m['d'] or Decimal('0'), m['c'] or Decimal('0')) for m in movements}

        # 2. Get accounts with OPENING entries
        opening_entry_accounts = set(JournalLine.objects.filter(
            entry__entry_type=JournalEntry.EntryType.OPENING,
            entry__is_posted=True
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
        from apps.sales.models import Customer
        customer = Customer.objects.get(id=customer_id)
        account = customer.account
        
        # 1. Check for opening entry
        has_opening = JournalLine.objects.filter(
            account=account,
            entry__entry_type=JournalEntry.EntryType.OPENING,
            entry__is_posted=True
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
            entry__date__lt=from_date
        ).aggregate(d=Sum('debit'), c=Sum('credit'))
        
        opening_balance = (init_debit + (pre_movements['d'] or 0)) - (init_credit + (pre_movements['c'] or 0))
        
        # Movements in period
        movements = JournalLine.objects.filter(
            account=account,
            entry__is_posted=True,
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
                'balance': running_balance
            })
            
        return {
            'customer': customer,
            'opening_balance': opening_balance,
            'lines': statement_lines,
            'closing_balance': running_balance
        }

    @staticmethod
    def stock_status(warehouse_id=None) -> list[dict]:
        """
        تقرير حالة المخزون
        """
        from apps.inventory.models import ItemLedger, Warehouse
        qs = ItemLedger.objects.select_related('item', 'warehouse', 'item__unit', 'item__category')
        
        if warehouse_id:
            qs = qs.filter(warehouse_id=warehouse_id)
            
        return qs.order_by('warehouse__name', 'item__name')

    @staticmethod
    def rep_commission_report(from_date: date, to_date: date) -> list[dict]:
        """
        تقرير عمولات المناديب بناءً على المبيعات (أو التحصيلات)
        """
        from apps.sales.models import SalesRepresentative, SalesInvoice
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
        from apps.core.models import CostCenter
        cost_center = CostCenter.objects.get(id=cost_center_id)
        
        movements = JournalLine.objects.filter(
            cost_center=cost_center,
            entry__is_posted=True,
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
            entry__is_posted=True
        ).exists()

        init_debit = Decimal('0')
        init_credit = Decimal('0')
        
        if not has_opening_entry:
            init_debit = account.initial_balance if account.initial_balance_type == 'debit' else Decimal('0')
            init_credit = account.initial_balance if account.initial_balance_type == 'credit' else Decimal('0')

        pre_movements = JournalLine.objects.filter(
            account=account, 
            entry__is_posted=True, 
            entry__date__lt=from_date
        ).aggregate(d=Sum('debit'), c=Sum('credit'))
        
        op_debit = init_debit + (pre_movements['d'] or Decimal('0'))
        op_credit = init_credit + (pre_movements['c'] or Decimal('0'))
        opening_balance = op_debit - op_credit
        
        # 2. Movements in period
        movements = JournalLine.objects.filter(
            account=account,
            entry__is_posted=True,
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
