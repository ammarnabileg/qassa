"""WhatsApp sending behind one interface (D-002). Each company sends from its own number (an Evolution API
instance); the platform holds only the gateway URL and its global key.

QASSA_WHATSAPP_ADAPTER:
  disabled  — nothing can be sent; callers get a clear error (default until a gateway is configured)
  console   — development/staging only: the message is written to the log, never delivered
  evolution — Evolution API v2 gateway (QASSA_WHATSAPP_URL + QASSA_WHATSAPP_TOKEN)
"""
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.utils import timezone

from apps.core.errors import DomainError
from apps.notifications.models import WhatsAppChannel, WhatsAppMessage
from apps.tenancy.context import get_tenant_id

log = logging.getLogger("qassa.whatsapp")


class ChannelUnavailable(DomainError):
    status_code = 503
    code = "whatsapp_unavailable"


class GatewayError(DomainError):
    status_code = 502
    code = "whatsapp_gateway_error"


def adapter() -> str:
    return settings.QASSA.get("WHATSAPP_ADAPTER", "disabled")


# ---------- Evolution API v2 ----------
def _call(method: str, path: str, body: dict | None = None) -> dict:
    """One gateway request. Kept small so tests can replace it with a fake gateway."""
    cfg = settings.QASSA
    req = urllib.request.Request(f"{cfg['WHATSAPP_URL'].rstrip('/')}{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "apikey": cfg["WHATSAPP_TOKEN"]})
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            raw = res.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read()[:300].decode(errors="replace")
        log.error("Evolution %s %s → %s %s", method, path, e.code, detail)
        raise GatewayError(message=f"gateway {e.code}", details={"status": e.code})
    except OSError as e:
        log.error("Evolution unreachable: %s", e)
        raise GatewayError(message="WhatsApp gateway unreachable")


def _require_gateway():
    if adapter() != "evolution":
        raise ChannelUnavailable(message="No WhatsApp gateway is configured on the platform")


def channel_for(tenant) -> WhatsAppChannel:
    ch = WhatsAppChannel.objects.filter(tenant_id=tenant.id).first()
    if ch is None:
        ch = WhatsAppChannel.objects.create(instance_name=f"qassa-{tenant.slug}"[:80])
    return ch


def connect(tenant) -> dict:
    """Create the company's instance if needed and return a QR (base64 PNG) to scan from the salon's phone."""
    _require_gateway()
    ch = channel_for(tenant)
    if ch.state == WhatsAppChannel.State.NEW:
        _call("POST", "/instance/create", {"instanceName": ch.instance_name, "qrcode": True, "integration": "WHATSAPP-BAILEYS"})
    data = _call("GET", f"/instance/connect/{ch.instance_name}")
    qr = data.get("base64") or (data.get("qrcode") or {}).get("base64")
    refresh(ch)
    if ch.state != WhatsAppChannel.State.OPEN:
        ch.state = WhatsAppChannel.State.CONNECTING
        ch.save(update_fields=["state"])
    return {"state": ch.state, "qr": qr, "pairing_code": data.get("pairingCode")}


def refresh(ch: WhatsAppChannel) -> WhatsAppChannel:
    """Ask the gateway for the live state (open / connecting / close)."""
    if adapter() != "evolution" or ch.state == WhatsAppChannel.State.NEW:
        return ch
    state = ((_call("GET", f"/instance/connectionState/{ch.instance_name}").get("instance") or {}).get("state") or "close")
    if state not in WhatsAppChannel.State.values:
        state = WhatsAppChannel.State.CLOSE
    if state == WhatsAppChannel.State.OPEN and ch.state != WhatsAppChannel.State.OPEN:
        ch.connected_at = timezone.now()
        try:
            for inst in _call("GET", f"/instance/fetchInstances?instanceName={ch.instance_name}") or []:
                jid = (inst.get("ownerJid") or (inst.get("instance") or {}).get("owner") or "")
                if jid:
                    ch.phone = jid.split("@")[0]
        except DomainError:
            pass
    ch.state, ch.checked_at = state, timezone.now()
    ch.save(update_fields=["state", "phone", "checked_at", "connected_at"])
    return ch


def disconnect(tenant) -> WhatsAppChannel:
    _require_gateway()
    ch = channel_for(tenant)
    if ch.state != WhatsAppChannel.State.NEW:
        try:
            _call("DELETE", f"/instance/logout/{ch.instance_name}")
        except GatewayError:
            pass  # already logged out on the gateway
    ch.state, ch.phone = WhatsAppChannel.State.CLOSE, ""
    ch.save(update_fields=["state", "phone"])
    return ch


def send_text(phone: str, text: str, *, kind: str, preview: str | None = None) -> str:
    """Send from the current company's number. Logs every attempt; raises ChannelUnavailable when it cannot
    deliver — never pretends a message went out."""
    tenant_id = get_tenant_id()
    name = adapter()

    def log_row(status, error=""):
        if tenant_id:
            WhatsAppMessage.objects.create(to=phone, kind=kind, status=status, error=error[:200],
                                           preview="" if preview is None else preview[:160])

    if name == "console":
        if settings.ENVIRONMENT == "production":
            raise ChannelUnavailable(message="console adapter is not allowed in production")
        log.warning("WHATSAPP (console, not delivered) to %s [%s]", phone, kind)
        log_row(WhatsAppMessage.Status.SENT, "console: not delivered")
        return name
    if name != "evolution":
        log_row(WhatsAppMessage.Status.FAILED, "no gateway configured")
        raise ChannelUnavailable(message="No WhatsApp channel is configured")
    ch = WhatsAppChannel.objects.filter(tenant_id=tenant_id).first()
    if ch is None or ch.state != WhatsAppChannel.State.OPEN:
        log_row(WhatsAppMessage.Status.FAILED, "company number not connected")
        raise ChannelUnavailable(message="This salon's WhatsApp number is not connected")
    try:
        _call("POST", f"/message/sendText/{ch.instance_name}", {"number": phone, "text": text})
    except GatewayError as e:
        log_row(WhatsAppMessage.Status.FAILED, str(e))
        # the number may have been logged out on the phone: re-check so the admin page shows the truth
        try:
            refresh(ch)
        except DomainError:
            pass
        raise ChannelUnavailable(message="Sending failed; the salon's WhatsApp may be disconnected")
    log_row(WhatsAppMessage.Status.SENT)
    return name
