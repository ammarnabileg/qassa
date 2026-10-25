"""Base class for tenant-owned rows.

- `objects` is always filtered by the current tenant and refuses to run without a context.
- `unscoped` is the explicit escape hatch (platform jobs, migrations); grep for it in reviews.
- Saving a row for a different tenant than the active context is refused.
- Cross-tenant references are additionally blocked in PostgreSQL by composite foreign keys
  (see `apps.core.db.CompositeTenantFK`).
"""
from django.db import models

from apps.core.errors import TenantContextMissing
from apps.tenancy.context import get_tenant_id


class TenantQuerySet(models.QuerySet):
    pass


class TenantManager(models.Manager.from_queryset(TenantQuerySet)):
    def get_queryset(self):
        tenant_id = get_tenant_id()
        if tenant_id is None:
            raise TenantContextMissing(f"No tenant context while querying {self.model.__name__}")
        return super().get_queryset().filter(tenant_id=tenant_id)


class TenantScopedModel(models.Model):
    tenant = models.ForeignKey("tenancy.Tenant", on_delete=models.PROTECT, related_name="+", editable=False)

    objects = TenantManager()
    unscoped = models.Manager()

    class Meta:
        abstract = True
        base_manager_name = "unscoped"  # related-object access is validated by composite FKs instead

    def save(self, *args, **kwargs):
        ctx = get_tenant_id()
        if self.tenant_id is None:
            if ctx is None:
                raise TenantContextMissing(f"Cannot save {type(self).__name__} without tenant context")
            self.tenant_id = ctx
        elif ctx is not None and ctx != self.tenant_id:
            raise TenantContextMissing(f"{type(self).__name__} belongs to tenant {self.tenant_id}, context is {ctx}")
        super().save(*args, **kwargs)
