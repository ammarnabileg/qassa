from celery import shared_task


@shared_task
def daily_loyalty():
    """Birthday gifts and inactivity expiry for every salon that has the loyalty programme on."""
    from django.db import transaction

    from apps.core.dates import business_date
    from apps.loyalty.models import LoyaltySettings
    from apps.loyalty.services import points
    from apps.tenancy.context import tenant_context
    today = business_date()
    out = {"birthday": 0, "expired": 0}
    for tid in LoyaltySettings.unscoped.filter(enabled=True).values_list("tenant_id", flat=True):
        with tenant_context(tid), transaction.atomic():
            out["birthday"] += points.birthday_gifts(today)
            out["expired"] += points.expire_inactive(today)
    return out
