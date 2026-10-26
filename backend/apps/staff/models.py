"""People who deliver services. A staff member may or may not have a login (user)."""
from django.db import models

from apps.tenancy.scoping import TenantScopedModel


class StaffMember(TenantScopedModel):
    full_name_ar = models.CharField(max_length=120)
    full_name_en = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=16, blank=True)
    # % of the service line's net amount (after discount), earned when the invoice is issued (architecture default)
    commission_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    user = models.ForeignKey("identity.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "id"], name="uniq_staff_tenant_id")]


class StaffBranch(TenantScopedModel):
    staff = models.ForeignKey(StaffMember, on_delete=models.CASCADE, related_name="branch_links")
    branch = models.ForeignKey("tenancy.Branch", on_delete=models.PROTECT, related_name="+")

    class Meta(TenantScopedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["staff", "branch"], name="uniq_staff_branch")]


class StaffSkill(TenantScopedModel):
    """Which services this person may deliver (used by booking in phase 3)."""
    staff = models.ForeignKey(StaffMember, on_delete=models.CASCADE, related_name="skill_links")
    service = models.ForeignKey("catalog.Service", on_delete=models.PROTECT, related_name="+")

    class Meta(TenantScopedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["staff", "service"], name="uniq_staff_skill")]


class CommissionEntry(TenantScopedModel):
    """Commission ledger per staff member. The rule used is copied into the entry (architecture §6.2 ex. 10)."""
    class Kind(models.TextChoices):
        ACCRUAL = "accrual"
        REVERSAL = "reversal"   # after a return
        PAYOUT = "payout"

    staff = models.ForeignKey(StaffMember, on_delete=models.PROTECT, related_name="commissions")
    kind = models.CharField(max_length=8, choices=Kind.choices)
    invoice_line = models.ForeignKey("pos.InvoiceLine", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    base = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=18, decimal_places=3)  # + accrual, − reversal/payout
    reference = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class WorkingHours(TenantScopedModel):
    """Weekly schedule of a staff member at a branch. No rows = follows the branch opening hours."""
    staff = models.ForeignKey(StaffMember, on_delete=models.CASCADE, related_name="hours")
    branch = models.ForeignKey("tenancy.Branch", on_delete=models.CASCADE, related_name="+")
    weekday = models.PositiveSmallIntegerField()  # 0 = Monday … 6 = Sunday (Python weekday)
    starts_at = models.TimeField()
    ends_at = models.TimeField()

    class Meta(TenantScopedModel.Meta):
        constraints = [models.CheckConstraint(condition=models.Q(weekday__lte=6), name="workinghours_weekday")]


class TimeOff(TenantScopedModel):
    staff = models.ForeignKey(StaffMember, on_delete=models.CASCADE, related_name="time_off")
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    reason = models.CharField(max_length=200, blank=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [models.CheckConstraint(condition=models.Q(ends_at__gt=models.F("starts_at")), name="timeoff_range_valid")]
