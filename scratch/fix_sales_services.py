import re

with open('apps/sales/services.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_bounce = """        entry = JournalService.create_entry(
            date_val=bounce_date,
            entry_type=JournalEntry.EntryType.BANK,
            description=f'مرتجع شيك رقم {receipt.cheque_number}',
            lines=lines,
            source_document=receipt,
            created_by=created_by,
        )

        receipt.cheque_status = CustomerReceipt.ChequeStatus.BOUNCED
        receipt.reference += f" | مرتجع بتاريخ {bounce_date}"
        receipt.save(update_fields=['cheque_status', 'reference'])

        return entry"""

new_bounce = """        entry = JournalService.create_entry(
            date_val=bounce_date,
            entry_type=JournalEntry.EntryType.BANK,
            description=f'مرتجع شيك رقم {receipt.cheque_number}',
            lines=lines,
            source_document=receipt,
            created_by=created_by,
        )

        # Revert paid_amount on related invoices
        for allocation in receipt.receiptallocation_set.select_related('invoice').all():
            invoice = SalesInvoice.objects.select_for_update().get(pk=allocation.invoice.pk)
            invoice.paid_amount -= allocation.amount
            if invoice.paid_amount < 0:
                invoice.paid_amount = Decimal('0.00')
            invoice.save(update_fields=['paid_amount'])

        receipt.cheque_status = CustomerReceipt.ChequeStatus.BOUNCED
        receipt.reference += f" | مرتجع بتاريخ {bounce_date}"
        receipt.save(update_fields=['cheque_status', 'reference'])

        return entry"""

content = content.replace(old_bounce, new_bounce)

with open('apps/sales/services.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done services!")
