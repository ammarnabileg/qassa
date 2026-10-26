"""Host validation: platform hosts from settings, company hosts from TenantDomain (active only).

Sets request.domain_tenant_id when the request came in on a company host, so public endpoints can resolve
the salon from the address bar. Unknown hosts get 400, as Django's ALLOWED_HOSTS would."""
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponseBadRequest
from django.utils.http import is_same_domain

CACHE_SECONDS = 60


def host_of(request) -> str:
    raw = request.META.get("HTTP_HOST") or request.META.get("SERVER_NAME", "")  # same fallback as Django
    return raw.rsplit(":", 1)[0].lower().rstrip(".")


def tenant_for_host(host: str):
    key = f"tenant-host:{host}"
    hit = cache.get(key)
    if hit is None:
        from apps.platform.models import TenantDomain
        row = TenantDomain.objects.filter(host=host, is_active=True).values_list("tenant_id", flat=True).first()
        hit = row or 0
        cache.set(key, hit, CACHE_SECONDS)
    return hit or None


def forget_host(host: str):
    cache.delete(f"tenant-host:{host}")


class HostMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = host_of(request)
        request.domain_tenant_id = None
        if not any(is_same_domain(host, pattern) for pattern in settings.PLATFORM_HOSTS):
            request.domain_tenant_id = tenant_for_host(host)
            if request.domain_tenant_id is None:
                return HttpResponseBadRequest("Unknown host")
        return self.get_response(request)
