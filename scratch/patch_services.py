import re

def main():
    file_path = 'apps/purchases/services.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading file: {e}")
        return

    # 1. SupplierService.create_supplier - Max sequence generation bug
    old_seq = """        # ✅ Fix: Use max code instead of count() to avoid duplicates
        last_account = Account.objects.filter(parent=parent).order_by('-code').first()
        if last_account:
            try:
                last_seq = int(last_account.code[len(parent.code):])
                next_seq = last_seq + 1
            except (ValueError, IndexError):
                next_seq = Account.objects.filter(parent=parent).count() + 1
        else:
            next_seq = 1"""
            
    new_seq = """        # ✅ Fix: Use max code instead of count() to avoid duplicates
        from django.db.models import IntegerField
        from django.db.models.functions import Cast, Substr
        last_account = Account.objects.filter(parent=parent).annotate(
            seq_int=Cast(Substr('code', len(parent.code) + 1), output_field=IntegerField())
        ).order_by('-seq_int').first()
        if last_account:
            try:
                last_seq = last_account.seq_int
                next_seq = last_seq + 1
            except (ValueError, TypeError, IndexError):
                next_seq = Account.objects.filter(parent=parent).count() + 1
        else:
            next_seq = 1"""
            
    content = content.replace(old_seq, new_seq)

    # 2. SupplierService.update_supplier - Protected field overwrite
    old_upd = """        for field, value in validated_data.items():
            if field not in ('initial_balance', 'initial_balance_type'):
                setattr(supplier, field, value)"""
                
    new_upd = """        for field, value in validated_data.items():
            if field not in ('initial_balance', 'initial_balance_type', 'code', 'account', 'account_id'):
                setattr(supplier, field, value)"""
                
    content = content.replace(old_upd, new_upd)

    # 3. PurchaseService.post_invoice / post_return - Null warehouse crash & Null discount crash
    old_acc1 = """            acc = line.warehouse.gl_account or line.item.inventory_account"""
    new_acc1 = """            warehouse_acc = line.warehouse.gl_account if line.warehouse else None
            acc = warehouse_acc or line.item.inventory_account or getattr(line.item, 'expense_account', None)"""
    content = content.replace(old_acc1, new_acc1) # Applies to both post_invoice and post_return
    
    old_net1 = """            line_net = line.quantity * line.unit_cost * (Decimal('1') - (Decimal(str(line.discount_percent)) / Decimal('100')))"""
    new_net1 = """            discount_pct = Decimal(str(line.discount_percent or '0'))
            line_net = line.quantity * line.unit_cost * (Decimal('1') - (discount_pct / Decimal('100')))"""
    content = content.replace(old_net1, new_net1) # Applies to both
    
    # 4. Unbalanced GL Entries - continue without tax acc
    old_tax1 = """                        tax_acc = tx_type.account
                        if not tax_acc:
                            continue"""
    new_tax1 = """                        tax_acc = tx_type.account
                        if not tax_acc:
                            raise ValueError(f"يرجى تحديد حساب الأستاذ لضريبة {tx_type.name}")"""
    content = content.replace(old_tax1, new_tax1) # Applies to both
    
    # Add balance validation before JournalService.create_entry (for invoice and return)
    # Since this occurs before `entry = JournalService.create_entry`, let's just regex replace that call to prepend validation
    old_create = """        entry = JournalService.create_entry("""
    new_create = """        total_dr = sum(l['debit'] for l in lines)
        total_cr = sum(l['credit'] for l in lines)
        if total_dr != total_cr:
            raise ValueError(f"عدم اتزان مالي: مدين {total_dr} ، دائن {total_cr}. يرجى مراجعة الخصومات والضرائب.")
            
        entry = JournalService.create_entry("""
    content = content.replace(old_create, new_create)
    
    # 5. Inventory Valuation Mismatch in reverse_invoice and post_return
    old_wac1 = """            conversion = _conversion_to_base(line)
            unit_cost_base = line.unit_cost / conversion"""
    new_wac1 = """            discount_pct = Decimal(str(line.discount_percent or '0'))
            line_net = line.quantity * line.unit_cost * (Decimal('1') - (discount_pct / Decimal('100')))
            res = calculate_line_taxes(line_net, line.tax_type, line.tax_percent or 0, line.tax_type2, line.tax_percent2 or 0, is_purchase_or_expense=True)
            inv_cost = line_net + res['capitalized_amount']
            base_qty = line.base_quantity or line.quantity
            unit_cost_base = (inv_cost / base_qty) if base_qty > 0 else Decimal('0')"""
    content = content.replace(old_wac1, new_wac1)
    
    # 6. Payment Over-Allocation & Race Conditions in record_payment
    old_alloc = """        # Update paid_amount in related invoices
        for allocation in payment.paymentallocation_set.all():
            invoice = allocation.invoice
            # Use atomic F() update to prevent race conditions on concurrent payment postings
            Invoice = type(invoice)
            Invoice.objects.filter(pk=invoice.pk).update(
                paid_amount=F('paid_amount') + allocation.amount
            )
            # Cap at total to prevent overpayment
            Invoice.objects.filter(
                pk=invoice.pk, paid_amount__gt=F('total')
            ).update(paid_amount=F('total'))"""
            
    new_alloc = """        # Update paid_amount in related invoices
        total_allocated = Decimal('0')
        for allocation in payment.paymentallocation_set.select_related('invoice').all():
            if allocation.amount <= 0:
                raise ValueError("مبلغ التخصيص يجب أن يكون موجباً")
            total_allocated += allocation.amount
            
            invoice = allocation.invoice
            Invoice = type(invoice)
            locked_invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
            
            if locked_invoice.status != PurchaseInvoice.Status.POSTED:
                raise ValueError(f"لا يمكن السداد لفاتورة غير مرحلة أو ملغاة: {locked_invoice.number}")
                
            if locked_invoice.paid_amount + allocation.amount > locked_invoice.total:
                raise ValueError(f"التخصيص يتجاوز المتبقي للفاتورة {locked_invoice.number}")
                
            locked_invoice.paid_amount += allocation.amount
            locked_invoice.save(update_fields=['paid_amount'])
            
        if total_allocated > payment.amount:
            raise ValueError("إجمالي التخصيصات يتجاوز مبلغ السند")"""
    content = content.replace(old_alloc, new_alloc)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
        
    print("Services updated successfully.")

if __name__ == '__main__':
    main()
