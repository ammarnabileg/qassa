"""Base classes for tenant-scoped API views.

The client chooses a tenant with the `X-Tenant` header (tenant id). The server only accepts it if the
authenticated user has an active membership there; otherwise 403. The tenant id is never read from the body.
"""
from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied
from rest_framework.views import APIView

from apps.tenancy.context import set_context
from apps.tenancy.models import Membership

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class TenantAPIView(APIView):
    required_permissions: dict[str, str] = {}  # e.g. {"GET": "accounting.view", "POST": "accounting.journal.post"}

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)  # authentication, throttling
        raw = request.headers.get("X-Tenant", "")
        if not raw.isdigit():
            raise PermissionDenied("X-Tenant header is required")
        if getattr(request, "domain_tenant_id", None) and int(raw) != request.domain_tenant_id:
            raise PermissionDenied("This address belongs to another salon")
        membership = (Membership.objects.select_related("role", "tenant")
                      .filter(user=request.user, tenant_id=int(raw), is_active=True).first())
        support = False
        if membership is None:
            membership = support_membership(request.user, int(raw))
            support = membership is not None
        if membership is None:
            raise PermissionDenied("No access to this tenant")
        if support and request.method in WRITE_METHODS:
            raise PermissionDenied("Support access is read-only")
        tenant = membership.tenant
        if tenant.status == tenant.Status.SUSPENDED:
            raise PermissionDenied("Tenant is suspended")
        if request.method in WRITE_METHODS and not tenant.writable:
            raise PermissionDenied("Tenant is read-only")
        perm = self.required_permissions.get(request.method)
        if perm and not membership.has_perm(perm):
            raise PermissionDenied(f"Missing permission: {perm}")
        request.tenant_id = tenant.id
        request.membership = membership
        request.support_access = support
        set_context(tenant.id, membership)


def support_membership(user, tenant_id):
    """An unsaved, read-only membership (every *view* permission, all branches) for platform staff with an
    active support access to this tenant. Writes are refused before any view code runs."""
    from apps.platform.api.console import active_support
    from apps.tenancy.models import Role
    from apps.tenancy.permissions_catalog import ALL
    acc = active_support(user, tenant_id).first()
    if acc is None:
        return None
    role = Role(tenant_id=tenant_id, key="support", name_ar="دعم فني (قراءة فقط)", name_en="Support (read-only)",
                permissions=sorted(p for p in ALL if ".view" in p))
    return Membership(user=user, tenant=acc.tenant, role=role, all_branches=True, is_active=True)


class IsPlatformStaff(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_platform_staff)


def branch_for(request, branch_id):
    """The branch, if it belongs to the tenant and the member may act on it; otherwise a clear error."""
    from apps.core.errors import DomainError
    from apps.tenancy.models import Branch
    try:
        branch = Branch.objects.select_related("legal_entity").filter(id=int(branch_id), is_active=True).first()
    except (TypeError, ValueError):
        branch = None
    if branch is None:
        raise DomainError(code="branch_unknown")
    allowed = request.membership.branch_ids()
    if allowed is not None and branch.id not in allowed:
        raise PermissionDenied("No access to this branch")
    return branch
