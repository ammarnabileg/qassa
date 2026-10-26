"""People who deliver services. A staff member may or may not have a login (user)."""
from django.db import models

from apps.tenancy.scoping import TenantScopedModel


class StaffMember(TenantScopedModel):
    full_name_ar = models.CharField(max_length=120)
    full_name_en = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=16, blank=True)
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
