import re

def main():
    file_path = 'apps/pos/services.py'
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return

    # open_session select_for_update
    old_open = """    def open_session(user, station, opening_cash):
        \"\"\"Opens a new POSSession for the user at a specified station.\"\"\"
        active = POSSession.objects.filter("""
    new_open = """    def open_session(user, station, opening_cash):
        \"\"\"Opens a new POSSession for the user at a specified station.\"\"\"
        from django.contrib.auth import get_user_model
        User = get_user_model()
        User.objects.select_for_update().get(pk=user.pk)
        
        active = POSSession.objects.filter("""
    content = content.replace(old_open, new_open)

    # create_order signature and parsing
    old_create_sig = """    def create_order(session, cart_items, payment_method, customer_id=None, is_taxable=True):"""
    new_create_sig = """    def create_order(session, cart_items, payment_method, customer_id=None, is_taxable=True, payment_reference=''):"""
    content = content.replace(old_create_sig, new_create_sig)

    old_create_loop = """        for c in cart_items:
            item_id = c.get('id')
            qty = Decimal(str(c.get('qty', 0)))
            price_inclusive = Decimal(str(c.get('price', 0)))"""
    new_create_loop = """        for c in cart_items:
            item_id = c.get('id')
            try:
                qty = Decimal(str(c.get('qty', 0)))
                price_inclusive = Decimal(str(c.get('price', 0)))
            except Exception:
                raise ValueError("قيم الكمية أو السعر غير صالحة")
            if qty <= 0:
                raise ValueError("الكمية يجب أن تكون أكبر من الصفر")
            if price_inclusive < 0:
                raise ValueError("سعر الوحدة لا يمكن أن يكون سالباً")"""
    content = content.replace(old_create_loop, new_create_loop)

    old_create_pay = """        POSPayment.objects.create(
            order=order,
            method=payment_method,
            amount=grand_total
        )"""
    new_create_pay = """        if payment_method in ('card', 'wallet') and not payment_reference:
            payment_reference = f"{payment_method}-{receipt_number}"

        POSPayment.objects.create(
            order=order,
            method=payment_method,
            amount=grand_total,
            reference=payment_reference
        )"""
    content = content.replace(old_create_pay, new_create_pay)

    # return_items logic update order lines and order totals
    old_return_loop_end = """            line_refund_tax = refund_amount - line_refund_subtotal
            
            total_refund += refund_amount
            total_refund_subtotal += line_refund_subtotal
            total_refund_tax += line_refund_tax

            # Return items to warehouse"""
    new_return_loop_end = """            line_refund_tax = refund_amount - line_refund_subtotal
            
            total_refund += refund_amount
            total_refund_subtotal += line_refund_subtotal
            total_refund_tax += line_refund_tax

            if return_qty == line.qty:
                line.delete()
            else:
                line.qty -= return_qty
                line.total -= refund_amount
                line.save(update_fields=['qty', 'total'])

            # Return items to warehouse"""
    content = content.replace(old_return_loop_end, new_return_loop_end)

    old_return_pay = """        if total_refund > 0:
            POSPayment.objects.create(
                order=order,
                method=POSPayment.PaymentMethod.CASH,
                amount=-total_refund,
                reference="مردودات مبيعات"
            )

        return True"""
    new_return_pay = """        if total_refund > 0:
            POSPayment.objects.create(
                order=order,
                method=POSPayment.PaymentMethod.CASH,
                amount=-total_refund,
                reference="مردودات مبيعات"
            )
            
            order.subtotal -= total_refund_subtotal
            order.tax -= total_refund_tax
            order.grand_total -= total_refund
            if order.subtotal < 0: order.subtotal = Decimal('0')
            if order.tax < 0: order.tax = Decimal('0')
            if order.grand_total < 0: order.grand_total = Decimal('0')
            order.save(update_fields=['subtotal', 'tax', 'grand_total'])

        return True"""
    content = content.replace(old_return_pay, new_return_pay)

    # create_combined_journal_entry fix ratio and negatives
    old_ratio = """        # If there are refunds, we proportionally reduce the revenue and tax
        refund_ratio = Decimal('1')
        if total_cash_sales > 0 and total_refund_cash > 0:
            refund_ratio = (total_cash_sales - total_refund_cash) / total_cash_sales
            if refund_ratio < 0: refund_ratio = Decimal('0')

        # 3. Credit Revenue and Taxes
        for account_id, data in revenue_by_account.items():
            account = data[0]
            amount = (data[1] * refund_ratio).quantize(Decimal('0.01'))
            if amount > 0:
                journal_lines.append({
                    'account': account, 'debit': Decimal('0'), 'credit': amount,
                    'description': f"إيرادات مبيعات - الوردية رقم {session.id}"
                })
        
        total_tax = (total_tax * refund_ratio).quantize(Decimal('0.01'))
        if total_tax > 0:"""
    new_ratio = """        # 3. Credit Revenue and Taxes
        for account_id, data in revenue_by_account.items():
            account = data[0]
            amount = data[1].quantize(Decimal('0.01'))
            if amount > 0:
                journal_lines.append({
                    'account': account, 'debit': Decimal('0'), 'credit': amount,
                    'description': f"إيرادات مبيعات - الوردية رقم {session.id}"
                })
        
        if total_tax > 0:"""
    content = content.replace(old_ratio, new_ratio)
    
    old_tax_net = """            item = line.item
            sales_acc = item.sales_account"""
    new_tax_net = """            item = line.item
            tax_rate = line.tax_percent / Decimal('100')
            line_net = (line.total / (Decimal('1') + tax_rate)).quantize(Decimal('0.01'))
            sales_acc = item.sales_account"""
    content = content.replace(old_tax_net, new_tax_net)
    
    old_rev_calc = """                revenue_by_account[sales_acc.id] = (sales_acc, revenue_by_account[sales_acc.id][1] + line.total)"""
    new_rev_calc = """                revenue_by_account[sales_acc.id] = (sales_acc, revenue_by_account[sales_acc.id][1] + line_net)"""
    content = content.replace(old_rev_calc, new_rev_calc)

    old_negatives = """        # 1. Debit Cash Box (Net Cash Received)
        net_cash = total_cash_sales - total_refund_cash
        if net_cash > 0 and cashbox_account:
            journal_lines.append({
                'account': cashbox_account, 'debit': net_cash, 'credit': Decimal('0'),
                'description': f"إجمالي المقبوضات النقدية للوردية رقم {session.id}"
            })

        # 2. Debit Banks/Wallets
        if total_card > 0 and session.station.bank_account and session.station.bank_account.account:
            journal_lines.append({
                'account': session.station.bank_account.account, 'debit': total_card, 'credit': Decimal('0'),
                'description': f"مدفوعات بطاقات الائتمان - الوردية رقم {session.id}"
            })
        if total_wallet > 0 and session.station.mobile_wallet and session.station.mobile_wallet.account:
            journal_lines.append({
                'account': session.station.mobile_wallet.account, 'debit': total_wallet, 'credit': Decimal('0'),
                'description': f"مدفوعات المحافظ الإلكترونية - الوردية رقم {session.id}"
            })"""
    new_negatives = """        # 1. Debit Cash Box (Net Cash Received)
        net_cash = total_cash_sales - total_refund_cash
        if net_cash > 0 and cashbox_account:
            journal_lines.append({
                'account': cashbox_account, 'debit': net_cash, 'credit': Decimal('0'),
                'description': f"إجمالي المقبوضات النقدية للوردية رقم {session.id}"
            })
        elif net_cash < 0 and cashbox_account:
            journal_lines.append({
                'account': cashbox_account, 'debit': Decimal('0'), 'credit': abs(net_cash),
                'description': f"إجمالي المدفوعات النقدية (مرتجعات) للوردية رقم {session.id}"
            })

        # 2. Debit Banks/Wallets
        if total_card > 0 and session.station.bank_account and session.station.bank_account.account:
            journal_lines.append({
                'account': session.station.bank_account.account, 'debit': total_card, 'credit': Decimal('0'),
                'description': f"مدفوعات بطاقات الائتمان - الوردية رقم {session.id}"
            })
        elif total_card < 0 and session.station.bank_account and session.station.bank_account.account:
            journal_lines.append({
                'account': session.station.bank_account.account, 'debit': Decimal('0'), 'credit': abs(total_card),
                'description': f"مرتجعات بطاقات الائتمان - الوردية رقم {session.id}"
            })
            
        if total_wallet > 0 and session.station.mobile_wallet and session.station.mobile_wallet.account:
            journal_lines.append({
                'account': session.station.mobile_wallet.account, 'debit': total_wallet, 'credit': Decimal('0'),
                'description': f"مدفوعات المحافظ الإلكترونية - الوردية رقم {session.id}"
            })
        elif total_wallet < 0 and session.station.mobile_wallet and session.station.mobile_wallet.account:
            journal_lines.append({
                'account': session.station.mobile_wallet.account, 'debit': Decimal('0'), 'credit': abs(total_wallet),
                'description': f"مرتجعات المحافظ الإلكترونية - الوردية رقم {session.id}"
            })"""
    content = content.replace(old_negatives, new_negatives)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("Services patched.")

if __name__ == '__main__':
    main()
