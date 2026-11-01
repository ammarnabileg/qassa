"""Booking deposits from the customer app (D-017). The money is a liability (CUSTOMER_DEPOSITS) until the visit is
invoiced (applied as a payment), refunded (cancelled in time, or by the salon), or kept (late cancel / no-show)."""
import secrets

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.services.log import record as audit
from apps.core.errors import DomainError
from apps.core.money import money
from apps.core.services.infra import enqueue, outbox_handler
from apps.payments.models import GatewayAccount, OnlinePayment
from apps.payments.services import klickpay
from apps.tenancy.context import tenant_context


def required(price) -> "money":
    """The deposit for a booking of this price under the salon's policy (0 = none)."""
    acc = GatewayAccount.objects.first()
    if acc is None or acc.status != GatewayAccount.Status.ACTIVE or acc.deposit_mode == "off" or not price:
        return money(0)
    value = acc.deposit_value if acc.deposit_mode == "fixed" else price * acc.deposit_value / 100
    return money(min(value, price))


def start(appt, amount) -> OnlinePayment:
    """Called right after the app booking is created: link + a timer that releases the slot if it stays unpaid."""
    from apps.booking.models import Appointment
    acc = GatewayAccount.objects.get()
    c = appt.customer
    ref = f"D{appt.tenant_id}-{secrets.token_hex(6).upper()}"
    base = settings.QASSA["PUBLIC_ADMIN_URL"].rstrip("/")
    d = klickpay.create_link(acc, reference=ref, amount=amount, client_name=c.full_name[:100],
                             client_email=c.email or f"no-reply@{settings.TENANT_BASE_DOMAIN}",
                             client_phone=c.phone[-8:] if c.phone.startswith("965") else c.phone,
                             success=f"{base}/pay/{ref}", error=f"{base}/pay/{ref}",
                             items=[{"item_code": f"BOOKING-{appt.id}", "item_name": "عربون حجز", "item_quantity": 1,
                                     "item_unit_price": float(amount), "item_total_price": float(amount), "item_currency": "KWD"}])
    op = OnlinePayment.objects.create(reference=ref, purpose=OnlinePayment.Purpose.DEPOSIT, appointment=appt, amount=amount,
                                      gateway_id=str(d["payment_id"]), payment_url=d["payment_url"])
    Appointment.objects.filter(id=appt.id).update(deposit_amount=amount, deposit_status="pending")
    enqueue("deposit.expire", {"online_payment_id": op.id}, tenant_id=appt.tenant_id, delay_seconds=acc.deposit_hold_minutes * 60)
    return op


def apply_paid(op, amount, method):
    """Deposit confirmed by KlickPay: Dr GATEWAY_CLEARING / Cr CUSTOMER_DEPOSITS. A booking already released is refunded."""
    from apps.accounting.services.posting import Line, post_entry
    from apps.booking.models import Appointment
    with transaction.atomic():
        op = OnlinePayment.objects.select_for_update().get(id=op.id)
        if op.status != OnlinePayment.Status.CREATED:
            return op
        appt = Appointment.objects.select_for_update().select_related("branch").get(id=op.appointment_id)
        op.settled_at, op.method = timezone.now(), method
        if amount != op.amount:
            op.status, op.detail = OnlinePayment.Status.NEEDS_REVIEW, f"paid {amount}; asked {op.amount}"
            op.save(update_fields=["status", "detail", "method", "settled_at"])
            return op
        post_entry(legal_entity_id=appt.branch.legal_entity_id, entry_date=timezone.localdate(), kind="auto", branch_id=appt.branch_id,
                   source_type="payments.deposit", source_id=str(op.id), event_type="deposit.received", memo=f"Deposit {op.reference}",
                   lines=[Line("GATEWAY_CLEARING", debit=amount, branch_id=appt.branch_id),
                          Line("CUSTOMER_DEPOSITS", credit=amount, branch_id=appt.branch_id)])
        op.status = OnlinePayment.Status.PAID
        op.save(update_fields=["status", "method", "settled_at"])
        late = appt.status == Appointment.Status.CANCELLED
        Appointment.objects.filter(id=appt.id).update(deposit_status="refunding" if late else "paid")
        audit("payments.deposit_paid", tenant_id=op.tenant_id, obj=op, data={"appointment": appt.id, "amount": str(amount)})
    if late:   # paid after the slot was released: give it back
        from apps.payments.services import refunds
        refunds.request(op, op.amount, reason="booking released before the deposit arrived")
    return op


def paid_deposit(appt) -> "OnlinePayment | None":
    if appt is None or appt.deposit_status != "paid":
        return None
    return OnlinePayment.objects.filter(appointment=appt, purpose=OnlinePayment.Purpose.DEPOSIT, status=OnlinePayment.Status.PAID).first()


def on_status(appt, new, *, by_customer: bool):
    """Booking left the active states: refund in time (or when the salon cancels), keep it when late or a no-show."""
    from apps.accounting.services.posting import Line, post_entry
    from apps.booking.models import Appointment
    op = paid_deposit(appt)
    if op is None or new not in {Appointment.Status.CANCELLED, Appointment.Status.NO_SHOW}:
        return
    acc = GatewayAccount.objects.get()
    in_time = (appt.starts_at - timezone.now()).total_seconds() >= acc.deposit_refund_hours * 3600
    if new == Appointment.Status.CANCELLED and (not by_customer or in_time):
        Appointment.objects.filter(id=appt.id).update(deposit_status="refunding")
        _refund_after_commit(op.id, appt.tenant_id)   # outbox row in this same transaction: runs only if it commits
        return
    post_entry(legal_entity_id=appt.branch.legal_entity_id, entry_date=timezone.localdate(), kind="auto", branch_id=appt.branch_id,
               source_type="payments.deposit", source_id=f"{op.id}:kept", event_type="deposit.forfeited", memo=f"Deposit kept {op.reference}",
               lines=[Line("CUSTOMER_DEPOSITS", debit=op.amount, branch_id=appt.branch_id),
                      Line("OTHER_INCOME", credit=op.amount, branch_id=appt.branch_id)])
    Appointment.objects.filter(id=appt.id).update(deposit_status="forfeited")


def _refund_after_commit(op_id, tenant_id):
    enqueue("deposit.refund", {"online_payment_id": op_id}, tenant_id=tenant_id)


@outbox_handler("deposit.refund")
def handle_refund(ev):
    from apps.payments.services import refunds
    with tenant_context(ev.tenant_id):
        op = OnlinePayment.objects.get(id=ev.payload["online_payment_id"])
        if refunds.refundable(op) > 0:
            refunds.request(op, refunds.refundable(op), reason="booking cancelled in time")


@outbox_handler("deposit.expire")
def handle_expire(ev):
    """Unpaid after the hold: ask KlickPay once more; still unpaid -> release the slot."""
    from apps.booking.models import Appointment
    from apps.booking.services.appointments import set_status
    from apps.payments.services import links
    with tenant_context(ev.tenant_id):
        op = OnlinePayment.objects.filter(id=ev.payload["online_payment_id"]).first()
        if op is None or op.status != OnlinePayment.Status.CREATED:
            return
        try:
            op = links.confirm(op)
        except DomainError:
            pass
        if op.status == OnlinePayment.Status.CREATED:
            OnlinePayment.objects.filter(id=op.id).update(status=OnlinePayment.Status.VOIDED, detail="expired unpaid", settled_at=timezone.now())
            appt = Appointment.objects.get(id=op.appointment_id)
            Appointment.objects.filter(id=appt.id).update(deposit_status="expired")
            if appt.status == Appointment.Status.BOOKED:
                set_status(appt, Appointment.Status.CANCELLED, reason="deposit not paid in time")


def refund_rest(op_id, tenant_id, amount):
    enqueue("deposit.refund_rest", {"online_payment_id": op_id, "amount": str(amount)}, tenant_id=tenant_id)


@outbox_handler("deposit.refund_rest")
def handle_refund_rest(ev):
    """The visit cost less than the deposit: the remainder goes back. Only that part leaves CUSTOMER_DEPOSITS."""
    from decimal import Decimal
    from apps.payments.services import refunds
    with tenant_context(ev.tenant_id):
        op = OnlinePayment.objects.get(id=ev.payload["online_payment_id"])
        amount = money(Decimal(ev.payload["amount"]))
        if refunds.refundable(op) >= amount > 0 and not op.refunds.filter(reason="deposit above the bill").exists():
            refunds.request(op, amount, reason="deposit above the bill")
