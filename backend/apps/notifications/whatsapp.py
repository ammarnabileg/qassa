"""WhatsApp sending behind one interface (D-002). The unofficial provider plugs in here without touching callers.

QASSA_WHATSAPP_ADAPTER:
  disabled  — nothing can be sent; callers get a clear error (default, and the only safe value until a
              provider is connected)
  console   — development/staging only: the message is written to the log, never delivered
  evolution — unofficial gateway (Evolution API compatible); needs QASSA_WHATSAPP_URL / _TOKEN / _INSTANCE
"""
import json
import logging
import urllib.request

from django.conf import settings

from apps.core.errors import DomainError

log = logging.getLogger("qassa.whatsapp")


class ChannelUnavailable(DomainError):
    status_code = 503
    code = "whatsapp_unavailable"


def adapter() -> str:
    return settings.QASSA.get("WHATSAPP_ADAPTER", "disabled")


def send_text(phone: str, text: str) -> str:
    """Returns the adapter name used. Raises ChannelUnavailable when nothing can deliver the message."""
    name = adapter()
    if name == "console":
        if settings.ENVIRONMENT == "production":
            raise ChannelUnavailable(message="console adapter is not allowed in production")
        log.warning("WHATSAPP (console, not delivered) to %s: %s", phone, text)
        return name
    if name == "evolution":
        cfg = settings.QASSA
        req = urllib.request.Request(
            f"{cfg['WHATSAPP_URL'].rstrip('/')}/message/sendText/{cfg['WHATSAPP_INSTANCE']}",
            data=json.dumps({"number": phone, "text": text}).encode(), method="POST",
            headers={"Content-Type": "application/json", "apikey": cfg["WHATSAPP_TOKEN"]})
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                if res.status >= 300:
                    raise ChannelUnavailable(message=f"gateway status {res.status}")
        except OSError as e:
            log.error("WhatsApp gateway failed: %s", e)
            raise ChannelUnavailable(message="WhatsApp gateway unreachable")
        return name
    raise ChannelUnavailable(message="No WhatsApp channel is configured")
