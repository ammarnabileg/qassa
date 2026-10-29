"""Platform subscription billing (D-010): monthly invoice per company, manual payment recording.

No money moves here and nothing is marked paid without a person recording a reference."""
import calendar
import datetime

from django.db import transaction
from django.utils import timezone

from apps.audit.services.log import record as audit
from apps.core.dates import business_date
from apps.core.errors import DomainError
from apps.platform.models import PlatformInvoice, Subscription
from apps.tenancy.models import Tenant

GRACE_DAYS = 7
BILLABLE = {Tenant.Status.TRIAL, Tenant.Status.ACTIVE, Tenant.Status.PAST_DUE}


def add_month(d: datetime.date, anchor_day: int | None = None) -> datetime.date:
    """Next month on the anchor day (clamped to the month's length), so a 31st does not drift to the 28th forever."""
    y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return datetime.date(y, m, min(anchor_day or d.day, calendar.monthrange(y, m)[1]))


def issue_due(today: datetime.date | None = None) -> list[PlatformInvoice]:
    """Invoice every company whose covered period has ended. Idempotent (one invoice per period)."""
    today = today or business_date()
    out = []
    for sub in Subscription.objects.select_related("tenant", "plan").filter(tenant__status__in=BILLABLE,
                                                                             current_period_end__lte=today):
        with transaction.atomic():
            sub = Subscription.objects.select_for_update().select_related("tenant", "plan").get(id=sub.id)
            while sub.current_period_end <= today:
                start = sub.current_period_end + datetime.timedelta(days=1)
                anchor = (sub.started_on + datetime.timedelta(days=30)).day   # day the first period ended (onboarding)
                end = add_month(sub.current_period_end, anchor_day=anchor)
                inv, created = PlatformInvoice.objects.get_or_create(
                    tenant=sub.tenant, period_start=start,
                    # number = tenant + period start: unique even when two periods start in the same month
                    defaults={"number": f"SUB-{start:%Y%m%d}-{sub.tenant_id:05d}", "plan": sub.plan, "period_end": end,
                              "amount": sub.plan.monthly_price, "due_on": start + datetime.timedelta(days=GRACE_DAYS)})
                sub.current_period_end = end
                if created:
                    out.append(inv)
            sub.save(update_fields=["current_period_end", "updated_at"])
    return out


def mark_overdue(today: datetime.date | None = None) -> int:
    """Active companies with an unpaid invoice past its due date become past_due (never suspended automatically)."""
    today = today or business_date()
    ids = set(PlatformInvoice.objects.filter(status=PlatformInvoice.Status.ISSUED, due_on__lt=today)
              .values_list("tenant_id", flat=True))
    n = 0
    for t in Tenant.objects.filter(id__in=ids, status__in=[Tenant.Status.ACTIVE, Tenant.Status.TRIAL]):
        t.status = Tenant.Status.PAST_DUE
        t.save(update_fields=["status"])
        audit("platform.tenant_past_due", tenant_id=t.id, obj=t, data={"by": "billing"})
        n += 1
    return n


def record_payment(inv: PlatformInvoice, *, method: str, reference: str, user) -> PlatformInvoice:
    if not reference.strip():
        raise DomainError(code="payment_reference_required")
    with transaction.atomic():
        inv = PlatformInvoice.objects.select_for_update().select_related("tenant").get(id=inv.id)
        if inv.status != PlatformInvoice.Status.ISSUED:
            raise DomainError(code="invoice_not_open", details={"status": inv.status})
        inv.status, inv.paid_at, inv.paid_method, inv.paid_reference, inv.recorded_by = (
            PlatformInvoice.Status.PAID, timezone.now(), method, reference.strip(), user)
        inv.save()
        t = inv.tenant
        still_open = PlatformInvoice.objects.filter(tenant=t, status=PlatformInvoice.Status.ISSUED,
                                                    due_on__lt=business_date()).exists()
        if t.status in (Tenant.Status.PAST_DUE, Tenant.Status.TRIAL) and not still_open:
            t.status = Tenant.Status.ACTIVE
            t.save(update_fields=["status"])
        audit("platform.invoice_paid", tenant_id=t.id, actor=user, obj=inv,
              data={"number": inv.number, "amount": str(inv.amount), "method": method, "reference": inv.paid_reference})
    return inv


def void(inv: PlatformInvoice, *, reason: str, user) -> PlatformInvoice:
    if not reason.strip():
        raise DomainError(code="reason_required")
    with transaction.atomic():
        inv = PlatformInvoice.objects.select_for_update().get(id=inv.id)   # not voiding an invoice paid a moment ago
        if inv.status != PlatformInvoice.Status.ISSUED:
            raise DomainError(code="invoice_not_open", details={"status": inv.status})
        inv.status = PlatformInvoice.Status.VOID
        inv.save(update_fields=["status"])
    audit("platform.invoice_void", tenant_id=inv.tenant_id, actor=user, obj=inv, data={"number": inv.number}, reason=reason)
    return inv
