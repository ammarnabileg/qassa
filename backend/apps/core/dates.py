"""Salon business day: a shift that crosses midnight belongs to the previous day (BUSINESS_DAY_START_HOUR)."""
from datetime import date, datetime, timedelta

from django.conf import settings
from django.utils import timezone


def business_date(at: datetime | None = None) -> date:
    at = timezone.localtime(at or timezone.now())
    return (at - timedelta(hours=settings.QASSA["BUSINESS_DAY_START_HOUR"])).date()


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """[start, end) of a business day as aware datetimes."""
    start = timezone.make_aware(datetime.combine(day, datetime.min.time())) + timedelta(
        hours=settings.QASSA["BUSINESS_DAY_START_HOUR"])
    return start, start + timedelta(days=1)


def accounting_date(at: datetime | None = None) -> date:
    """The calendar date (Kuwait) on which the transaction really happened — the date of its journal entry.
    The business day above is for shift and drawer reports only: a sale at 02:00 on 1 January belongs to the
    31 December shift but to January (and the new year) in the books (accountant's review, 2026-11)."""
    return timezone.localtime(at or timezone.now()).date()
