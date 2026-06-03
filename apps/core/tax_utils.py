from decimal import Decimal
from apps.core.models import TaxType

def calculate_line_taxes(base_amount, tax_type1=None, tax_percent1=None, tax_type2=None, tax_percent2=None, is_purchase_or_expense=False):
    """
    Computes taxes uniformly following Egyptian Tax Law compliance:
    - Table Tax (category = 'table') is computed first on base_amount.
    - VAT (category = 'vat') is computed on (base_amount + Table Tax).
    - Others (WHT, Stamp, Customs, etc.) are computed on base_amount.
    - Non-refundable taxes (Table, Stamp, Customs, Other) are capitalized in purchases/expenses.
    - Deductions (WHT, Salary, Insurance) are returned with a negative sign for final total adjustment.
    """
    base_amount = Decimal(str(base_amount or '0'))
    
    # 1. Gather tax inputs
    taxes = []
    if tax_type1:
        rate = Decimal(str(tax_percent1 if tax_percent1 is not None else tax_type1.rate))
        taxes.append({'type': tax_type1, 'rate': rate, 'index': 1})
    if tax_type2:
        rate = Decimal(str(tax_percent2 if tax_percent2 is not None else tax_type2.rate))
        taxes.append({'type': tax_type2, 'rate': rate, 'index': 2})
        
    # 2. First pass: Identify and calculate Table Tax
    table_tax_val = Decimal('0')
    tax1_val = Decimal('0')
    tax2_val = Decimal('0')
    
    for t in taxes:
        if t['type'].category == 'table':
            val = base_amount * (t['rate'] / Decimal('100'))
            table_tax_val += val
            if t['index'] == 1:
                tax1_val = val
            else:
                tax2_val = val
                
    # 3. Second pass: Calculate other taxes
    for t in taxes:
        if t['type'].category == 'table':
            continue
        elif t['type'].category == 'vat':
            # VAT is calculated on Net + Table Tax
            val = (base_amount + table_tax_val) * (t['rate'] / Decimal('100'))
        else:
            # Others like WHT are calculated directly on Net (base_amount)
            val = base_amount * (t['rate'] / Decimal('100'))
            
        if t['index'] == 1:
            tax1_val = val
        else:
            tax2_val = val

    # Quantize to 2 decimal places to avoid floating point issues
    tax1_val = tax1_val.quantize(Decimal('0.01'))
    tax2_val = tax2_val.quantize(Decimal('0.01'))
    table_tax_val = table_tax_val.quantize(Decimal('0.01'))

    # 4. Determine signs and capitalization
    # Deductions (WHT, salary, insurance) have negative impact on final total
    # Additions (VAT, table, stamp, customs, other) have positive impact
    def get_signed_val(tax_type, val):
        if not tax_type:
            return Decimal('0')
        if tax_type.category in ['wht', 'salary', 'insurance']:
            return -val
        return val

    tax1_signed = get_signed_val(tax_type1, tax1_val)
    tax2_signed = get_signed_val(tax_type2, tax2_val)

    # In purchases and expenses, non-refundable taxes are capitalized
    # Non-refundable categories: table, customs, stamp, other
    capitalized_amount = Decimal('0')
    if is_purchase_or_expense:
        for t, val in [(tax_type1, tax1_val), (tax_type2, tax2_val)]:
            if t and t.category in ['table', 'customs', 'stamp', 'other']:
                capitalized_amount += val

    # Absolute additions and deductions for document summaries
    tax_total_added = Decimal('0')
    tax_total_deducted = Decimal('0')
    for t, val in [(tax_type1, tax1_val), (tax_type2, tax2_val)]:
        if t:
            if t.category in ['wht', 'salary', 'insurance']:
                tax_total_deducted += val
            else:
                tax_total_added += val

    return {
        'tax1_value': tax1_val,
        'tax2_value': tax2_val,
        'tax1_signed': tax1_signed,
        'tax2_signed': tax2_signed,
        'capitalized_amount': capitalized_amount.quantize(Decimal('0.01')),
        'tax_total_added': tax_total_added.quantize(Decimal('0.01')),
        'tax_total_deducted': tax_total_deducted.quantize(Decimal('0.01')),
    }
