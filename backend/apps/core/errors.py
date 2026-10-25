"""Domain errors and a uniform API error shape: {"error": {"code", "message", "details"}}."""
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_handler


class DomainError(Exception):
    """A business-rule violation. `code` is stable and translated by the client (i18n key)."""
    status_code = 422
    code = "domain_error"

    def __init__(self, message="", code=None, details=None):
        super().__init__(message or self.code)
        if code:
            self.code = code
        self.details = details or {}


class ConflictError(DomainError):
    status_code = 409
    code = "conflict"


class TenantContextMissing(RuntimeError):
    """Raised when tenant-scoped data is accessed without an established tenant context."""


def exception_handler(exc, context):
    if isinstance(exc, DomainError):
        return Response({"error": {"code": exc.code, "message": str(exc), "details": exc.details}},
                        status=exc.status_code)
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    if isinstance(exc, DjangoPermissionDenied):
        exc = exceptions.PermissionDenied()
    response = drf_handler(exc, context)
    if response is not None:
        code = getattr(exc, "default_code", "error")
        detail = response.data
        message = detail.get("detail", "") if isinstance(detail, dict) else ""
        response.data = {"error": {"code": code, "message": str(message),
                                   "details": detail if not message else {}}}
    return response
