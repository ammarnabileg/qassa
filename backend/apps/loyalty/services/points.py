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


def earn(customer, invoice):
    """Earn on what the customer actually paid for (tips and package sessions excluded), once per invoice."""
    cfg = settings_for()
    if cfg is None or not cfg.enabled or PointsEntry.objects.filter(invoice=invoice, kind="earn").exists():
        return
    points = math.floor(invoice.total * cfg.points_per_kd)
    record(customer, points, "earn", invoice=invoice)


def reverse_for_return(invoice, credit_note):
    earned = PointsEntry.objects.filter(invoice=invoice, kind="earn").aggregate(s=Sum("points"))["s"] or 0
    if earned and invoice.total:
        take = math.ceil(earned * credit_note.total / invoice.total)
        already = -(PointsEntry.objects.filter(invoice=invoice, kind="reverse").aggregate(s=Sum("points"))["s"] or 0)
        take = min(take, earned - already)
        if take > 0:
            record(invoice.customer, -take, "reverse", invoice=invoice, note=credit_note.number)
