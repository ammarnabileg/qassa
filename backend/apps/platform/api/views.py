from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.services.infra import idempotent
from apps.tenancy.api.base import IsPlatformStaff
from apps.platform.models import Plan, TenantDomain
from apps.tenancy.models import Branch, BusinessType, Tenant
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
    plan_code = serializers.SlugField(default="basic")


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


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ["id", "code", "name_ar", "name_en", "monthly_price", "max_branches", "max_staff", "custom_domain",
                  "is_active", "sort", "highlight", "features_ar", "features_en"]


class TenantOut(serializers.ModelSerializer):
    plan = serializers.CharField(source="subscription.plan.code", default=None)
    hosts = serializers.SerializerMethodField()
    owner_phone = serializers.SerializerMethodField()
    branches = serializers.IntegerField(source="branch_count")

    class Meta:
        model = Tenant
        fields = ["id", "name", "slug", "status", "default_business_type", "plan", "branches", "hosts", "owner_phone", "created_at"]

    def get_owner_phone(self, obj) -> str:
        m = obj.memberships.filter(role__key="owner").select_related("user").first()
        return m.user.phone if m else ""

    def get_hosts(self, obj) -> list[str]:
        return [d.host for d in obj.domains.all() if d.is_active]


class TenantsListView(APIView):
    permission_classes = [IsPlatformStaff]

    @extend_schema(responses=TenantOut(many=True))
    def get(self, request):
        from django.db.models import Count
        qs = list(Tenant.objects.select_related("subscription__plan").prefetch_related("domains").order_by("-id"))
        # branch rows are tenant-scoped; count them with the explicit escape hatch
        counts = dict(Branch.unscoped.values_list("tenant_id").annotate(n=Count("id")))
        for t in qs:
            t.branch_count = counts.get(t.id, 0)
        return Response(TenantOut(qs, many=True).data)


class TenantAdminIn(serializers.Serializer):
    status = serializers.ChoiceField(choices=Tenant.Status.choices, required=False)
    owner_phone = serializers.CharField(required=False, allow_blank=True, max_length=20)  # receives login codes on WhatsApp
    plan_code = serializers.SlugField(required=False)
    reason = serializers.CharField(max_length=300)


class TenantAdminView(APIView):
    """Platform staff change a tenant's status or plan. Always audited with a reason."""
    permission_classes = [IsPlatformStaff]

    @extend_schema(request=TenantAdminIn, responses=TenantOut)
    def patch(self, request, pk):
        from django.db import transaction
        from rest_framework.generics import get_object_or_404

        from apps.audit.services.log import record as audit
        from apps.core.errors import DomainError
        tenant = get_object_or_404(Tenant.objects.select_related("subscription__plan"), pk=pk)
        s = TenantAdminIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        with transaction.atomic():
            if "plan_code" in v:
                plan = Plan.objects.filter(code=v["plan_code"], is_active=True).first()
                if plan is None:
                    raise DomainError(code="plan_unknown")
                active = Branch.unscoped.filter(tenant_id=tenant.id, is_active=True).count()
                if active > plan.max_branches:
                    raise DomainError(code="plan_limit_branches", details={"limit": plan.max_branches, "plan": plan.code})
                tenant.subscription.plan = plan
                tenant.subscription.save(update_fields=["plan", "updated_at"])
            if "status" in v:
                tenant.status = v["status"]
                tenant.save(update_fields=["status"])
            if "owner_phone" in v:
                from apps.customers.services.phone import normalize_phone
                from apps.identity.models import User
                phone = normalize_phone(v["owner_phone"]) if v["owner_phone"].strip() else ""
                User.objects.filter(memberships__tenant=tenant, memberships__role__key="owner").update(phone=phone)
            audit("platform.tenant.changed", tenant_id=tenant.id, actor=request.user, obj=tenant, reason=v["reason"],
                  data={k: v[k] for k in ("status", "plan_code", "owner_phone") if k in v})
        tenant.branch_count = Branch.unscoped.filter(tenant_id=tenant.id).count()
        return Response(TenantOut(tenant).data)


class PlansView(APIView):
    """Public (pricing page) read; platform staff edit."""
    def get_permissions(self):
        from rest_framework.permissions import AllowAny
        return [AllowAny()] if self.request.method == "GET" else [IsPlatformStaff()]

    @extend_schema(responses=PlanSerializer(many=True))
    def get(self, request):
        return Response(PlanSerializer(Plan.objects.filter(is_active=True).order_by("sort"), many=True).data)


class PlanDetailView(APIView):
    permission_classes = [IsPlatformStaff]

    @extend_schema(request=PlanSerializer, responses=PlanSerializer)
    def patch(self, request, pk):
        from rest_framework.generics import get_object_or_404

        from apps.audit.services.log import record as audit
        plan = get_object_or_404(Plan.objects.all(), pk=pk)
        s = PlanSerializer(plan, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        if s.validated_data.get("highlight"):
            Plan.objects.exclude(id=plan.id).update(highlight=False)   # one "most popular" plan
        s.save()
        audit("platform.plan.changed", actor=request.user, obj=plan, data={k: str(v) for k, v in s.validated_data.items()})
        return Response(s.data)


class TenantsView(TenantCreateView, TenantsListView):
    """GET: list tenants · POST: onboard a tenant (platform staff only)."""


class DomainSerializer(serializers.ModelSerializer):
    class Meta:
        model = TenantDomain
        fields = ["id", "host", "kind", "is_active", "created_at", "activated_at"]
        read_only_fields = ["kind", "is_active", "created_at", "activated_at"]
        extra_kwargs = {"host": {"validators": []}}  # uniqueness reported as domain_taken by the view

    def validate_host(self, value):
        import re
        host = value.strip().lower().rstrip(".")
        if not re.fullmatch(r"(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}", host):
            raise serializers.ValidationError("invalid host")
        return host


class TenantDomainsView(APIView):
    """Platform staff list/add a company's custom domains. Adding does not activate: DNS must point to us first."""
    permission_classes = [IsPlatformStaff]

    @extend_schema(responses=DomainSerializer(many=True))
    def get(self, request, pk):
        return Response(DomainSerializer(TenantDomain.objects.filter(tenant_id=pk).order_by("id"), many=True).data)

    @extend_schema(request=DomainSerializer, responses={201: DomainSerializer})
    def post(self, request, pk):
        from django.conf import settings
        from django.db import IntegrityError
        from rest_framework.generics import get_object_or_404

        from apps.audit.services.log import record as audit
        from apps.core.errors import DomainError
        tenant = get_object_or_404(Tenant.objects.select_related("subscription__plan"), pk=pk)
        if not tenant.subscription.plan.custom_domain:
            raise DomainError(code="plan_no_custom_domain", details={"plan": tenant.subscription.plan.code})
        s = DomainSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        host = s.validated_data["host"]
        base = settings.TENANT_BASE_DOMAIN
        if host == base or host.endswith("." + base) or host in settings.PLATFORM_HOSTS:
            raise DomainError(code="domain_reserved")
        from django.db import transaction
        try:
            with transaction.atomic():
                d = TenantDomain.objects.create(tenant=tenant, host=host, kind=TenantDomain.Kind.CUSTOM)
        except IntegrityError:
            raise DomainError(code="domain_taken")
        audit("platform.domain.added", tenant_id=tenant.id, actor=request.user, obj=d, data={"host": host})
        return Response(DomainSerializer(d).data, status=status.HTTP_201_CREATED)


class DomainActivationIn(serializers.Serializer):
    is_active = serializers.BooleanField()
    reason = serializers.CharField(max_length=300)


class DomainDetailView(APIView):
    permission_classes = [IsPlatformStaff]

    @extend_schema(request=DomainActivationIn, responses=DomainSerializer)
    def patch(self, request, pk):
        from django.utils import timezone
        from rest_framework.generics import get_object_or_404

        from apps.audit.services.log import record as audit
        from apps.core.errors import DomainError
        from apps.platform.middleware import forget_host
        d = get_object_or_404(TenantDomain.objects.select_related("tenant__subscription__plan"), pk=pk)
        s = DomainActivationIn(data=request.data)
        s.is_valid(raise_exception=True)
        on = s.validated_data["is_active"]
        if on and d.kind == TenantDomain.Kind.CUSTOM and not d.tenant.subscription.plan.custom_domain:
            raise DomainError(code="plan_no_custom_domain")
        d.is_active = on
        d.activated_at = timezone.now() if on else None
        d.save(update_fields=["is_active", "activated_at"])
        forget_host(d.host)
        audit("platform.domain.activated" if on else "platform.domain.deactivated", tenant_id=d.tenant_id,
              actor=request.user, obj=d, reason=s.validated_data["reason"], data={"host": d.host})
        return Response(DomainSerializer(d).data)
