"""Receive goods → supplier bill → payment (architecture §6.2 example 8). No expense is booked on payment."""
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from apps.accounting.services.posting import Line, post_entry
from apps.audit.services.log import record as audit
from apps.core.dates import business_date
from apps.core.errors import DomainError
from apps.core.money import money
from apps.core.services.infra import next_number
from apps.inventory.models import GoodsReceipt, GoodsReceiptLine, Product, StockMove, Supplier, SupplierBill, SupplierPayment
from apps.inventory.services import stock

INV_ROLE = {Product.Kind.RETAIL: "INVENTORY_RETAIL", Product.Kind.SUPPLY: "INVENTORY_SUPPLIES"}


@dataclass
class ReceiptLineIn:
    product_id: int
    qty: Decimal
    unit_cost: Decimal


def receive_goods(*, branch, supplier_id, lines: list[ReceiptLineIn], user, notes="") -> GoodsReceipt:
    if not lines:
        raise DomainError(code="receipt_empty")
    supplier = Supplier.objects.filter(id=supplier_id, is_active=True).first() or _raise("supplier_unknown")
    products = {p.id: p for p in Product.objects.filter(id__in=[ln.product_id for ln in lines], is_active=True)}
    today = business_date()
    planned, by_role, total = [], {}, Decimal("0")
    for ln in lines:
        p = products.get(ln.product_id) or _raise("product_unknown")
        qty, cost = Decimal(ln.qty), Decimal(ln.unit_cost)
        if qty <= 0 or cost < 0:
            raise DomainError(code="stock_qty_invalid")
        line_total = money(qty * cost)
        planned.append((p, qty, cost, line_total))
        by_role[INV_ROLE[p.kind]] = by_role.get(INV_ROLE[p.kind], Decimal("0")) + line_total
        total += line_total
    with transaction.atomic():
        seq = next_number(branch.tenant_id, f"grn:{today.year}")
        grn = GoodsReceipt.objects.create(number=f"GRN-{today.year}-{seq:06d}", branch=branch, supplier=supplier,
                                          received_on=today, total=money(total), notes=notes, created_by=user)
        for p, qty, cost, line_total in planned:
            GoodsReceiptLine.objects.create(receipt=grn, product=p, qty=qty, unit_cost=cost, line_total=line_total)
            stock.receive(branch_id=branch.id, product_id=p.id, qty=qty, unit_cost=cost, source=("inventory.grn", grn.id), user=user)
        post_entry(legal_entity_id=branch.legal_entity_id, entry_date=today, user=user, kind="auto", branch_id=branch.id,
                   source_type="inventory.grn", source_id=str(grn.id), event_type="goods.received", memo=f"{grn.number} {supplier.name}",
                   lines=[*[Line(role, debit=v, branch_id=branch.id) for role, v in by_role.items() if v > 0],
                          Line("GRNI", credit=money(total), branch_id=branch.id)])
        audit("inventory.goods_received", tenant_id=branch.tenant_id, actor=user, obj=grn, data={"total": str(grn.total)})
    return grn


def record_bill(*, receipt: GoodsReceipt, supplier_ref, amount, bill_date=None, due_date=None, user) -> SupplierBill:
    amount = money(amount)
    if hasattr(receipt, "bill"):
        raise DomainError(code="bill_exists")
    if amount != receipt.total:
        raise DomainError(code="bill_amount_mismatch", message="Bill differs from the received value — refer to the accountant",
                          details={"received": str(receipt.total)})
    with transaction.atomic():
        bill = SupplierBill.objects.create(receipt=receipt, supplier_ref=supplier_ref.strip(), amount=amount,
                                           bill_date=bill_date or business_date(), due_date=due_date, created_by=user)
        post_entry(legal_entity_id=receipt.branch.legal_entity_id, entry_date=bill.bill_date, user=user, kind="auto",
                   branch_id=receipt.branch_id, source_type="inventory.bill", source_id=str(bill.id), event_type="bill.recorded",
                   memo=f"{receipt.supplier.name} {bill.supplier_ref}",
                   lines=[Line("GRNI", debit=amount, branch_id=receipt.branch_id), Line("AP_SUPPLIERS", credit=amount, branch_id=receipt.branch_id)])
    return bill


def bill_balance(bill) -> Decimal:
    return money(bill.amount - (bill.payments.aggregate(s=Sum("amount"))["s"] or 0))


def pay_bill(*, bill: SupplierBill, amount, reference, user) -> SupplierPayment:
    """Bank/transfer payment of a supplier bill (cash from a drawer is not supported: it would break the count)."""
    amount = money(amount)
    if not reference.strip():
        raise DomainError(code="payment_reference_required")
    with transaction.atomic():
        bill = SupplierBill.objects.select_for_update().select_related("receipt__branch", "receipt__supplier").get(id=bill.id)
        if amount <= 0 or amount > bill_balance(bill):
            raise DomainError(code="overpayment", details={"balance": str(bill_balance(bill))})
        pay = SupplierPayment.objects.create(bill=bill, amount=amount, paid_on=business_date(), reference=reference.strip(), created_by=user)
        br = bill.receipt.branch
        post_entry(legal_entity_id=br.legal_entity_id, entry_date=pay.paid_on, user=user, kind="auto", branch_id=br.id,
                   source_type="inventory.supplier_payment", source_id=str(pay.id), event_type="supplier.paid",
                   memo=f"{bill.receipt.supplier.name} {reference}",
                   lines=[Line("AP_SUPPLIERS", debit=amount, branch_id=br.id), Line("BANK", credit=amount, branch_id=br.id)])
    return pay


def adjust(*, branch, product_id, qty_delta, reason, user) -> StockMove:
    """Stock count correction. Loss/gain goes to cost of goods (policy default, accountant to confirm)."""
    if not reason.strip():
        raise DomainError(code="reason_required")
    p = Product.objects.filter(id=product_id).first() or _raise("product_unknown")
    qty = Decimal(qty_delta)
    with transaction.atomic():
        if qty > 0:
            from apps.inventory.models import StockLevel
            lvl = StockLevel.objects.filter(branch=branch, product=p).first()
            move = stock.receive(branch_id=branch.id, product_id=p.id, qty=qty, unit_cost=lvl.avg_cost if lvl else 0,
                                 kind=StockMove.Kind.ADJUST, source=("inventory.adjust", ""), user=user, reason=reason)
        else:
            move = stock.issue(branch_id=branch.id, product_id=p.id, qty=-qty, kind=StockMove.Kind.ADJUST,
                               source=("inventory.adjust", ""), user=user, reason=reason)
        value = abs(move.value)
        if value > 0:
            inv, gain = INV_ROLE[p.kind], qty > 0
            post_entry(legal_entity_id=branch.legal_entity_id, entry_date=business_date(), user=user, kind="auto", branch_id=branch.id,
                       source_type="inventory.adjust", source_id=str(move.id), event_type="stock.adjusted", memo=reason,
                       lines=[Line(inv, branch_id=branch.id, **({"debit": value} if gain else {"credit": value})),
                              Line("COGS_PRODUCTS", branch_id=branch.id, **({"credit": value} if gain else {"debit": value}))])
        audit("inventory.adjusted", tenant_id=branch.tenant_id, actor=user, obj=move, reason=reason, data={"qty": str(qty)})
    return move


def _raise(code):
    raise DomainError(code=code)
