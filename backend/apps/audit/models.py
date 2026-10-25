from django.db import models


class AuditLog(models.Model):
    """Append-only. UPDATE/DELETE are blocked by a database trigger (see migration 0002).
    `hash` chains every row of a tenant to the previous one so tampering is detectable."""
    tenant = models.ForeignKey("tenancy.Tenant", on_delete=models.PROTECT, null=True)
    actor = models.ForeignKey("identity.User", on_delete=models.PROTECT, null=True)
    acting_as_support = models.BooleanField(default=False)
    action = models.CharField(max_length=80)
    object_type = models.CharField(max_length=80, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    data = models.JSONField(default=dict)
    reason = models.TextField(blank=True)
    ip = models.GenericIPAddressField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    prev_hash = models.CharField(max_length=64)
    hash = models.CharField(max_length=64)

    class Meta:
        indexes = [models.Index(fields=["tenant", "id"]), models.Index(fields=["object_type", "object_id"])]
