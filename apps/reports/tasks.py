from celery import shared_task
from .services import ReportService
from apps.core.models import FiscalYear
from datetime import date

@shared_task
def generate_trial_balance_task(as_of_date_str):
    as_of_date = date.fromisoformat(as_of_date_str)
    fiscal_year = FiscalYear.objects.filter(is_closed=False).first()
    if fiscal_year:
        return ReportService.trial_balance(fiscal_year.start_date, as_of_date)
    return []
