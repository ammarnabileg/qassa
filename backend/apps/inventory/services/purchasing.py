"""Receive goods → supplier bill → payment (architecture §6.2 example 8). No expense is booked on payment."""
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from apps.accounting.services.posting import Line, post_entry
from apps.audit.services.log import record as audit
from apps.core.dates import accounting_date, business_date
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
    today = accounting_date()   # goods arrive on a calendar date, not a shift
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


COST_ROLE = {Product.Kind.RETAIL: "COGS_PRODUCTS", Product.Kind.SUPPLY: "COST_OF_SERVICES_SUPPLIES"}


def bill_difference_split(receipt: GoodsReceipt, diff: Decimal) -> list[dict]:
    """Where a bill/receipt price difference goes (accountant's review): per receipt line in proportion to its value;
    the part matching what is still on the shelf goes to inventory (and its average cost), the part already sold or used
    to cost of sales / supplies consumed."""
    from apps.core.money import allocate
    from apps.inventory.models import StockLevel
    lines = list(receipt.lines.select_related("product"))
    shares = allocate(diff, [ln.line_total for ln in lines]) if diff else [Decimal("0")] * len(lines)
    out = []
    for ln, share in zip(lines, shares):
        lvl = StockLevel.objects.filter(branch_id=receipt.branch_id, product_id=ln.product_id).first()
        on_hand = min(max(lvl.qty if lvl else Decimal("0"), Decimal("0")), ln.qty)
        to_stock = money(share * on_hand / ln.qty) if ln.qty else Decimal("0")
        out.append({"product": ln.product, "level": lvl, "on_hand": on_hand, "to_stock": to_stock, "to_cost": money(share - to_stock)})
    return out


def record_bill(*, receipt: GoodsReceipt, supplier_ref, amount, bill_date=None, due_date=None, user,
                accept_difference=False, note="") -> SupplierBill:
    """Supplier bill against a receipt. A different amount is refused unless the accountant accepts the difference
    (with a note): it is then split between stock still on hand and cost of what was already sold or used."""
    amount = money(amount)
    if hasattr(receipt, "bill"):
        raise DomainError(code="bill_exists")
    diff = money(amount - receipt.total)
    if diff and not accept_difference:
        raise DomainError(code="bill_amount_mismatch", message="Bill differs from the received value — refer to the accountant",
                          details={"received": str(receipt.total), "difference": str(diff)})
    if diff and not note.strip():
        raise DomainError(code="reason_required")
    with transaction.atomic():
        bill = SupplierBill.objects.create(receipt=receipt, supplier_ref=supplier_ref.strip(), amount=amount,
                                           bill_date=bill_date or accounting_date(), due_date=due_date, created_by=user)
        br = receipt.branch_id
        lines = [Line("GRNI", debit=receipt.total, branch_id=br)]
        for part in bill_difference_split(receipt, diff) if diff else []:
            kind = part["product"].kind
            for role, v in ((INV_ROLE[kind], part["to_stock"]), (COST_ROLE[kind], part["to_cost"])):
                if v:
                    lines.append(Line(role, branch_id=br, description=f"price difference {part['product'].sku}",
                                      **({"debit": v} if v > 0 else {"credit": -v})))
            if part["to_stock"] and part["level"] is not None and part["level"].qty > 0:   # keep the stock card = ledger
                lvl = part["level"]
                lvl.avg_cost = (lvl.qty * lvl.avg_cost + part["to_stock"]) / lvl.qty
                lvl.save(update_fields=["avg_cost"])
        lines.append(Line("AP_SUPPLIERS", credit=amount, branch_id=br))
        post_entry(legal_entity_id=receipt.branch.legal_entity_id, entry_date=bill.bill_date, user=user, kind="auto",
                   branch_id=br, source_type="inventory.bill", source_id=str(bill.id), event_type="bill.recorded",
                   memo=f"{receipt.supplier.name} {bill.supplier_ref}" + (f" — difference {diff}: {note.strip()}" if diff else ""), lines=lines)
        if diff:
            audit("inventory.bill_difference", tenant_id=receipt.tenant_id, actor=user, obj=bill, reason=note.strip(),
                  data={"received": str(receipt.total), "billed": str(amount), "difference": str(diff)})
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


ADJUST_ROLE = {  # accountant's review: supplies are not cost of products sold; losses get their own account
    "count": {Product.Kind.RETAIL: "COGS_PRODUCTS", Product.Kind.SUPPLY: "COST_OF_SERVICES_SUPPLIES"},
    "consumed": {Product.Kind.RETAIL: "COGS_PRODUCTS", Product.Kind.SUPPLY: "COST_OF_SERVICES_SUPPLIES"},
    "damaged": {Product.Kind.RETAIL: "INVENTORY_LOSSES", Product.Kind.SUPPLY: "INVENTORY_LOSSES"},
    "shrinkage": {Product.Kind.RETAIL: "INVENTORY_LOSSES", Product.Kind.SUPPLY: "INVENTORY_LOSSES"},
}


def adjust(*, branch, product_id, qty_delta, reason, user, cause="count") -> StockMove:
    """Stock correction. cause: count (stock-take difference), consumed (supplies used in services), damaged,
    shrinkage (missing). The other side follows the item's kind and the cause (ADJUST_ROLE)."""
    if cause not in ADJUST_ROLE:
        raise DomainError(code="adjust_cause_unknown")
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
            post_entry(legal_entity_id=branch.legal_entity_id, entry_date=accounting_date(), user=user, kind="auto", branch_id=branch.id,
                       source_type="inventory.adjust", source_id=str(move.id), event_type="stock.adjusted", memo=reason,
                       lines=[Line(inv, branch_id=branch.id, **({"debit": value} if gain else {"credit": value})),
                              Line(ADJUST_ROLE[cause][p.kind], branch_id=branch.id, **({"credit": value} if gain else {"debit": value}))])
        audit("inventory.adjusted", tenant_id=branch.tenant_id, actor=user, obj=move, reason=reason, data={"qty": str(qty), "cause": cause})
    return move


def _raise(code):
    raise DomainError(code=code)
