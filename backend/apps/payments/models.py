"""Online payments through KlickPay (D-017). Each salon is its own KlickPay merchant: own credentials, own dashboard at
KlickPay, own webhook. The platform opens the merchant account on the salon's behalf (KYC documents reviewed here),
then enters the credentials and the commission it takes on that salon's online payments."""
import uuid

from django.db import models

from apps.tenancy.scoping import TenantScopedModel

MONEY = dict(max_digits=18, decimal_places=3)


def kyc_path(instance, filename):
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    return f"kyc/{instance.tenant_id}/{uuid.uuid4().hex}{ext}"


class GatewayAccount(TenantScopedModel):
    class Status(models.TextChoices):
        NOT_STARTED = "not_started"      # nothing uploaded yet
        COLLECTING = "collecting"        # uploading documents
        UNDER_REVIEW = "under_review"    # submitted; platform is reviewing / KlickPay is opening the account
        NEEDS_CHANGES = "needs_changes"  # one or more documents missing or wrong
        ACTIVE = "active"                # credentials entered, payments allowed
        SUSPENDED = "suspended"

    class Env(models.TextChoices):
        STAGING = "staging"
        PRODUCTION = "production"

    status = models.CharField(max_length=14, choices=Status.choices, default=Status.NOT_STARTED)
    environment = models.CharField(max_length=10, choices=Env.choices, default=Env.STAGING)
    client_id = models.CharField(max_length=200, blank=True)
    client_secret_enc = models.TextField(blank=True)       # apps.core.secrets
    webhook_secret_enc = models.TextField(blank=True)
    webhook_token = models.CharField(max_length=40, unique=True, null=True, blank=True)  # path part of our webhook URL
    merchant_token = models.CharField(max_length=200, blank=True)  # KlickPay's id for the merchant, when known
    # what the platform takes from this salon's successful online payments
    commission_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    commission_fixed = models.DecimalField(**MONEY, default=0)      # per successful payment
    review_note = models.CharField(max_length=500, blank=True)
    # booking deposit (customer app), set by the salon
    deposit_mode = models.CharField(max_length=7, choices=[("off", "off"), ("fixed", "fixed"), ("percent", "percent")], default="off")
    deposit_value = models.DecimalField(**MONEY, default=0)          # KWD, or % of the booking price
    deposit_refund_hours = models.PositiveSmallIntegerField(default=24)  # cancel at least this long before: refunded; later or no-show: kept
    deposit_hold_minutes = models.PositiveSmallIntegerField(default=15)  # unpaid this long after booking: the booking is released
    submitted_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant"], name="one_gateway_account_per_tenant"),
                       models.CheckConstraint(condition=models.Q(commission_percent__gte=0) & models.Q(commission_percent__lte=100)
                                              & models.Q(commission_fixed__gte=0), name="gateway_commission_valid")]


class KycDocumentType(models.Model):
    """Platform-wide list of documents KlickPay asks for. Edited by the platform team (not per salon)."""
    code = models.SlugField(max_length=40, unique=True)
    name_ar = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120)
    help_ar = models.CharField(max_length=300, blank=True)
    help_en = models.CharField(max_length=300, blank=True)
    required = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    sort = models.PositiveSmallIntegerField(default=0)


class KycDocument(TenantScopedModel):
    class Status(models.TextChoices):
        UPLOADED = "uploaded"
        ACCEPTED = "accepted"
        REJECTED = "rejected"    # the note says what is wrong; the salon uploads again

    doc_type = models.ForeignKey(KycDocumentType, on_delete=models.PROTECT, related_name="+")
    file = models.FileField(upload_to=kyc_path, max_length=200)
    original_name = models.CharField(max_length=200)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.UPLOADED)
    note = models.CharField(max_length=500, blank=True)
    uploaded_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    is_current = models.BooleanField(default=True)   # a re-upload replaces the previous file for that type

    class Meta(TenantScopedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "doc_type"], condition=models.Q(is_current=True), name="one_current_kyc_doc")]


class OnlinePayment(TenantScopedModel):
    class Status(models.TextChoices):
        CREATED = "created"      # link issued, nothing paid yet
        PAID = "paid"            # confirmed with /payments/status and recorded on the invoice
        DECLINED = "declined"
        FAILED = "failed"
        VOIDED = "voided"
        NEEDS_REVIEW = "review"  # paid at KlickPay but could not be applied (amount mismatch / invoice already settled)

    class Purpose(models.TextChoices):
        INVOICE = "invoice"
        DEPOSIT = "deposit"   # booking deposit from the customer app

    reference = models.CharField(max_length=40, unique=True)   # our transction_reference (KlickPay echoes it back)
    purpose = models.CharField(max_length=8, choices=Purpose.choices, default=Purpose.INVOICE)
    invoice = models.ForeignKey("pos.Invoice", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    appointment = models.ForeignKey("booking.Appointment", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    amount = models.DecimalField(**MONEY)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.CREATED)
    gateway_id = models.CharField(max_length=60, blank=True, db_index=True)   # KlickPay payment_id (QI...)
    payment_url = models.URLField(max_length=1000, blank=True)
    method = models.CharField(max_length=30, blank=True)       # as reported by KlickPay (KNET, CREDIT_DEBIT_CARD, ...)
    detail = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, null=True, blank=True, related_name="+")  # empty: the customer (app)
    created_at = models.DateTimeField(auto_now_add=True)
    settled_at = models.DateTimeField(null=True, blank=True)
    payment = models.OneToOneField("pos.Payment", on_delete=models.PROTECT, null=True, blank=True, related_name="+")

    class Meta(TenantScopedModel.Meta):
        indexes = [models.Index(fields=["tenant", "status", "created_at"])]
        constraints = [models.UniqueConstraint(fields=["tenant", "id"], name="uniq_onlinepayment_tenant_id"),
                       models.CheckConstraint(condition=(models.Q(purpose="invoice") & models.Q(invoice__isnull=False))
                                              | (models.Q(purpose="deposit") & models.Q(appointment__isnull=False)), name="online_payment_target")]


class OnlineRefund(TenantScopedModel):
    """Money sent back through KlickPay. Written as a refund (and posted) only when KlickPay reports success."""
    class Status(models.TextChoices):
        REQUESTED = "requested"
        SUCCESS = "success"
        PENDING_BALANCE = "pending"   # salon's KlickPay wallet too low: KlickPay retries once it is funded
        FAILED = "failed"

    online_payment = models.ForeignKey(OnlinePayment, on_delete=models.PROTECT, related_name="refunds")
    amount = models.DecimalField(**MONEY)
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.REQUESTED)
    refund_reference = models.CharField(max_length=80, blank=True, db_index=True)
    reason = models.CharField(max_length=200)
    detail = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    settled_at = models.DateTimeField(null=True, blank=True)
    payment = models.OneToOneField("pos.Payment", on_delete=models.PROTECT, null=True, blank=True, related_name="+")


class GatewayEvent(TenantScopedModel):
    """Every webhook delivery we accepted (signature verified), kept for audit and to ignore re-deliveries."""
    event_type = models.CharField(max_length=40)
    ref = models.CharField(max_length=80)   # payment / refund reference
    body = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "event_type", "ref"], name="uniq_gateway_event")]
