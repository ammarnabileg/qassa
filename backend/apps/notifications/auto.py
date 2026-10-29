"""Automatic service messages over the salon's WhatsApp (D-012): booking confirmation / change, reminder, receipt.

Events are written to the outbox in the same transaction as the booking or invoice, so a message is only
attempted for something that really happened. A salon without a connected number simply gets a 'failed'
row in its message log — nothing is retried for hours and nothing is reported as sent."""
import logging
from datetime import timedelta

from django.utils import timezone

from apps.core.models import OutboxEvent
from apps.core.services.infra import enqueue, outbox_handler
from apps.tenancy.context import tenant_context

log = logging.getLogger("qassa.whatsapp")
TZ_FMT = "%Y-%m-%d %H:%M"

TEXT = {
    "booking.confirmed": {
        "ar": "أهلاً {name} 👋\nحجزك في {salon} — {branch} اتأكد.\n🗓 {when}\n✂️ {services}\nلو حابب تلغي أو تغيّر، كلّمنا قبلها بساعة.",
        "en": "Hi {name} 👋\nYour booking at {salon} — {branch} is confirmed.\n🗓 {when}\n✂️ {services}\nTo cancel or change, contact us at least 1 hour before."},
    "booking.changed": {
        "ar": "أهلاً {name}، ميعادك في {salon} — {branch} اتغيّر.\n🗓 الميعاد الجديد: {when}\n✂️ {services}",
        "en": "Hi {name}, your appointment at {salon} — {branch} has changed.\n🗓 New time: {when}\n✂️ {services}"},
    "booking.reminder": {
        "ar": "تذكير من {salon} ⏰\nميعادك النهارده {when} في فرع {branch}.\n✂️ {services}\nمستنيينك!",
        "en": "Reminder from {salon} ⏰\nYour appointment is at {when} at {branch}.\n✂️ {services}\nSee you soon!"},
    "receipt": {
        "ar": "شكراً لزيارتك {salon} 🌟\nفاتورة {number}\nالإجمالي: {total} د.ك\n{points}",
        "en": "Thank you for visiting {salon} 🌟\nInvoice {number}\nTotal: {total} KWD\n{points}"},
}


def settings_for(tenant_id):
    from apps.notifications.models import MessagingSettings
    obj, _ = MessagingSettings.objects.get_or_create(tenant_id=tenant_id)
    return obj


def _when(dt, lang):
    local = timezone.localtime(dt)
    return local.strftime(TZ_FMT) if lang == "en" else local.strftime("%d/%m %H:%M")


# ---------- producers (called inside the booking / invoice transaction) ----------
def booking_created(appt):
    if appt.customer_id and appt.status == "booked":
        enqueue("wa.booking", {"appointment_id": appt.id, "kind": "booking.confirmed", "starts_at": appt.starts_at.isoformat()},
                tenant_id=appt.tenant_id, dedupe_key=f"appt:{appt.id}:confirmed")


def booking_rescheduled(appt):
    if appt.customer_id:
        enqueue("wa.booking", {"appointment_id": appt.id, "kind": "booking.changed", "starts_at": appt.starts_at.isoformat()},
                tenant_id=appt.tenant_id, dedupe_key=f"appt:{appt.id}:changed:{appt.starts_at.isoformat()}")


def invoice_issued(inv):
    if inv.customer_id:
        enqueue("wa.receipt", {"invoice_id": inv.id}, tenant_id=inv.tenant_id, dedupe_key=f"inv:{inv.id}:receipt")


def queue_reminders(now=None) -> int:
    """Run every 15 minutes: queue a reminder for bookings starting within each salon's reminder window."""
    from apps.booking.models import Appointment
    from apps.notifications.models import MessagingSettings
    now = now or timezone.now()
    n = 0
    off = set(MessagingSettings.unscoped.filter(reminder=False).values_list("tenant_id", flat=True))
    hours = dict(MessagingSettings.unscoped.values_list("tenant_id", "reminder_hours"))
    for a in Appointment.unscoped.filter(status="booked", customer__isnull=False, starts_at__gt=now,
                                         starts_at__lte=now + timedelta(hours=48)).only("id", "tenant_id", "starts_at"):
        if a.tenant_id in off or a.starts_at > now + timedelta(hours=hours.get(a.tenant_id, 3)):
            continue
        key = f"appt:{a.id}:reminder:{a.starts_at.isoformat()}"
        if OutboxEvent.objects.filter(topic="wa.booking", dedupe_key=key).exists():
            continue
        enqueue("wa.booking", {"appointment_id": a.id, "kind": "booking.reminder", "starts_at": a.starts_at.isoformat()},
                tenant_id=a.tenant_id, dedupe_key=key)
        n += 1
    return n


# ---------- handlers ----------
def _send(tenant_id, customer, kind, text, preview):
    from apps.notifications import whatsapp
    try:
        whatsapp.send_text(customer.phone, text, kind=kind, preview=preview)
    except whatsapp.ChannelUnavailable as e:
        log.info("auto message %s for tenant %s not sent: %s", kind, tenant_id, e)   # logged as failed; not retried


@outbox_handler("wa.booking")
def handle_booking(ev):
    from apps.booking.models import Appointment
    with tenant_context(ev.tenant_id):
        kind = ev.payload["kind"]
        s = settings_for(ev.tenant_id)
        if (kind == "booking.reminder" and not s.reminder) or (kind != "booking.reminder" and not s.booking_confirmation):
            return
        a = (Appointment.objects.select_related("customer", "beneficiary", "branch", "tenant")
             .prefetch_related("items__service").filter(id=ev.payload["appointment_id"]).first())
        if a is None or a.customer is None or not a.customer.whatsapp_opt_in or a.status != "booked":
            return
        if a.starts_at.isoformat() != ev.payload["starts_at"] or a.starts_at <= timezone.now():
            return                                    # moved again or already past: this message is stale
        lang = a.customer.preferred_language
        services = "، ".join(i.service.name_ar if lang == "ar" else (i.service.name_en or i.service.name_ar) for i in a.items.all())
        name = (a.beneficiary.full_name if a.beneficiary_id else a.customer.full_name).split(" ")[0]
        text = TEXT[kind][lang].format(name=name, salon=a.tenant.name, branch=a.branch.name_en if lang == "en" and a.branch.name_en else a.branch.name_ar,
                                       when=_when(a.starts_at, lang), services=services)
        _send(ev.tenant_id, a.customer, kind, text, f"{kind} {_when(a.starts_at, 'en')}")


@outbox_handler("wa.receipt")
def handle_receipt(ev):
    from apps.loyalty.services import points
    from apps.pos.models import Invoice
    with tenant_context(ev.tenant_id):
        if not settings_for(ev.tenant_id).receipt:
            return
        inv = Invoice.objects.select_related("customer", "tenant").filter(id=ev.payload["invoice_id"]).first()
        if inv is None or inv.customer is None or not inv.customer.whatsapp_opt_in:
            return
        lang = inv.customer.preferred_language
        bal = points.balance(inv.customer)
        pts = "" if not bal else (f"رصيد نقاطك: {bal}" if lang == "ar" else f"Your points: {bal}")
        text = TEXT["receipt"][lang].format(salon=inv.tenant.name, number=inv.number, total=inv.total, points=pts).strip()
        _send(ev.tenant_id, inv.customer, "receipt", text, f"receipt {inv.number}")
