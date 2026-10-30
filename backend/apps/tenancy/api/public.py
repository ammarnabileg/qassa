"""Unauthenticated, read-only salon storefront data for the customer PWA/app.

On a company host (its subdomain or custom domain) the salon is the one that owns the host — a slug in the
URL cannot switch to another company. On the platform host (the store-published picker app, D-001) the slug
selects the salon. Suspended companies are hidden (404) with no hint that they exist.
"""
from django.http import JsonResponse
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from apps.core.throttling import AtomicScopedRateThrottle as ScopedRateThrottle
from rest_framework.views import APIView

from apps.core.errors import DomainError
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Branch, Tenant

BRAND = {"kids": "#0CD273", "men": "#C9A24B", "women": "#EC6F9A"}


class SalonNotFound(DomainError):
    status_code = 404
    code = "salon_not_found"


class PublicBranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ["id", "name_ar", "name_en", "business_type", "address", "phone"]


def resolve(request, slug=None) -> Tenant:
    qs = Tenant.objects.exclude(status=Tenant.Status.SUSPENDED)
    if request.domain_tenant_id:
        tenant = qs.filter(id=request.domain_tenant_id).first()
    else:
        tenant = qs.filter(slug=slug).first() if slug else None
    if tenant is None:
        raise SalonNotFound()
    return tenant


class PublicView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public"


class PublicSalonView(PublicView):
    @extend_schema(responses=inline_serializer("PublicSalon", {
        "slug": serializers.CharField(), "name": serializers.CharField(), "locked": serializers.BooleanField(),
        "business_type": serializers.CharField(), "branches": PublicBranchSerializer(many=True)}))
    def get(self, request, slug=None):
        tenant = resolve(request, slug)
        with tenant_context(tenant.id):
            branches = list(Branch.objects.filter(is_active=True).order_by("code"))
        return Response({"slug": tenant.slug, "name": tenant.name, "business_type": tenant.default_business_type,
                         # locked = served on the company's own host; the app must not offer "change salon"
                         "locked": bool(request.domain_tenant_id),
                         "branches": PublicBranchSerializer(branches, many=True).data})


class PublicManifestView(PublicView):
    """Web app manifest per company host, so "Add to home screen" installs it under the salon's name."""
    @extend_schema(exclude=True)
    def get(self, request):
        if not request.domain_tenant_id:
            name, color = "قصّة", BRAND["kids"]
        else:
            t = resolve(request)
            name, color = t.name, BRAND.get(t.default_business_type, BRAND["kids"])
        icons = [{"src": f"icons/Icon-{s}.png", "sizes": f"{s}x{s}", "type": "image/png"} for s in (192, 512)]
        icons += [{"src": f"icons/Icon-maskable-{s}.png", "sizes": f"{s}x{s}", "type": "image/png", "purpose": "maskable"}
                  for s in (192, 512)]
        return JsonResponse({"name": name, "short_name": name[:12], "start_url": "/", "scope": "/", "display": "standalone",
                             "lang": "ar", "dir": "rtl", "background_color": "#F6F8F6", "theme_color": color, "icons": icons},
                            content_type="application/manifest+json", json_dumps_params={"ensure_ascii": False})
