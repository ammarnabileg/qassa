"""Stock movements at weighted-average cost. All writes lock the branch/product level row."""
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction

from apps.core.errors import DomainError
from apps.core.money import money
from apps.inventory.models import StockLevel, StockMove

COST_Q = Decimal("0.000001")


def _level(branch_id, product_id) -> StockLevel:
    StockLevel.objects.get_or_create(branch_id=branch_id, product_id=product_id)
    return StockLevel.objects.select_for_update().get(branch_id=branch_id, product_id=product_id)


def receive(*, branch_id, product_id, qty, unit_cost, kind=StockMove.Kind.RECEIPT, source=("", ""), user=None, reason="") -> StockMove:
    """Stock in at a cost; the average cost is re-weighted."""
    qty, unit_cost = Decimal(qty), Decimal(unit_cost)
    if qty <= 0 or unit_cost < 0:
        raise DomainError(code="stock_qty_invalid")
    with transaction.atomic():
        lvl = _level(branch_id, product_id)
        new_qty = lvl.qty + qty
        lvl.avg_cost = ((lvl.qty * lvl.avg_cost + qty * unit_cost) / new_qty).quantize(COST_Q, ROUND_HALF_UP)
        lvl.qty = new_qty
        lvl.save(update_fields=["qty", "avg_cost"])
        return StockMove.objects.create(branch_id=branch_id, product_id=product_id, kind=kind, qty=qty, unit_cost=unit_cost,
                                        value=money(qty * unit_cost), source_type=source[0], source_id=str(source[1]),
                                        created_by=user, reason=reason)


def issue(*, branch_id, product_id, qty, kind=StockMove.Kind.SALE, source=("", ""), user=None, reason="") -> StockMove:
    """Stock out at the current average cost. Refuses to go below zero."""
    qty = Decimal(qty)
    if qty <= 0:
        raise DomainError(code="stock_qty_invalid")
    with transaction.atomic():
        lvl = _level(branch_id, product_id)
        if lvl.qty < qty:
            raise DomainError(code="stock_insufficient", message="Not enough stock",
                              details={"product": product_id, "available": str(lvl.qty)})
        lvl.qty -= qty
        lvl.save(update_fields=["qty"])
        return StockMove.objects.create(branch_id=branch_id, product_id=product_id, kind=kind, qty=-qty, unit_cost=lvl.avg_cost,
                                        value=-money(qty * lvl.avg_cost), source_type=source[0], source_id=str(source[1]),
                                        created_by=user, reason=reason)
