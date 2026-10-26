"""One WhatsApp number per company (D-002), and a log of every message attempt (content of login codes is never
stored)."""
from django.db import models

from apps.tenancy.scoping import TenantScopedModel


class WhatsAppChannel(TenantScopedModel):
    class State(models.TextChoices):
        NEW = "new"                # instance not created yet
        CONNECTING = "connecting"  # waiting for the QR to be scanned
        OPEN = "open"              # connected, can send
        CLOSE = "close"            # disconnected / logged out

    instance_name = models.CharField(max_length=80, unique=True)
    state = models.CharField(max_length=12, choices=State.choices, default=State.NEW)
    phone = models.CharField(max_length=20, blank=True)  # the connected number, when known
    checked_at = models.DateTimeField(null=True, blank=True)
    connected_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant"], name="one_whatsapp_channel_per_tenant")]


class WhatsAppMessage(TenantScopedModel):
    class Status(models.TextChoices):
        SENT = "sent"
        FAILED = "failed"

    to = models.CharField(max_length=20)
    kind = models.CharField(max_length=30)       # otp, booking.confirmed, receipt …
    preview = models.CharField(max_length=160, blank=True)  # empty for login codes
    status = models.CharField(max_length=8, choices=Status.choices)
    error = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
