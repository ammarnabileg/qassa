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


class MessagingSettings(TenantScopedModel):
    """Which automatic service messages a salon sends from its own WhatsApp number (D-012).
    Only to customers with whatsapp_opt_in; never marketing."""
    booking_confirmation = models.BooleanField(default=True)
    reminder = models.BooleanField(default=True)
    reminder_hours = models.PositiveSmallIntegerField(default=3)
    receipt = models.BooleanField(default=False)
    feedback = models.BooleanField(default=False)          # rating link ~2 hours after a paid visit
    google_review_url = models.URLField(blank=True)        # happy customers (4–5 stars) are invited to review here
    # marketing: only to customers with marketing_opt_in as well as whatsapp_opt_in
    winback = models.BooleanField(default=False)
    winback_days = models.PositiveSmallIntegerField(default=45)
    winback_coupon = models.CharField(max_length=30, blank=True)
    rebook = models.BooleanField(default=False)   # "time for the next cut" on each service's rebook_days (marketing consent)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant"], name="uniq_messaging_settings"),
                       models.CheckConstraint(condition=models.Q(reminder_hours__gte=1) & models.Q(reminder_hours__lte=48),
                                              name="reminder_hours_range"),
                       models.CheckConstraint(condition=models.Q(winback_days__gte=14) & models.Q(winback_days__lte=365),
                                              name="winback_days_range")]


class Feedback(TenantScopedModel):
    """One rating request per invoice; the link carries an unguessable token and works until rated."""
    invoice = models.OneToOneField("pos.Invoice", on_delete=models.PROTECT, related_name="+")
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="+")
    branch = models.ForeignKey("tenancy.Branch", on_delete=models.PROTECT, related_name="+")
    token = models.CharField(max_length=32, unique=True)
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    comment = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    rated_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [models.CheckConstraint(condition=models.Q(rating__isnull=True) | (models.Q(rating__gte=1) & models.Q(rating__lte=5)),
                                              name="feedback_rating_1_5")]
        indexes = [models.Index(fields=["tenant", "rated_at"])]
