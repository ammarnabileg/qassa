"""Loyalty points ledger. Points are a marketing discount when redeemed (§6.3 option a); no accounting entry."""
import math
from decimal import Decimal

from django.db.models import Sum

from apps.core.errors import DomainError
from apps.core.money import money
from apps.loyalty.models import LoyaltySettings, PointsEntry


def settings_for():
    return LoyaltySettings.objects.first()


def balance(customer) -> int:
    return PointsEntry.objects.filter(customer=customer).aggregate(s=Sum("points"))["s"] or 0


def record(customer, points: int, kind: str, invoice=None, note=""):
    if points:
        PointsEntry.objects.create(customer=customer, points=points, kind=kind, invoice=invoice, note=note)


def redemption(customer, wanted: int, payable: Decimal) -> tuple[int, Decimal]:
    """Validate a redemption and return (points, discount). Never discounts more than what is payable."""
    cfg = settings_for()
    if cfg is None or not cfg.enabled:
        raise DomainError(code="loyalty_disabled")
    if wanted < cfg.min_redeem:
        raise DomainError(code="points_below_minimum", details={"min": cfg.min_redeem})
    have = balance(customer)
    if wanted > have:
        raise DomainError(code="points_insufficient", details={"balance": have})
    max_points = math.floor(payable / cfg.point_value)
    points = min(wanted, max_points)
    return points, money(points * cfg.point_value)


def lifetime(customer) -> int:
    """Points ever earned (purchases and gifts, net of returns) — what the tier is based on; redemptions don't lower it."""
    return PointsEntry.objects.filter(customer=customer, kind__in=["earn", "reverse", "gift"]).aggregate(s=Sum("points"))["s"] or 0


def tier_for(cfg, earned: int):
    tiers = sorted(cfg.tiers or [], key=lambda t: t["min"]) if cfg else []
    current = None
    for t in tiers:
        if earned >= t["min"]:
            current = t
    return current


def earn(customer, invoice):
    """Earn on what the customer actually paid for (tips and package sessions excluded), once per invoice.
    The tier reached before this invoice multiplies it; a customer's first earning invoice also brings the welcome gift."""
    cfg = settings_for()
    if cfg is None or not cfg.enabled or PointsEntry.objects.filter(invoice=invoice, kind="earn").exists():
        return
    first = not PointsEntry.objects.filter(customer=customer, kind="earn").exists()
    tier = tier_for(cfg, lifetime(customer))
    mul = Decimal(str(tier["mul"])) if tier else Decimal(1)
    points = math.floor(invoice.total * cfg.points_per_kd * mul)
    record(customer, points, "earn", invoice=invoice)
    if first and cfg.welcome_points and not PointsEntry.objects.filter(customer=customer, kind="gift", note="welcome").exists():
        record(customer, cfg.welcome_points, "gift", note="welcome")


def birthday_gifts(today) -> int:
    """Daily, per salon: birthday points for each person on the account (the guardian or a child) born on this day, once a year,
    credited to the account's wallet. Feb 29 birthdays get it on Feb 28 off leap years."""
    import calendar
    from apps.customers.models import Beneficiary
    cfg = settings_for()
    if cfg is None or not cfg.enabled or not cfg.birthday_points:
        return 0
    days = [today.day]
    if today.month == 2 and today.day == 28 and not calendar.isleap(today.year):
        days.append(29)
    n = 0
    for b in Beneficiary.objects.filter(is_active=True, customer__is_active=True, birth_date__month=today.month,
                                        birth_date__day__in=days).select_related("customer"):
        note = f"birthday:{today.year}:{b.id}"
        if not PointsEntry.objects.filter(customer=b.customer, kind="gift", note=note).exists():
            record(b.customer, cfg.birthday_points, "gift", note=note)
            n += 1
    return n


def expire_inactive(today) -> int:
    """Daily, per salon: a positive balance lapses when the customer has had no points activity for expiry_months."""
    import calendar
    from django.db.models import Max
    cfg = settings_for()
    if cfg is None or not cfg.enabled or not cfg.expiry_months:
        return 0
    m = today.year * 12 + today.month - 1 - cfg.expiry_months
    y, mo = divmod(m, 12)
    cutoff = today.replace(year=y, month=mo + 1, day=min(today.day, calendar.monthrange(y, mo + 1)[1]))
    n = 0
    rows = PointsEntry.objects.values("customer_id").annotate(bal=Sum("points"), last=Max("created_at")).filter(bal__gt=0, last__date__lt=cutoff)
    for r in rows:
        PointsEntry.objects.create(customer_id=r["customer_id"], points=-r["bal"], kind="expire", note=f"inactive since {r['last']:%Y-%m-%d}")
        n += 1
    return n


def reverse_for_return(invoice, credit_note):
    earned = PointsEntry.objects.filter(invoice=invoice, kind="earn").aggregate(s=Sum("points"))["s"] or 0
    if earned and invoice.total:
        take = math.ceil(earned * credit_note.total / invoice.total)
        already = -(PointsEntry.objects.filter(invoice=invoice, kind="reverse").aggregate(s=Sum("points"))["s"] or 0)
        take = min(take, earned - already)
        if take > 0:
            record(invoice.customer, -take, "reverse", invoice=invoice, note=credit_note.number)
