
🔴 1. balance_sheet بيحسب صافي الربح من أول يناير دايماً
pythonfirst_day_of_year = date(as_of_date.year, 1, 1)  # ❌ hardcoded
income_stmt = ReportService.income_statement(first_day_of_year, as_of_date)
لو السنة المالية مش كالنداريه (مثلاً بتبدأ أبريل أو يوليو) — ده شائع جداً — الربح اللي هيظهر في الميزانية هيكون غلط. المفروض:
pythonfiscal_year = FiscalYear.objects.get(start_date__lte=as_of_date, end_date__gte=as_of_date)
income_stmt = ReportService.income_statement(fiscal_year.start_date, as_of_date)

🔴 2. customer_statement بيتجاهل initial_balance للعميل
account_statement بيتحقق من has_opening_entry ويضيف initial_balance لو مفيش قيد افتتاحي — ده صح. لكن customer_statement مش بيعمل ده:
pythonpre_movements = JournalLine.objects.filter(..., entry__date__lt=from_date).aggregate(...)
opening_balance = (pre_movements['d'] or 0) - (pre_movements['c'] or 0)
# ❌ مفيش إضافة للـ initial_balance
يعني أي عميل عنده رصيد افتتاحي (مديونية قبل النظام) هيظهر كشف حسابه غلط من اليوم الأول.

🔴 3. close_fiscal_year بيعمل get(code='34') بدون حماية
pythonprofit_loss_acc = Account.objects.get(code='34')
لو حساب 34 اتحذف أو اتغير كوده، العملية كلها هتفشل بـ DoesNotExist داخل transaction.atomic وكل الحسابات اللي اتحسبت هتتلغي. المفروض تتحقق قبل البدء:
pythontry:
    profit_loss_acc = Account.objects.get(code=getattr(settings, 'RETAINED_EARNINGS_ACCOUNT', '34'))
except Account.DoesNotExist:
    raise ValueError("حساب الأرباح المرحلة غير موجود — تحقق من إعدادات النظام")
وكمان RETAINED_EARNINGS_ACCOUNT يتضاف للـ settings بدل ما يكون hardcoded.

🟠 4. process_transfer في treasury مفيش تحقق من الحالة
pythondef process_transfer(transfer, posted_by) -> JournalEntry:
    # مفيش: if transfer.status == 'posted': raise ValueError(...)
    ...
    transfer.journal_entry = entry
    transfer.save()
لو الـ view اتضغطت مرتين، هيتعمل قيدين للتحويل نفسه. كل services التانية عندها الـ guard ده ما عدا هنا.

🟡 5. N+1 queries في balance_sheet وtrial_balance
في balance_sheet، لكل حساب (أصول، خصوم، ملكية) بيتعمل query منفصل للحركات + query لـ has_opening:
pythonfor acc in asset_accounts:           # فرضاً 50 حساب
    val = JournalLine.objects.filter(account=acc, ...).aggregate(...)   # query
    has_opening = JournalLine.objects.filter(account=acc, ...).exists() # query
يعني لو عندك 100 حساب ورقي → 200+ query في request واحد. نفس المشكلة في trial_balance بـ 3 queries لكل حساب. الحل هو aggregation واحدة على كل الحسابات:
pythonJournalLine.objects.filter(entry__is_posted=True, entry__date__lte=as_of_date)\
    .values('account_id')\
    .annotate(total_debit=Sum('debit'), total_credit=Sum('credit'))
وتبني الـ dict منها بدل loop.