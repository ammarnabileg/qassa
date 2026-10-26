from django.contrib.postgres.fields import ArrayField
from django.db import models

from apps.tenancy.scoping import TenantScopedModel


class BusinessType(models.TextChoices):
    KIDS = "kids", "Kids"
    MEN = "men", "Men"
    WOMEN = "women", "Women"


class Tenant(models.Model):
    """A subscribing customer account of the platform (not necessarily one legal company)."""
    class Status(models.TextChoices):
        TRIAL = "trial"
        ACTIVE = "active"
        PAST_DUE = "past_due"     # grace period: full access, warnings
        READ_ONLY = "read_only"   # writes blocked per contract, data preserved
        SUSPENDED = "suspended"

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=60, unique=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.TRIAL)
    default_business_type = models.CharField(max_length=8, choices=BusinessType.choices, default=BusinessType.KIDS)
    multi_entity_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    @property
    def writable(self):
        return self.status in {self.Status.TRIAL, self.Status.ACTIVE, self.Status.PAST_DUE}


class LegalEntity(TenantScopedModel):
    """The legal owner of the books (commercial registration). Financial documents always carry it."""
    name_ar = models.CharField(max_length=200)
    name_en = models.CharField(max_length=200, blank=True)
    commercial_registration = models.CharField(max_length=50, blank=True)
    legal_form = models.CharField(max_length=60, blank=True)  # exact list to come from the Qayd guide
    address = models.TextField(blank=True)
    base_currency = models.CharField(max_length=3, default="KWD")
    fiscal_year_start_month = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "id"], name="uniq_legalentity_tenant_id")]

    def __str__(self):
        return self.name_ar


class Branch(TenantScopedModel):
    legal_entity = models.ForeignKey(LegalEntity, on_delete=models.PROTECT, related_name="branches")
    name_ar = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120, blank=True)
    code = models.CharField(max_length=20)
    business_type = models.CharField(max_length=8, choices=BusinessType.choices)
    timezone = models.CharField(max_length=40, default="Asia/Kuwait")
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    # location (nearest-branch suggestion in the customer app) and daily opening hours (online booking slots)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    opens_at = models.TimeField(default="10:00")
    closes_at = models.TimeField(default="22:00")
    online_booking = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "id"], name="uniq_branch_tenant_id"),
            models.UniqueConstraint(fields=["tenant", "code"], name="uniq_branch_code"),
        ]

    def __str__(self):
        return self.name_ar


class Role(TenantScopedModel):
    key = models.CharField(max_length=40)
    name_ar = models.CharField(max_length=80)
    name_en = models.CharField(max_length=80)
    permissions = ArrayField(models.CharField(max_length=60), default=list, blank=True)
    is_system = models.BooleanField(default=False)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "id"], name="uniq_role_tenant_id"),
            models.UniqueConstraint(fields=["tenant", "key"], name="uniq_role_key"),
        ]


class Membership(models.Model):
    """User ↔ tenant link with a role and branch scope. Resolved before a tenant context exists,
    therefore not a TenantScopedModel; always filter by the authenticated user."""
    user = models.ForeignKey("identity.User", on_delete=models.CASCADE, related_name="memberships")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="memberships")
    role = models.ForeignKey(Role, on_delete=models.PROTECT)
    all_branches = models.BooleanField(default=False)
    branches = models.ManyToManyField(Branch, blank=True, through="MembershipBranch")
    is_active = models.BooleanField(default=True)
    discount_limit_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "tenant"], name="uniq_membership"),
            models.UniqueConstraint(fields=["tenant", "id"], name="uniq_membership_tenant_id"),
        ]

    def has_perm(self, code: str) -> bool:
        return self.is_active and code in set(self.role.permissions)

    def branch_ids(self):
        if self.all_branches:
            return None  # None = every branch of the tenant
        return set(self.membershipbranch_set.values_list("branch_id", flat=True))


class MembershipBranch(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE)
    membership = models.ForeignKey(Membership, on_delete=models.CASCADE)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["membership", "branch"], name="uniq_membership_branch")]
