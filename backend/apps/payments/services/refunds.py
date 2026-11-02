"""Refunds through KlickPay. A refund is posted (Payment out / deposit release) only when KlickPay reports success,
either in the API answer or later by a signed refund webhook (pending wallet balance)."""
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.audit.services.log import record as audit
from apps.core.errors import DomainError
from apps.core.money import money
from apps.payments.models import GatewayAccount, OnlinePayment, OnlineRefund
from apps.payments.services import klickpay


def refundable(op) -> "money":
    done = op.refunds.exclude(status=OnlineRefund.Status.FAILED).aggregate(s=Sum("amount"))["s"] or 0
    return money(op.amount - done)


def request(op, amount, *, reason, user=None) -> OnlineRefund:
    amount = money(amount)
    if op.status != OnlinePayment.Status.PAID:
        raise DomainError(code="refund_not_paid")
    if amount <= 0 or amount > refundable(op):
        raise DomainError(code="refund_too_much", details={"refundable": str(refundable(op))})
    acc = GatewayAccount.objects.get()
    r = OnlineRefund.objects.create(online_payment=op, amount=amount, reason=reason[:200], created_by=user)
    code, d = klickpay.refund(acc, op.gateway_id, amount, full=amount == op.amount and not op.refunds.exclude(id=r.id).exists())
    r.refund_reference = str(d.get("refund_reference") or "")[:80]
    if code == "REFUND_SUCCESS":
        r.save(update_fields=["refund_reference"])
        apply_success(r)
    elif code == "INSUFFICIENT_BALANCE":
        r.status, r.detail = OnlineRefund.Status.PENDING_BALANCE, f"wallet short by {d.get('shortfall_amount', '?')} KWD"
        r.save(update_fields=["status", "detail", "refund_reference"])
    else:
        gw = d.get("gateway") or {}
        r.status, r.detail, r.settled_at = OnlineRefund.Status.FAILED, str(gw.get("message") or d.get("message") or code)[:300], timezone.now()
        r.save(update_fields=["status", "detail", "refund_reference", "settled_at"])
    audit("payments.refund_requested", tenant_id=op.tenant_id, actor=user, obj=r, data={"amount": str(amount), "status": r.status})
    r.refresh_from_db()
    return r


def apply_success(r: OnlineRefund):
    """Post the money going back. Invoice: a refund payment (Dr AR / Cr gateway). Deposit: release the liability."""
    from apps.accounting.services.posting import Line, post_entry
    from apps.booking.models import Appointment
    from apps.pos.models import Payment
    from apps.pos.services import ledger
    with transaction.atomic():
        r = OnlineRefund.objects.select_for_update().select_related("online_payment").get(id=r.id)
        if r.status == OnlineRefund.Status.SUCCESS:
            return r
        op = r.online_payment
        today = timezone.localdate()
        if op.purpose == OnlinePayment.Purpose.INVOICE:
            inv = op.invoice
            pay = Payment.objects.create(branch_id=inv.branch_id, invoice=inv, direction="out", method=Payment.Method.ONLINE,
                                         amount=r.amount, reference=(r.refund_reference or op.gateway_id)[:60], business_date=today,
                                         received_by=r.created_by or op.created_by or inv.issued_by)
            ledger.post_payment(pay, inv, r.created_by)
            r.payment = pay
        else:
            appt = Appointment.objects.select_related("branch").get(id=op.appointment_id)
            post_entry(legal_entity_id=appt.branch.legal_entity_id, entry_date=today, kind="auto", branch_id=appt.branch_id,
                       source_type="payments.refund", source_id=str(r.id), event_type="deposit.refunded", memo=f"Deposit refund {op.reference}",
                       lines=[Line("CUSTOMER_DEPOSITS", debit=r.amount, branch_id=appt.branch_id),
                              *ledger.refund_lines(appt.branch.legal_entity_id, "GATEWAY_CLEARING", r.amount, today, appt.branch_id,
                                                   f"deposit {op.reference}")])
            Appointment.objects.filter(id=appt.id, deposit_status__in=["paid", "refunding"]).update(deposit_status="refunded")
        r.status, r.settled_at = OnlineRefund.Status.SUCCESS, timezone.now()
        r.save(update_fields=["status", "settled_at", "payment"])
    audit("payments.refunded", tenant_id=op.tenant_id, obj=r, data={"amount": str(r.amount)})
    return r


def on_webhook(body: dict, event: str):
    ref = str(body.get("refund_reference") or "")
    r = OnlineRefund.objects.filter(refund_reference=ref).first() if ref else None
    if r is None or r.status == OnlineRefund.Status.SUCCESS:
        return
    if event == "refund.success":
        apply_success(r)
    elif event == "refund.failed":
        r.status, r.detail, r.settled_at = OnlineRefund.Status.FAILED, str(body.get("gateway_message") or "")[:300], timezone.now()
        r.save(update_fields=["status", "detail", "settled_at"])
    elif event == "refund.pending_balance":
        r.status = OnlineRefund.Status.PENDING_BALANCE
        r.save(update_fields=["status"])
