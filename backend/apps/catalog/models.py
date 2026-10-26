"""Services and their prices. A price is a dated row: changing a price closes the current row and opens a new
one, so any document dated in the past still resolves to the price that applied then."""
from django.db import models

from apps.tenancy.models import BusinessType
from apps.tenancy.scoping import TenantScopedModel


class ServiceCategory(TenantScopedModel):
    name_ar = models.CharField(max_length=80)
    name_en = models.CharField(max_length=80, blank=True)
    business_type = models.CharField(max_length=8, choices=BusinessType.choices)
    sort = models.PositiveSmallIntegerField(default=0)

    class Meta(TenantScopedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "id"], name="uniq_svccat_tenant_id")]


class Service(TenantScopedModel):
    category = models.ForeignKey(ServiceCategory, on_delete=models.PROTECT, related_name="services")
    name_ar = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120, blank=True)
    duration_minutes = models.PositiveSmallIntegerField()
    home_visit = models.BooleanField(default=False)  # can be booked as a home visit
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "id"], name="uniq_service_tenant_id"),
            models.CheckConstraint(condition=models.Q(duration_minutes__gte=5, duration_minutes__lte=600),
                                   name="service_duration_range"),
        ]


class ServicePrice(TenantScopedModel):
    """Valid on [valid_from, valid_to). branch NULL = company-wide default; a branch row overrides it."""
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="prices")
    branch = models.ForeignKey("tenancy.Branch", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    price = models.DecimalField(max_digits=18, decimal_places=3)
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "id"], name="uniq_svcprice_tenant_id"),
            models.CheckConstraint(condition=models.Q(price__gte=0), name="svcprice_non_negative"),
            models.CheckConstraint(condition=models.Q(valid_to__isnull=True) | models.Q(valid_to__gt=models.F("valid_from")),
                                   name="svcprice_range_valid"),
        ]
