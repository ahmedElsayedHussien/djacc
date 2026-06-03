from django.conf import settings

class AccountCodes:
    """مرجع موحد لأكواد الحسابات المحاسبية
    يضمن استخدام نفس الكود في كل مكان بدلاً من الكتابة الثابتة"""

    # الحسابات الرئيسية
    ASSETS = '1'
    LIABILITIES = '2'
    EQUITY = '3'
    REVENUE = '4'
    EXPENSES = '5'

    # الأصول
    CASH_BOXES = '1111'
    BANKS = '1112'
    CASH_IN_TRANSIT = lambda: getattr(settings, 'CASH_IN_TRANSIT_ACCOUNT', '1114')
    CUSTOMERS = lambda: getattr(settings, 'CUSTOMERS_PARENT_ACCOUNT', '1121')
    SUPPLIERS = lambda: getattr(settings, 'SUPPLIERS_PARENT_ACCOUNT', '2111')
    INVENTORY = lambda: getattr(settings, 'DEFAULT_INVENTORY_ACCOUNT', '1131')
    CHEQUES_UNDER_COLLECTION = lambda: getattr(settings, 'CHEQUES_UNDER_COLLECTION_ACCOUNT', '1151')
    REP_RECEIVABLE = lambda: getattr(settings, 'SALES_REP_RECEIVABLE_PARENT', '1141')
    REP_INVENTORY = lambda: getattr(settings, 'SALES_REP_INVENTORY_PARENT', '1134')
    CUSTODY = lambda: getattr(settings, 'CUSTODY_ACCOUNTS_PARENT', '1142')
    LOANS = lambda: getattr(settings, 'LOANS_RECEIVABLE_ACCOUNT', '1143')

    # الخصوم
    CHEQUES_ISSUED = lambda: getattr(settings, 'CHEQUES_ISSUED_ACCOUNT', '2141')
    INSURANCE_PAYABLE = lambda: getattr(settings, 'INSURANCE_PAYABLE_ACCOUNT', '2133')
    SALARIES_PAYABLE = lambda: getattr(settings, 'SALARIES_PAYABLE_ACCOUNT', '2132')
    INCOME_TAX_PAYABLE = lambda: getattr(settings, 'INCOME_TAX_PAYABLE_ACCOUNT', '2125')
    OTHER_DEDUCTIONS = lambda: getattr(settings, 'OTHER_DEDUCTIONS_ACCOUNT', '2126')

    # حقوق الملكية
    OPENING_BALANCES = lambda: getattr(settings, 'OPENING_BALANCES_ACCOUNT', '35')
    RETAINED_EARNINGS = lambda: getattr(settings, 'RETAINED_EARNINGS_ACCOUNT', '34')

    # الإيرادات
    SALES_REVENUE = lambda: getattr(settings, 'DEFAULT_SALES_ACCOUNT', '411')
    SALES_RETURNS = lambda: getattr(settings, 'DEFAULT_SALES_RETURN_ACCOUNT', '413')
    SALES_DISCOUNT = lambda: getattr(settings, 'SALES_DISCOUNT_ACCOUNT', '414')
    INTEREST_REVENUE = lambda: getattr(settings, 'INTEREST_REVENUE_ACCOUNT', '421')
    GAIN_ON_DISPOSAL = lambda: getattr(settings, 'GAIN_ON_DISPOSAL_ACCOUNT', '4210')

    # المصروفات
    COGS = lambda: getattr(settings, 'DEFAULT_COGS_ACCOUNT', '511')
    SALARY = lambda: getattr(settings, 'SALARY_ACCOUNT', '5210')
    ALLOWANCES = lambda: getattr(settings, 'ALLOWANCES_ACCOUNT', '5213')
    INSURANCE_EXPENSE = lambda: getattr(settings, 'INSURANCE_EXPENSE_ACCOUNT', '5214')
    EOS_EXPENSE = lambda: getattr(settings, 'EOS_EXPENSE_ACCOUNT', '5215')
    BANK_CHARGES = lambda: getattr(settings, 'BANK_CHARGES_ACCOUNT', '531')
    LOSS_ON_DISPOSAL = lambda: getattr(settings, 'LOSS_ON_DISPOSAL_ACCOUNT', '5261')
