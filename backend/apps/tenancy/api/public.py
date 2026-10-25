"""Unauthenticated, read-only salon profile for the customer app's salon picker (D-001).

Exposes only what a salon shows on its storefront: name, business type, active branches.
Suspended tenants are hidden (404) — no hint that the slug exists.
"""
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core.errors import DomainError
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Branch, Tenant


class SalonNotFound(DomainError):
    status_code = 404
    code = "salon_not_found"


class PublicBranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ["id", "name_ar", "name_en", "business_type", "address", "phone"]


class PublicSalonView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public"

    @extend_schema(responses=inline_serializer("PublicSalon", {
        "slug": serializers.CharField(), "name": serializers.CharField(),
        "business_type": serializers.CharField(), "branches": PublicBranchSerializer(many=True)}))
    def get(self, request, slug):
        tenant = Tenant.objects.filter(slug=slug).exclude(status=Tenant.Status.SUSPENDED).first()
        if tenant is None:
            raise SalonNotFound()
        with tenant_context(tenant.id):
            branches = list(Branch.objects.filter(is_active=True).order_by("code"))
        return Response({"slug": tenant.slug, "name": tenant.name,
                         "business_type": tenant.default_business_type,
                         "branches": PublicBranchSerializer(branches, many=True).data})
