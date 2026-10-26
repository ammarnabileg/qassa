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
    service_id: int
    qty: int = 1
    discount: Decimal = ZERO
    staff_id: int | None = None


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


def close_session(session: CashSession, counted, user, notes="") -> CashSession:
    with transaction.atomic():
        s = CashSession.objects.select_for_update().get(id=session.id)
        if s.status != CashSession.Status.OPEN:
            raise DomainError(code="session_not_open")
        s.expected_cash = expected_cash(s)
        s.counted_cash = money(counted)
        s.variance = money(s.counted_cash - s.expected_cash)
        s.status, s.closed_by, s.closed_at, s.notes = CashSession.Status.CLOSED, user, timezone.now(), notes
        s.variance_status = CashSession.Variance.NONE if s.variance == 0 else CashSession.Variance.PENDING
        s.save()
        audit("cash.session.closed", tenant_id=s.tenant_id, actor=user, obj=s,
              data={"expected": str(s.expected_cash), "counted": str(s.counted_cash), "variance": str(s.variance)})
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
    return {"paid": paid, "credited": money(credited), "balance": money(inv.total - credited - paid),
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
def checkout(data: CheckoutIn, *, user, membership) -> Invoice:
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

        services = {s.id: s for s in Service.objects.select_related("category").filter(id__in=[x.service_id for x in data.lines])}
        staff_ids = {x.staff_id for x in data.lines if x.staff_id}
        staff = {s.id: s for s in StaffMember.objects.filter(id__in=staff_ids)}
        planned, subtotal, discount_total, max_pct = [], ZERO, ZERO, ZERO
        for i, ln in enumerate(data.lines):
            svc = services.get(ln.service_id)
            if svc is None or not svc.is_active:
                raise DomainError(code="service_unknown", details={"position": i})
            if svc.category.business_type != branch.business_type:
                raise DomainError(code="service_not_for_branch", details={"position": i})
            if ln.staff_id and ln.staff_id not in staff:
                raise DomainError(code="staff_unknown", details={"position": i})
            price = price_on(svc, branch.id, today)
            if price is None:
                raise DomainError(code="service_has_no_price", details={"position": i, "service": svc.id})
            if ln.qty < 1 or ln.qty > 50:
                raise DomainError(code="qty_invalid", details={"position": i})
            gross = money(price * ln.qty)
            disc = money(ln.discount or 0)
            if disc < 0 or disc > gross:
                raise DomainError(code="discount_invalid", details={"position": i})
            if gross > 0:
                max_pct = max(max_pct, disc * 100 / gross)
            planned.append((svc, ln, price, disc, money(gross - disc)))
            subtotal += gross
            discount_total += disc
        total = money(subtotal - discount_total)

        if data.expected_total is not None and money(data.expected_total) != total:
            raise ConflictError(code="price_changed", message="Prices changed; review the cart",
                                details={"total": str(total)})
        approved_by = None
        if max_pct > membership.discount_limit_percent:
            if not membership.has_perm("pos.discount.override"):
                raise DomainError(code="discount_over_limit", details={"limit": str(membership.discount_limit_percent)})
            approved_by = user

        paying = money(sum((money(p.amount) for p in data.payments), ZERO))
        if paying > total:
            raise DomainError(code="overpayment", details={"total": str(total), "paying": str(paying)})
        is_credit = paying < total
        if is_credit:
            if not membership.has_perm("pos.credit_sale"):
                raise DomainError(code="credit_sale_forbidden")
            if customer is None:
                raise DomainError(code="credit_sale_needs_customer")

        seq = next_number(branch.tenant_id, f"invoice:{branch.legal_entity_id}:{today.year}")
        inv = Invoice.objects.create(
            legal_entity_id=branch.legal_entity_id, branch=branch, number=f"INV-{today.year}-{seq:06d}",
            customer=customer, beneficiary=beneficiary, appointment=appointment, cash_session=open_session_for(branch.id),
            subtotal=money(subtotal), discount_total=money(discount_total), total=total, is_credit=is_credit,
            business_date=today, issued_by=user, discount_approved_by=approved_by)
        for svc, ln, price, disc, line_total in planned:
            InvoiceLine.objects.create(invoice=inv, service=svc, staff_id=ln.staff_id, name_ar=svc.name_ar, name_en=svc.name_en,
                                       qty=ln.qty, unit_price=price, discount=disc, line_total=line_total)
        ledger.post_invoice(inv, user)
        _take_payments(inv, data.payments, user, branch.id)
        if appointment is not None:
            Appointment.objects.filter(id=appointment.id).update(status=Appointment.Status.INVOICED, updated_at=timezone.now())
        audit("pos.invoice.issued", tenant_id=inv.tenant_id, actor=user, obj=inv,
              data={"number": inv.number, "total": str(total), "paid": str(paying), "credit": is_credit})
    return inv


def collect(inv: Invoice, payments: list[PaymentIn], *, user) -> list[Payment]:
    with transaction.atomic():
        inv = Invoice.objects.select_for_update().get(id=inv.id)
        state = invoice_state(inv)
        paying = money(sum((money(p.amount) for p in payments), ZERO))
        if paying <= 0:
            raise DomainError(code="payment_empty")
        if paying > state["balance"]:
            raise DomainError(code="overpayment", details={"balance": str(state["balance"])})
        created = _take_payments(inv, payments, user, inv.branch_id)
        audit("pos.invoice.collected", tenant_id=inv.tenant_id, actor=user, obj=inv, data={"amount": str(paying)})
    return created


def credit_note(inv: Invoice, *, lines: list[tuple[int, Decimal]], reason: str, refund: PaymentIn | None, user) -> CreditNote:
    """Return part or all of an invoice. Optional refund of money already paid (cash needs an open drawer)."""
    if not reason.strip():
        raise DomainError(code="reason_required")
    with transaction.atomic():
        inv = Invoice.objects.select_for_update().get(id=inv.id)
        inv_lines = {ln.id: ln for ln in inv.lines.all()}
        total = ZERO
        planned = []
        for line_id, amount in lines:
            ln = inv_lines.get(line_id) or _raise("invoice_line_unknown")
            amount = money(amount)
            already = ln.credit_lines.aggregate(s=Sum("amount"))["s"] or ZERO
            if amount <= 0 or amount > ln.line_total - already:
                raise DomainError(code="return_exceeds_line", details={"line": line_id, "max": str(ln.line_total - already)})
            planned.append((ln, amount))
            total += amount
        if not planned:
            raise DomainError(code="return_empty")
        today = business_date()
        seq = next_number(inv.tenant_id, f"credit_note:{inv.legal_entity_id}:{today.year}")
        cn = CreditNote.objects.create(invoice=inv, number=f"CN-{today.year}-{seq:06d}", reason=reason.strip(),
                                       total=money(total), business_date=today, issued_by=user)
        for ln, amount in planned:
            CreditNoteLine.objects.create(credit_note=cn, invoice_line=ln, amount=amount)
        ledger.post_credit_note(cn, inv, user)
        if refund is not None and money(refund.amount) > 0:
            state = invoice_state(inv)
            # money owed back = what was paid beyond what the customer still owes after the return
            owed_back = money(state["paid"] - (inv.total - state["credited"]))
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
