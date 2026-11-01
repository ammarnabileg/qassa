"""Payment links for invoices, and turning a KlickPay confirmation into a real receipt on the invoice.

Nothing is recorded as paid from a redirect or a webhook alone: both only trigger a /payments/status check, and the
receipt is written only when KlickPay reports the link paid for exactly the amount we asked (D-017)."""
import hashlib
import hmac
import logging
import secrets
import time
from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.services.log import record as audit
from apps.core.errors import DomainError
from apps.core.money import money
from apps.core.services.infra import enqueue, outbox_handler
from apps.payments.models import GatewayAccount, GatewayEvent, OnlinePayment
from apps.payments.services import klickpay
from apps.tenancy.context import tenant_context

log = logging.getLogger("qassa.klickpay")
SIGNATURE_WINDOW = 300   # seconds, as KlickPay recommends
PAID = {"paid"}
FAILED = {"declined": OnlinePayment.Status.DECLINED, "failed": OnlinePayment.Status.FAILED, "voided": OnlinePayment.Status.VOIDED}


def active_account() -> GatewayAccount:
    acc = GatewayAccount.objects.first()
    if acc is None or acc.status != GatewayAccount.Status.ACTIVE:
        raise DomainError(code="gateway_not_active")
    return acc


def create_invoice_link(inv, user) -> OnlinePayment:
    from apps.pos.services.sales import invoice_state
    acc = active_account()
    balance = invoice_state(inv)["balance"]
    if balance <= 0:
        raise DomainError(code="invoice_settled")
    if inv.customer is None:
        raise DomainError(code="invoice_no_customer")
    open_link = OnlinePayment.objects.filter(invoice=inv, status=OnlinePayment.Status.CREATED, amount=balance).order_by("-id").first()
    if open_link and (timezone.now() - open_link.created_at).total_seconds() < 24 * 3600:
        return open_link   # the same unpaid link again, not a second charge
    ref = f"Q{inv.tenant_id}-{secrets.token_hex(6).upper()}"
    base = settings.QASSA["PUBLIC_ADMIN_URL"].rstrip("/")
    c = inv.customer
    email = c.email or f"no-reply@{settings.TENANT_BASE_DOMAIN}"   # KlickPay requires one; confirm this with them (D-017)
    items = [{"item_code": str(ln.id), "item_name": ln.name_ar[:100] or inv.number, "item_quantity": int(ln.qty),
              "item_unit_price": float(ln.unit_price), "item_total_price": float(ln.line_total), "item_currency": "KWD"}
             for ln in inv.lines.all()] if balance == inv.total else [
        {"item_code": inv.number, "item_name": inv.number, "item_quantity": 1, "item_unit_price": float(balance),
         "item_total_price": float(balance), "item_currency": "KWD"}]
    d = klickpay.create_link(acc, reference=ref, amount=balance, client_name=c.full_name[:100], client_email=email,
                             client_phone=c.phone[-8:] if c.phone.startswith("965") else c.phone,
                             success=f"{base}/pay/{ref}", error=f"{base}/pay/{ref}", items=items)
    op = OnlinePayment.objects.create(reference=ref, invoice=inv, amount=balance, gateway_id=str(d["payment_id"]),
                                      payment_url=d["payment_url"], created_by=user)
    audit("payments.link_created", tenant_id=inv.tenant_id, actor=user, obj=op, data={"invoice": inv.number, "amount": str(balance)})
    return op


def request_check(op):
    enqueue("klickpay.confirm", {"online_payment_id": op.id}, tenant_id=op.tenant_id)


def confirm(op) -> OnlinePayment:
    """Ask KlickPay, then apply. Safe to call any number of times."""
    if op.status != OnlinePayment.Status.CREATED:
        return op
    acc = GatewayAccount.objects.get()
    data = klickpay.payment_status(acc, op.gateway_id)
    status = str(data.get("status", "")).lower()
    op.method = str(data.get("payment_method", ""))[:30]
    if status in PAID and str(data.get("result", "")).upper() in {"CAPTURED", "SUCCESS", ""}:
        return _apply_paid(op, money(Decimal(str(data.get("amount") or "0"))), op.method)
    if status in FAILED:
        op.status, op.detail, op.settled_at = FAILED[status], str(data.get("result", ""))[:300], timezone.now()
        op.save(update_fields=["status", "detail", "method", "settled_at"])
    return op


def _apply_paid(op, amount, method="") -> OnlinePayment:
    from apps.loyalty.services import points as pts
    from apps.pos.models import Invoice, Payment
    from apps.pos.services import ledger
    from apps.pos.services.sales import invoice_state
    with transaction.atomic():
        op = OnlinePayment.objects.select_for_update().get(id=op.id)
        if op.status != OnlinePayment.Status.CREATED:
            return op
        inv = Invoice.objects.select_for_update().get(id=op.invoice_id)
        balance = invoice_state(inv)["balance"]
        op.settled_at, op.method = timezone.now(), method
        if amount != op.amount or amount > balance:
            # never invent a receipt: someone must look (refund or record by hand)
            op.status = OnlinePayment.Status.NEEDS_REVIEW
            op.detail = f"paid {amount} at KlickPay; asked {op.amount}; invoice balance {balance}"
            op.save(update_fields=["status", "detail", "method", "settled_at"])
            audit("payments.needs_review", tenant_id=op.tenant_id, obj=op, data={"detail": op.detail})
            return op
        pay = Payment.objects.create(branch_id=inv.branch_id, invoice=inv, direction="in", method=Payment.Method.ONLINE,
                                     amount=amount, reference=op.gateway_id[:60], business_date=timezone.localdate(),
                                     received_by=op.created_by)
        ledger.post_payment(pay, inv, op.created_by)
        op.status, op.payment = OnlinePayment.Status.PAID, pay
        op.save(update_fields=["status", "payment", "method", "settled_at"])
        if inv.customer_id and invoice_state(inv)["balance"] == 0:
            pts.earn(inv.customer, inv)
        audit("payments.paid", tenant_id=op.tenant_id, obj=op, data={"invoice": inv.number, "amount": str(amount), "method": op.method})
    return op


@outbox_handler("klickpay.confirm")
def handle_confirm(ev):
    with tenant_context(ev.tenant_id):
        op = OnlinePayment.objects.filter(id=ev.payload["online_payment_id"]).first()
        if op is not None:
            confirm(op)   # a gateway error raises: the outbox retries with backoff


# ---------- webhook ----------
def verify(raw: bytes, signature: str, timestamp: str, secret: str, now=None) -> bool:
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature.strip().lower()):
        return False
    try:
        return abs((now or time.time()) - int(timestamp)) <= SIGNATURE_WINDOW
    except (TypeError, ValueError):
        return False


def accept_webhook(acc, body: dict, header_event: str):
    """Record the delivery once and schedule the status check for the payment it names."""
    event = str(body.get("event_type") or header_event)[:40]
    ids = {str(body.get(k)) for k in ("invoice_id", "payment_id", "invoice_token") if body.get(k)}
    ref = str(body.get("refund_reference") or body.get("payment_id") or body.get("invoice_id") or "")[:80]
    with tenant_context(acc.tenant_id):
        result = "ok"
        try:
            with transaction.atomic():
                GatewayEvent.objects.create(event_type=event, ref=ref, body=body)
        except IntegrityError:
            result = "duplicate"   # not stored twice, but a still-open link is checked again (cheap and idempotent)
        if acc.merchant_token and body.get("merchant_token") and body["merchant_token"] != acc.merchant_token:
            log.warning("klickpay webhook for tenant %s carries another merchant token", acc.tenant_id)
            return "foreign"
        if event.startswith("payment."):
            for op in OnlinePayment.objects.filter(gateway_id__in=ids, status=OnlinePayment.Status.CREATED):
                request_check(op)
        return result
