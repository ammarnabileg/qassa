from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.services.infra import idempotent
from apps.tenancy.api.base import IsPlatformStaff
from apps.tenancy.models import BusinessType
from apps.platform.services.onboarding import BranchSpec, OnboardingSpec, onboard_tenant


class BranchIn(serializers.Serializer):
    name_ar = serializers.CharField(max_length=120)
    name_en = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    code = serializers.SlugField(max_length=20)
    business_type = serializers.ChoiceField(choices=BusinessType.choices)


class TenantIn(serializers.Serializer):
    tenant_name = serializers.CharField(max_length=200)
    owner_email = serializers.EmailField()
    owner_name = serializers.CharField(max_length=150)
    legal_name_ar = serializers.CharField(max_length=200)
    legal_name_en = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    commercial_registration = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    business_type = serializers.ChoiceField(choices=BusinessType.choices)
    branches = BranchIn(many=True, required=False, default=list)


class TenantCreateView(APIView):
    permission_classes = [IsPlatformStaff]

    @extend_schema(request=TenantIn, responses={201: inline_serializer("TenantCreated", {"id": serializers.IntegerField(), "slug": serializers.CharField(), "status": serializers.CharField()})})
    @idempotent
    def post(self, request):
        s = TenantIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        tenant = onboard_tenant(OnboardingSpec(**{**v, "branches": [BranchSpec(**b) for b in v["branches"]]}),
                                actor=request.user)
        return Response({"id": tenant.id, "slug": tenant.slug, "status": tenant.status}, status=status.HTTP_201_CREATED)
