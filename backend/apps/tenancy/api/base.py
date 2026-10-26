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
        membership = (Membership.objects.select_related("role", "tenant")
                      .filter(user=request.user, tenant_id=int(raw), is_active=True).first())
        if membership is None:
            raise PermissionDenied("No access to this tenant")
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
        set_context(tenant.id, membership)


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
