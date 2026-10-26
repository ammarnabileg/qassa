"""Packages (prepaid sessions), loyalty points and coupons.

Packages: the money is a liability when sold and becomes revenue session by session at the value fixed at sale
(architecture §6.2 ex. 5). Points: a marketing discount at redemption (§6.3 option a, pending the accountant)."""
from django.db import models
from django.db.models import Q

from apps.tenancy.scoping import TenantScopedModel

MONEY = dict(max_digits=18, decimal_places=3)


class PackagePlan(TenantScopedModel):
    name_ar = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120, blank=True)
    service = models.ForeignKey("catalog.Service", on_delete=models.PROTECT, related_name="+")
    sessions = models.PositiveSmallIntegerField()
    price = models.DecimalField(**MONEY)
    validity_days = models.PositiveSmallIntegerField(default=180)
    is_active = models.BooleanField(default=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "id"], name="uniq_pkgplan_tenant_id"),
                       models.CheckConstraint(condition=Q(sessions__gte=2) & Q(price__gt=0), name="pkgplan_valid")]


class CustomerPackage(TenantScopedModel):
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="+")
    plan = models.ForeignKey(PackagePlan, on_delete=models.PROTECT, related_name="+")
    service = models.ForeignKey("catalog.Service", on_delete=models.PROTECT, related_name="+")
    sold_on_line = models.OneToOneField("pos.InvoiceLine", on_delete=models.PROTECT, related_name="sold_package")
    sessions_total = models.PositiveSmallIntegerField()
    sessions_left = models.PositiveSmallIntegerField()
    session_value = models.DecimalField(**MONEY)  # fixed at sale; later price changes never change it
    expires_on = models.DateField()
    voided = models.BooleanField(default=False)   # returned before any use
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "id"], name="uniq_custpkg_tenant_id"),
                       models.CheckConstraint(condition=Q(sessions_left__lte=models.F("sessions_total")), name="custpkg_left_le_total")]


class LoyaltySettings(TenantScopedModel):
    enabled = models.BooleanField(default=False)
    points_per_kd = models.PositiveSmallIntegerField(default=1)      # earned per 1.000 KD paid
    point_value = models.DecimalField(**MONEY, default="0.010")      # KD discount per point redeemed
    min_redeem = models.PositiveIntegerField(default=100)

    class Meta(TenantScopedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant"], name="one_loyalty_settings_per_tenant")]


class PointsEntry(TenantScopedModel):
    class Kind(models.TextChoices):
        EARN = "earn"
        REDEEM = "redeem"
        REVERSE = "reverse"   # earned points taken back after a return
        ADJUST = "adjust"

    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, related_name="+")
    kind = models.CharField(max_length=8, choices=Kind.choices)
    points = models.IntegerField()
    invoice = models.ForeignKey("pos.Invoice", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        indexes = [models.Index(fields=["tenant", "customer"])]


class Coupon(TenantScopedModel):
    class Kind(models.TextChoices):
        PERCENT = "percent"
        AMOUNT = "amount"

    code = models.CharField(max_length=30)
    kind = models.CharField(max_length=8, choices=Kind.choices)
    value = models.DecimalField(**MONEY)
    min_total = models.DecimalField(**MONEY, default=0)
    valid_from = models.DateField()
    valid_to = models.DateField()
    max_uses = models.PositiveIntegerField(null=True, blank=True)
    used_count = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "code"], name="uniq_coupon_code"),
            models.CheckConstraint(condition=Q(value__gt=0) & (~Q(kind="percent") | Q(value__lte=100)), name="coupon_value_valid"),
            models.CheckConstraint(condition=Q(max_uses__isnull=True) | Q(used_count__lte=models.F("max_uses")), name="coupon_uses_within_max"),
        ]
