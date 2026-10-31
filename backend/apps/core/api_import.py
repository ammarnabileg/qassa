"""Spreadsheet import for moving a salon over from its old system. Every upload is a preview unless commit=true."""
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response

from apps.audit.services.log import record as audit
from apps.core.errors import DomainError
from apps.tenancy.api.base import TenantAPIView


class ImportView(TenantAPIView):
    parser_classes = [MultiPartParser]
    required_permissions = {"POST": "customers.manage"}   # services also need catalog rights, checked below

    @extend_schema(request={"multipart/form-data": OpenApiTypes.OBJECT}, responses=dict)
    def post(self, request, kind):
        f = request.FILES.get("file")
        if f is None:
            raise DomainError(code="import_bad_file")
        if f.size > 5 * 1024 * 1024:
            raise DomainError(code="import_too_big")
        commit = str(request.data.get("commit", "")).lower() in {"1", "true"}
        if kind == "customers":
            from apps.customers.services.importer import run
            out = run(f, commit=commit)
        elif kind == "services":
            if not (request.membership.has_perm("catalog.manage") and request.membership.has_perm("catalog.price.change")):
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied()
            from apps.catalog.services.importer import run
            out = run(f, commit=commit, user=request.user, default_type=request.membership.tenant.default_business_type)
        else:
            raise DomainError(code="import_bad_file")
        if commit:
            audit(f"import.{kind}", tenant_id=request.tenant_id, actor=request.user, data={k: v for k, v in out.items() if k != "errors"})
        return Response({**out, "committed": commit})
