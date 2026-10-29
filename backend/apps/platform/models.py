"""Platform subscription plans. Billing collection waits for the payment provider (deferred, see DECISIONS)."""
from django.db import models


class Plan(models.Model):
    code = models.SlugField(max_length=30, unique=True)
    name_ar = models.CharField(max_length=60)
    name_en = models.CharField(max_length=60)
    monthly_price = models.DecimalField(max_digits=18, decimal_places=3)
    max_branches = models.PositiveSmallIntegerField()
    max_staff = models.PositiveSmallIntegerField()
    custom_domain = models.BooleanField(default=False)  # may serve its PWA on its own domain
    is_active = models.BooleanField(default=True)
    sort = models.PositiveSmallIntegerField(default=0)
    highlight = models.BooleanField(default=False)            # "most popular" on the pricing page
    features_ar = models.JSONField(default=list, blank=True)   # bullet lines on the pricing page
    features_en = models.JSONField(default=list, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(monthly_price__gte=0), name="plan_price_non_negative")]


class Subscription(models.Model):
    tenant = models.OneToOneField("tenancy.Tenant", on_delete=models.CASCADE, related_name="subscription")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    started_on = models.DateField()
    current_period_end = models.DateField()
    updated_at = models.DateTimeField(auto_now=True)


class TenantDomain(models.Model):
    """Host names that serve a company's customer PWA. A subdomain of the platform base domain is created at
    onboarding; a custom domain needs a plan that allows it and is activated by platform staff after DNS points
    to us (we terminate TLS and route). Platform-level table: resolved before any tenant context exists."""
    class Kind(models.TextChoices):
        SUBDOMAIN = "subdomain"
        CUSTOM = "custom"

    tenant = models.ForeignKey("tenancy.Tenant", on_delete=models.CASCADE, related_name="domains")
    host = models.CharField(max_length=253, unique=True)  # lower-case, no port
    kind = models.CharField(max_length=10, choices=Kind.choices)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    activated_at = models.DateTimeField(null=True, blank=True)


class PlatformInvoice(models.Model):
    """Subscription invoice from the platform to a salon company. One per tenant and period; paid manually
    (bank / KNET outside the system) until an online payment provider is chosen (D-010)."""
    class Status(models.TextChoices):
        ISSUED = "issued"
        PAID = "paid"
        VOID = "void"

    tenant = models.ForeignKey("tenancy.Tenant", on_delete=models.PROTECT, related_name="platform_invoices")
    number = models.CharField(max_length=30, unique=True)
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT)
    period_start = models.DateField()
    period_end = models.DateField()
    amount = models.DecimalField(max_digits=18, decimal_places=3)
    due_on = models.DateField()
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ISSUED)
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_method = models.CharField(max_length=20, blank=True)
    paid_reference = models.CharField(max_length=80, blank=True)
    recorded_by = models.ForeignKey("identity.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "period_start"], name="uniq_platform_invoice_period"),
                       models.CheckConstraint(condition=models.Q(amount__gte=0), name="platform_invoice_amount_gte_0")]
        ordering = ["-period_start", "-id"]


class SupportTicket(models.Model):
    class Status(models.TextChoices):
        OPEN = "open"          # waiting for the platform
        PENDING = "pending"    # waiting for the salon
        CLOSED = "closed"

    class Priority(models.TextChoices):
        LOW = "low"
        MID = "mid"
        HIGH = "high"

    tenant = models.ForeignKey("tenancy.Tenant", on_delete=models.CASCADE, related_name="tickets")
    subject = models.CharField(max_length=200)
    priority = models.CharField(max_length=4, choices=Priority.choices, default=Priority.MID)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.OPEN)
    created_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]


class TicketMessage(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    from_platform = models.BooleanField(default=False)
    body = models.TextField(max_length=5000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]


class Lead(models.Model):
    """'Contact us' requests from the public site; platform staff open the account (D-010)."""
    class Status(models.TextChoices):
        NEW = "new"
        CONTACTED = "contacted"
        CONVERTED = "converted"
        REJECTED = "rejected"

    salon_name = models.CharField(max_length=120)
    contact_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    business_type = models.CharField(max_length=8, default="kids")
    branches = models.PositiveSmallIntegerField(default=1)
    plan_code = models.CharField(max_length=30, blank=True)
    city = models.CharField(max_length=60, blank=True)
    message = models.TextField(max_length=2000, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.NEW)
    notes = models.TextField(blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]


class SupportAccess(models.Model):
    """Time-limited, read-only access of a platform staff member to one tenant, with a written reason."""
    staff = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    tenant = models.ForeignKey("tenancy.Tenant", on_delete=models.CASCADE, related_name="+")
    reason = models.CharField(max_length=300)
    started_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
