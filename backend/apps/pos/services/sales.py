"""Checkout, collections, returns and the cash drawer. Prices always come from the server's price list."""
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.audit.services.log import record as audit
from apps.booking.models import Appointment
from apps.catalog.models import Service
from apps.catalog.services.pricing import price_on
from apps.core.dates import business_date
from apps.core.errors import ConflictError, DomainError
from apps.core.money import money
from apps.core.services.infra import next_number
from apps.customers.models import Beneficiary, Customer
from apps.pos.models import CashSession, CreditNote, CreditNoteLine, Invoice, InvoiceLine, Payment
from apps.pos.services import ledger
from apps.staff.models import StaffMember
from apps.tenancy.models import Branch

ZERO = Decimal("0.000")


@dataclass
class LineIn:
    service_id: int | None = None
    qty: int = 1
    discount: Decimal = ZERO
    staff_id: int | None = None
    product_id: int | None = None          # a retail product
    package_plan_id: int | None = None     # sell a package
    redeem_package_id: int | None = None   # pay this service with one session of the customer's package


@dataclass
class PaymentIn:
    method: str
    amount: Decimal
    reference: str = ""


@dataclass
class CheckoutIn:
    branch: Branch
    lines: list[LineIn]
    payments: list[PaymentIn] = field(default_factory=list)
    customer_id: int | None = None
    beneficiary_id: int | None = None
    appointment_id: int | None = None
    expected_total: Decimal | None = None  # what the cashier saw; a mismatch means prices changed meanwhile
    coupon_code: str = ""
    redeem_points: int = 0
    tip: Decimal = ZERO
    tip_staff_id: int | None = None


# ---------- cash drawer ----------
def open_session(branch: Branch, opening_float, user) -> CashSession:
    try:
        with transaction.atomic():
            s = CashSession.objects.create(branch=branch, opening_float=money(opening_float), opened_by=user)
    except IntegrityError:
        raise ConflictError(code="session_already_open", message="This branch already has an open drawer")
    audit("cash.session.opened", tenant_id=s.tenant_id, actor=user, obj=s, data={"float": str(s.opening_float)})
    return s


def open_session_for(branch_id) -> CashSession | None:
    return CashSession.objects.filter(branch_id=branch_id, status=CashSession.Status.OPEN).first()


def expected_cash(session: CashSession) -> Decimal:
    def total(direction):
        return session.payments.filter(method="cash", direction=direction).aggregate(s=Sum("amount"))["s"] or ZERO
    return money(session.opening_float + total("in") - total("out"))


# Kuwaiti dinar notes and coins, largest first (value in KWD)
DENOMINATIONS = ["20.000", "10.000", "5.000", "1.000", "0.500", "0.250", "0.100", "0.050", "0.020", "0.010", "0.005"]


def count_denominations(counts: dict) -> tuple[Decimal, dict]:
    """Total of a drawer count. Unknown denominations, negative or non-integer counts are refused."""
    clean, total = {}, Decimal("0.000")
    for key, n in (counts or {}).items():
        if key not in DENOMINATIONS:
            raise DomainError(code="denomination_unknown", details={"denomination": key})
        if not isinstance(n, int) or isinstance(n, bool) or n < 0 or n > 100000:
            raise DomainError(code="denomination_count_invalid", details={"denomination": key})
        if n:
            clean[key] = n
            total += Decimal(key) * n
    return money(total), clean


def close_session(session: CashSession, counted, user, notes="", denominations=None) -> CashSession:
    with transaction.atomic():
        s = CashSession.objects.select_for_update().get(id=session.id)
        if s.status != CashSession.Status.OPEN:
            raise DomainError(code="session_not_open")
        s.expected_cash = expected_cash(s)
        if denominations:  # the server computes the total from the count; a typed total is ignored
            counted, s.denominations = count_denominations(denominations)
        elif counted is None:
            raise DomainError(code="count_required")
        s.counted_cash = money(counted)
        s.variance = money(s.counted_cash - s.expected_cash)
        s.status, s.closed_by, s.closed_at, s.notes = CashSession.Status.CLOSED, user, timezone.now(), notes
        s.variance_status = CashSession.Variance.NONE if s.variance == 0 else CashSession.Variance.PENDING
        s.save()
        audit("cash.session.closed", tenant_id=s.tenant_id, actor=user, obj=s,
              data={"expected": str(s.expected_cash), "counted": str(s.counted_cash), "variance": str(s.variance),
                    "denominations": s.denominations})
    return s


def approve_variance(session: CashSession, user, membership) -> CashSession:
    with transaction.atomic():
        s = CashSession.objects.select_for_update().select_related("branch").get(id=session.id)
        if s.variance_status != CashSession.Variance.PENDING:
            raise DomainError(code="variance_not_pending")
        if user.id in {s.closed_by_id, s.opened_by_id}:
            raise DomainError(code="variance_self_approval", message="The person who ran the drawer cannot approve its variance")
        ledger.post_cash_variance(s, s.branch.legal_entity_id, user)
        s.variance_status, s.variance_approved_by = CashSession.Variance.APPROVED, user
        s.save(update_fields=["variance_status", "variance_approved_by"])
        audit("cash.variance.approved", tenant_id=s.tenant_id, actor=user, obj=s, data={"variance": str(s.variance)})
    return s


# ---------- invoice balance ----------
def invoice_state(inv: Invoice) -> dict:
    agg = {d: inv.payments.filter(direction=d).aggregate(s=Sum("amount"))["s"] or ZERO for d in ("in", "out")}
    credited = inv.credit_notes.aggregate(s=Sum("total"))["s"] or ZERO
    paid = money(agg["in"] - agg["out"])
    return {"paid": paid, "credited": money(credited), "balance": money(inv.total + inv.tip - credited - paid),
            "refundable": paid}


def _take_payments(inv, payments: list[PaymentIn], user, session_needed_branch):
    created = []
    for p in payments:
        amount = money(p.amount)
        if amount <= 0:
            continue
        if p.method not in Payment.Method.values:
            raise DomainError(code="payment_method_unknown")
        if p.method != "cash" and not p.reference.strip():
            raise DomainError(code="payment_reference_required", details={"method": p.method})
        session = None
        if p.method == "cash":
            session = open_session_for(session_needed_branch)
            if session is None:
                raise DomainError(code="no_open_session", message="Open the cash drawer first")
        pay = Payment.objects.create(branch_id=inv.branch_id, invoice=inv, direction="in", method=p.method, amount=amount,
                                     reference=p.reference.strip(), cash_session=session,
                                     business_date=business_date(), received_by=user)
        ledger.post_payment(pay, inv, user)
        created.append(pay)
    return created


# ---------- checkout ----------
def _plan_lines(data: CheckoutIn, branch, today, customer):
    """Price every line from the server's data. Returns planned lines: dicts with everything needed to write them."""
    from apps.inventory.models import Product, StockLevel
    from apps.loyalty.models import CustomerPackage, PackagePlan
    planned = []
    for i, ln in enumerate(data.lines):
        if ln.qty < 1 or ln.qty > 50:
            raise DomainError(code="qty_invalid", details={"position": i})
        if ln.staff_id and not StaffMember.objects.filter(id=ln.staff_id).exists():
            raise DomainError(code="staff_unknown", details={"position": i})
        disc = money(ln.discount or 0)
        if ln.product_id:
            p = Product.objects.filter(id=ln.product_id, is_active=True, kind=Product.Kind.RETAIL).first()
            if p is None or p.sale_price is None:
                raise DomainError(code="product_unknown", details={"position": i})
            lvl = StockLevel.objects.filter(branch=branch, product=p).first()
            if lvl is None or lvl.qty < ln.qty:
                raise DomainError(code="stock_insufficient", details={"position": i, "available": str(lvl.qty if lvl else 0)})
            planned.append(dict(kind="product", product=p, name_ar=p.name_ar, name_en=p.name_en, price=p.sale_price, ln=ln, disc=disc))
            continue
        if ln.package_plan_id:
            plan = PackagePlan.objects.select_related("service__category").filter(id=ln.package_plan_id, is_active=True).first()
            if plan is None or plan.service.category.business_type != branch.business_type:
                raise DomainError(code="package_unknown", details={"position": i})
            if customer is None:
                raise DomainError(code="package_needs_customer")
            if ln.qty != 1:
                raise DomainError(code="qty_invalid", details={"position": i})
            planned.append(dict(kind="package", plan=plan, service=plan.service, name_ar=plan.name_ar, name_en=plan.name_en,
                                price=plan.price, ln=ln, disc=disc))
            continue
        svc = Service.objects.select_related("category").filter(id=ln.service_id, is_active=True).first()
        if svc is None:
            raise DomainError(code="service_unknown", details={"position": i})
        if svc.category.business_type != branch.business_type:
            raise DomainError(code="service_not_for_branch", details={"position": i})
        if ln.redeem_package_id:
            pkg = (CustomerPackage.objects.select_for_update().filter(id=ln.redeem_package_id, customer=customer, voided=False).first()
                   if customer else None)
            if pkg is None or pkg.service_id != svc.id:
                raise DomainError(code="package_unknown", details={"position": i})
            if pkg.expires_on < today:
                raise DomainError(code="package_expired", details={"position": i})
            if pkg.sessions_left < ln.qty:
                raise DomainError(code="package_used_up", details={"position": i})
            # the session is valued at what the customer paid for it; the line itself costs nothing now
            planned.append(dict(kind="service", service=svc, name_ar=svc.name_ar, name_en=svc.name_en, price=pkg.session_value,
                                ln=ln, disc=money(pkg.session_value * ln.qty), package=pkg))
            continue
        price = price_on(svc, branch.id, today)
        if price is None:
            raise DomainError(code="service_has_no_price", details={"position": i, "service": svc.id})
        planned.append(dict(kind="service", service=svc, name_ar=svc.name_ar, name_en=svc.name_en, price=price, ln=ln, disc=disc))
    for p in planned:
        p["gross"] = money(p["price"] * p["ln"].qty)
        if p["disc"] < 0 or p["disc"] > p["gross"]:
            raise DomainError(code="discount_invalid")
    return planned


def _apply_promotions(planned, data, customer, today):
    """Coupon and points discounts, spread over the payable lines in proportion (not on package redemptions)."""
    from apps.core.money import allocate
    from apps.loyalty.models import Coupon
    from apps.loyalty.services import points as pts
    payable = [p for p in planned if "package" not in p and p["gross"] - p["disc"] > 0]
    base = money(sum((p["gross"] - p["disc"] for p in payable), ZERO))
    coupon, coupon_disc, points, points_disc = None, ZERO, 0, ZERO
    if data.coupon_code.strip():
        coupon = Coupon.objects.select_for_update().filter(code__iexact=data.coupon_code.strip(), is_active=True).first()
        if coupon is None or not (coupon.valid_from <= today <= coupon.valid_to):
            raise DomainError(code="coupon_invalid")
        if coupon.max_uses is not None and coupon.used_count >= coupon.max_uses:
            raise DomainError(code="coupon_used_up")
        if base < coupon.min_total:
            raise DomainError(code="coupon_min_total", details={"min_total": str(coupon.min_total)})
        coupon_disc = money(base * coupon.value / 100) if coupon.kind == Coupon.Kind.PERCENT else min(money(coupon.value), base)
    if data.redeem_points:
        if customer is None:
            raise DomainError(code="points_need_customer")
        points, points_disc = pts.redemption(customer, data.redeem_points, money(base - coupon_disc))
    extra = money(coupon_disc + points_disc)
    if extra > 0 and payable:
        weights = [p["gross"] - p["disc"] for p in payable]
        for p, share in zip(payable, allocate(extra, weights)):
            p["promo"] = share
    return coupon, coupon_disc, points, points_disc


def checkout(data: CheckoutIn, *, user, membership) -> Invoice:
    from apps.inventory.services import stock
    from apps.loyalty.models import CustomerPackage
    from apps.loyalty.services import points as pts
    from apps.staff.services import commissions
    if not data.lines:
        raise DomainError(code="invoice_empty")
    branch = data.branch
    today = business_date()
    customer = beneficiary = appointment = None
    if data.customer_id:
        customer = Customer.objects.filter(id=data.customer_id).first() or _raise("customer_unknown")
    if data.beneficiary_id:
        beneficiary = Beneficiary.objects.filter(id=data.beneficiary_id, customer=customer).first() or _raise("beneficiary_unknown")

    with transaction.atomic():
        if data.appointment_id:
            appointment = (Appointment.objects.select_for_update().filter(id=data.appointment_id, branch=branch).first()
                           or _raise("appointment_unknown"))
            if appointment.status == Appointment.Status.INVOICED:
                raise ConflictError(code="appointment_already_invoiced")
            if appointment.status not in {Appointment.Status.COMPLETED, Appointment.Status.IN_SERVICE,
                                          Appointment.Status.ARRIVED, Appointment.Status.BOOKED}:
                raise DomainError(code="appointment_not_billable", details={"status": appointment.status})
            customer = customer or appointment.customer
            beneficiary = beneficiary or appointment.beneficiary

        planned = _plan_lines(data, branch, today, customer)
        # the cashier's own discount limit applies to manual discounts only (not coupons, points or packages)
        max_pct = max((p["disc"] * 100 / p["gross"] for p in planned if "package" not in p and p["gross"] > 0), default=ZERO)
        approved_by = None
        if max_pct > membership.discount_limit_percent:
            if not membership.has_perm("pos.discount.override"):
                raise DomainError(code="discount_over_limit", details={"limit": str(membership.discount_limit_percent)})
            approved_by = user
        coupon, coupon_disc, points, points_disc = _apply_promotions(planned, data, customer, today)
        for p in planned:
            p["disc"] = money(p["disc"] + p.get("promo", ZERO))
            p["total"] = money(p["gross"] - p["disc"])
        subtotal = money(sum((p["gross"] for p in planned), ZERO))
        discount_total = money(sum((p["disc"] for p in planned), ZERO))
        total = money(subtotal - discount_total)
        tip = money(data.tip or 0)
        if tip < 0:
            raise DomainError(code="tip_invalid")
        if tip > 0 and not data.tip_staff_id:
            raise DomainError(code="tip_needs_staff")

        if data.expected_total is not None and money(data.expected_total) != total:
            raise ConflictError(code="price_changed", message="Prices changed; review the cart", details={"total": str(total)})
        paying = money(sum((money(p.amount) for p in data.payments), ZERO))
        if paying > total + tip:
            raise DomainError(code="overpayment", details={"total": str(total + tip), "paying": str(paying)})
        is_credit = paying < total + tip
        if is_credit:
            if not membership.has_perm("pos.credit_sale"):
                raise DomainError(code="credit_sale_forbidden")
            if customer is None:
                raise DomainError(code="credit_sale_needs_customer")
            if tip > 0:
                raise DomainError(code="tip_needs_full_payment")

        seq = next_number(branch.tenant_id, f"invoice:{branch.legal_entity_id}:{today.year}")
        inv = Invoice.objects.create(
            legal_entity_id=branch.legal_entity_id, branch=branch, number=f"INV-{today.year}-{seq:06d}",
            customer=customer, beneficiary=beneficiary, appointment=appointment, cash_session=open_session_for(branch.id),
            subtotal=subtotal, discount_total=discount_total, total=total, is_credit=is_credit, business_date=today,
            issued_by=user, discount_approved_by=approved_by, coupon=coupon, points_redeemed=points, tip=tip,
            tip_staff_id=data.tip_staff_id if tip > 0 else None)
        lines = []
        for p in planned:
            ln = p["ln"]
            cost = ZERO
            if p["kind"] == "product":
                move = stock.issue(branch_id=branch.id, product_id=p["product"].id, qty=ln.qty, source=("pos.invoice", inv.id), user=user)
                cost = move.unit_cost
            line = InvoiceLine.objects.create(
                invoice=inv, kind=p["kind"], service=p.get("service") if p["kind"] != "product" else None,
                product=p.get("product"), package_plan=p.get("plan"), redeemed_package=p.get("package"),
                staff_id=ln.staff_id, name_ar=p["name_ar"], name_en=p["name_en"], qty=ln.qty, unit_price=p["price"],
                discount=p["disc"], line_total=p["total"], unit_cost=cost)
            if p["kind"] == "package":
                plan = p["plan"]
                CustomerPackage.objects.create(customer=customer, plan=plan, service=plan.service, sold_on_line=line,
                                               sessions_total=plan.sessions, sessions_left=plan.sessions,
                                               session_value=money(line.line_total / plan.sessions),
                                               expires_on=today + __import__("datetime").timedelta(days=plan.validity_days))
            if "package" in p:
                CustomerPackage.objects.filter(id=p["package"].id).update(sessions_left=p["package"].sessions_left - ln.qty)
            lines.append(line)
        ledger.post_invoice(inv, lines, user)
        ledger.post_cogs(inv, lines, user)
        ledger.post_package_redemptions(inv, lines, user)
        if tip > 0:
            ledger.post_tip(inv, user)
        commissions.accrue(inv, lines, user)
        if coupon is not None:
            from apps.loyalty.models import Coupon
            Coupon.objects.filter(id=coupon.id).update(used_count=coupon.used_count + 1)
        if points:
            pts.record(customer, -points, "redeem", invoice=inv)
        _take_payments(inv, data.payments, user, branch.id)
        if not is_credit and customer is not None:
            pts.earn(customer, inv)
        if appointment is not None:
            Appointment.objects.filter(id=appointment.id).update(status=Appointment.Status.INVOICED, updated_at=timezone.now())
        audit("pos.invoice.issued", tenant_id=inv.tenant_id, actor=user, obj=inv,
              data={"number": inv.number, "total": str(total), "paid": str(paying), "credit": is_credit, "tip": str(tip),
                    "coupon": coupon.code if coupon else "", "points": points})
    return inv


def collect(inv: Invoice, payments: list[PaymentIn], *, user) -> list[Payment]:
    from apps.loyalty.services import points as pts
    with transaction.atomic():
        inv = Invoice.objects.select_for_update().get(id=inv.id)
        state = invoice_state(inv)
        paying = money(sum((money(p.amount) for p in payments), ZERO))
        if paying <= 0:
            raise DomainError(code="payment_empty")
        if paying > state["balance"]:
            raise DomainError(code="overpayment", details={"balance": str(state["balance"])})
        created = _take_payments(inv, payments, user, inv.branch_id)
        if inv.customer_id and invoice_state(inv)["balance"] == 0:
            pts.earn(inv.customer, inv)  # credit invoices earn points once fully paid
        audit("pos.invoice.collected", tenant_id=inv.tenant_id, actor=user, obj=inv, data={"amount": str(paying)})
    return created


def credit_note(inv: Invoice, *, lines: list[tuple], reason: str, refund: PaymentIn | None, user) -> CreditNote:
    """Return part or all of an invoice. lines: (invoice_line_id, amount[, restock_qty]).
    Products may go back to stock at their original cost; commissions and earned points are reversed in proportion;
    a sold package can be returned only while unused."""
    from apps.inventory.services import stock
    from apps.loyalty.models import CustomerPackage
    from apps.loyalty.services import points as pts
    from apps.staff.services import commissions
    if not reason.strip():
        raise DomainError(code="reason_required")
    with transaction.atomic():
        inv = Invoice.objects.select_for_update().get(id=inv.id)
        inv_lines = {ln.id: ln for ln in inv.lines.all()}
        total, planned = ZERO, []
        for item in lines:
            line_id, amount = item[0], money(item[1])
            restock = int(item[2]) if len(item) > 2 and item[2] else 0
            ln = inv_lines.get(line_id) or _raise("invoice_line_unknown")
            already = ln.credit_lines.aggregate(s=Sum("amount"))["s"] or ZERO
            if amount <= 0 or amount > ln.line_total - already:
                raise DomainError(code="return_exceeds_line", details={"line": line_id, "max": str(ln.line_total - already)})
            if restock and (ln.kind != "product" or restock > ln.qty - (ln.credit_lines.aggregate(s=Sum("restock_qty"))["s"] or 0)):
                raise DomainError(code="restock_invalid", details={"line": line_id})
            if ln.kind == "package":
                pkg = CustomerPackage.objects.select_for_update().get(sold_on_line=ln)
                if pkg.sessions_left != pkg.sessions_total or amount != ln.line_total:
                    raise DomainError(code="package_already_used", message="A package can be returned in full only before any use")
            planned.append((ln, amount, restock))
            total += amount
        if not planned:
            raise DomainError(code="return_empty")
        today = business_date()
        seq = next_number(inv.tenant_id, f"credit_note:{inv.legal_entity_id}:{today.year}")
        cn = CreditNote.objects.create(invoice=inv, number=f"CN-{today.year}-{seq:06d}", reason=reason.strip(),
                                       total=money(total), business_date=today, issued_by=user)
        cn_lines = []
        for ln, amount, restock in planned:
            cn_lines.append(CreditNoteLine.objects.create(credit_note=cn, invoice_line=ln, amount=amount, restock_qty=restock))
            if restock:
                stock.receive(branch_id=inv.branch_id, product_id=ln.product_id, qty=restock, unit_cost=ln.unit_cost,
                              kind="return", source=("pos.credit_note", cn.id), user=user, reason=reason)
            if ln.kind == "package":
                CustomerPackage.objects.filter(sold_on_line=ln).update(voided=True, sessions_left=0)
        ledger.post_credit_note(cn, inv, cn_lines, user)
        commissions.reverse(cn, cn_lines, user)
        if inv.customer_id:
            pts.reverse_for_return(inv, cn)
        if refund is not None and money(refund.amount) > 0:
            state = invoice_state(inv)
            owed_back = money(state["paid"] - (inv.total + inv.tip - state["credited"]))
            amount = money(refund.amount)
            if amount > owed_back:
                raise DomainError(code="refund_exceeds_paid", details={"max": str(max(owed_back, ZERO))})
            if refund.method != "cash" and not refund.reference.strip():
                raise DomainError(code="payment_reference_required")
            session = None
            if refund.method == "cash":
                session = open_session_for(inv.branch_id) or _raise("no_open_session")
            pay = Payment.objects.create(branch_id=inv.branch_id, invoice=inv, credit_note=cn, direction="out",
                                         method=refund.method, amount=amount, reference=refund.reference.strip(),
                                         cash_session=session, business_date=today, received_by=user)
            ledger.post_payment(pay, inv, user)
        audit("pos.credit_note.issued", tenant_id=inv.tenant_id, actor=user, obj=cn, reason=reason,
              data={"invoice": inv.number, "total": str(cn.total), "refund": str(refund.amount) if refund else "0"})
    return cn


def _raise(code):
    raise DomainError(code=code)
