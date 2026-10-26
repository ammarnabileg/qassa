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
