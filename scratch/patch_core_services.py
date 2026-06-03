import re

def main():
    file_path = 'apps/core/services.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    # 1. create_entry atomicity and safe decimal parsing
    old_create_sig = """    @staticmethod
    def create_entry(
        date_val, 
        entry_type, 
        description, 
        lines, 
        source_document=None, 
        created_by=None
    ) -> JournalEntry:"""
    new_create_sig = """    @staticmethod
    @transaction.atomic
    def create_entry(
        date_val, 
        entry_type, 
        description, 
        lines, 
        source_document=None, 
        created_by=None
    ) -> JournalEntry:"""
    content = content.replace(old_create_sig, new_create_sig)
    
    # 2. create_entry None crash fix
    old_debit_sum = """        total_debit = sum(Decimal(str(l.get('debit', 0))) for l in lines)
        total_credit = sum(Decimal(str(l.get('credit', 0))) for l in lines)"""
    new_debit_sum = """        total_debit = sum(Decimal(str(l.get('debit') or 0)) for l in lines)
        total_credit = sum(Decimal(str(l.get('credit') or 0)) for l in lines)"""
    content = content.replace(old_debit_sum, new_debit_sum)
    
    # 3. create_entry Penny adjustment negative balances fix
    old_penny = """            if largest_line:
                if diff > 0:
                    largest_line['debit'] = Decimal(str(largest_line.get('debit', 0))) - diff
                else:
                    largest_line['credit'] = Decimal(str(largest_line.get('credit', 0))) - abs(diff)"""
    new_penny = """            if largest_line:
                if diff > 0:
                    largest_line['credit'] = Decimal(str(largest_line.get('credit') or 0)) + diff
                else:
                    largest_line['debit'] = Decimal(str(largest_line.get('debit') or 0)) + abs(diff)"""
    content = content.replace(old_penny, new_penny)
    
    # 4. create_entry account_id bypass fix
    old_acc_bypass = """        for i, l in enumerate(lines):
            acc = l.get('account')
            
            if acc and isinstance(acc, Account):
                if not acc.is_leaf:
                    raise ValueError(f"الحساب {acc.name} هو حساب رئيسي. لا يمكن التسجيل عليه مباشرة")
                if not acc.is_active:
                    raise ValueError(f"الحساب {acc.name} غير نشط")"""
    new_acc_bypass = """        for i, l in enumerate(lines):
            acc = l.get('account') or Account.objects.filter(pk=l.get('account_id')).first()
            
            if acc:
                if not acc.is_leaf:
                    raise ValueError(f"الحساب {acc.name} هو حساب رئيسي. لا يمكن التسجيل عليه مباشرة")
                if not acc.is_active:
                    raise ValueError(f"الحساب {acc.name} غير نشط")"""
    content = content.replace(old_acc_bypass, new_acc_bypass)

    # 5. reverse_entry new_entry.is_reversal = True
    old_reverse_save = """        new_entry.source_document_id = entry.source_document_id
        new_entry.source_document_type = entry.source_document_type
        new_entry.save()"""
    new_reverse_save = """        new_entry.source_document_id = entry.source_document_id
        new_entry.source_document_type = entry.source_document_type
        new_entry.is_reversal = True
        new_entry.save()"""
    content = content.replace(old_reverse_save, new_reverse_save)

    # 6. post_opening_balances reverse old entries instead of just flagging
    old_open_bal = """        for old_entry in old_entries:
            old_entry.is_reversed = True
            old_entry.save(update_fields=['is_reversed'])"""
    new_open_bal = """        for old_entry in old_entries:
            JournalService.reverse_entry(old_entry, fiscal_year.start_date, created_by)"""
    content = content.replace(old_open_bal, new_open_bal)
    
    # 7. close_fiscal_year N+1 query fix
    old_close_fy = """        for account in revenue_expenses:
            # Aggregate balances for the year
            balance = account.journal_lines.filter(
                entry__fiscal_year=fiscal_year,
                entry__is_posted=True,
                entry__is_reversed=False
            ).aggregate(
                total_dr=Sum('debit'),
                total_cr=Sum('credit')
            )
            dr = balance['total_dr'] or Decimal('0')
            cr = balance['total_cr'] or Decimal('0')
            net = dr - cr
            
            if net > 0:
                # Debit balance (Expense) - Credit it to close
                lines.append({
                    'account': account,
                    'debit': 0,
                    'credit': net,
                    'description': f'إقفال رصيد {account.name}'
                })
                total_expenses += net
            elif net < 0:
                # Credit balance (Revenue) - Debit it to close
                lines.append({
                    'account': account,
                    'debit': abs(net),
                    'credit': 0,
                    'description': f'إقفال رصيد {account.name}'
                })
                total_revenues += abs(net)"""
    new_close_fy = """        # Fix N+1 queries by aggregating once
        account_balances = JournalLine.objects.filter(
            account__in=revenue_expenses,
            entry__fiscal_year=fiscal_year,
            entry__is_posted=True,
            entry__is_reversed=False
        ).values('account_id').annotate(
            total_dr=Sum('debit'),
            total_cr=Sum('credit')
        )
        
        balance_map = {
            item['account_id']: (item['total_dr'] or Decimal('0')) - (item['total_cr'] or Decimal('0'))
            for item in account_balances
        }
        
        for account in revenue_expenses:
            net = balance_map.get(account.id, Decimal('0'))
            
            if net > 0:
                # Debit balance (Expense) - Credit it to close
                lines.append({
                    'account': account,
                    'debit': 0,
                    'credit': net,
                    'description': f'إقفال رصيد {account.name}'
                })
                total_expenses += net
            elif net < 0:
                # Credit balance (Revenue) - Debit it to close
                lines.append({
                    'account': account,
                    'debit': abs(net),
                    'credit': 0,
                    'description': f'إقفال رصيد {account.name}'
                })
                total_revenues += abs(net)"""
    content = content.replace(old_close_fy, new_close_fy)

    # 8. setup_default_cost_centers is_leaf fix
    old_cc_leaf = """            if not created:
                cc.is_leaf = is_leaf
                cc.save(update_fields=['is_leaf'])"""
    new_cc_leaf = """            if not created:
                has_children = cc.children.exists()
                cc.is_leaf = False if has_children else is_leaf
                cc.save(update_fields=['is_leaf'])"""
    content = content.replace(old_cc_leaf, new_cc_leaf)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
        
    print("Services updated successfully.")

    # Now tax_utils.py
    tax_file = 'apps/core/tax_utils.py'
    try:
        with open(tax_file, 'r', encoding='utf-8') as f:
            tax_content = f.read()
    except Exception as e:
        print(f"Error reading {tax_file}: {e}")
        return
        
    old_tax = """        if t2_type == 'table':
            tax2_val = base_amount * t2_rate
            taxable_for_vat = base_amount + tax2_val"""
    new_tax = """        if t2_type == 'table':
            tax2_val = (base_amount * t2_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            taxable_for_vat = base_amount + tax2_val"""
    tax_content = tax_content.replace(old_tax, new_tax)
    
    with open(tax_file, 'w', encoding='utf-8') as f:
        f.write(tax_content)
    print("Tax Utils updated successfully.")

if __name__ == '__main__':
    main()
