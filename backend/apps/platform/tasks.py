from celery import shared_task


@shared_task
def daily_billing():
    from apps.platform.services import billing
    issued = billing.issue_due()
    return {"issued": len(issued), "past_due": billing.mark_overdue()}
