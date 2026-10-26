from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.response import Response

from apps.tenancy.api.base import TenantAPIView
from apps.tenancy.models import Branch, LegalEntity


class LegalEntitySerializer(serializers.ModelSerializer):
    class Meta:
        model = LegalEntity
        fields = ["id", "name_ar", "name_en", "commercial_registration", "legal_form", "base_currency",
                  "fiscal_year_start_month"]


class BranchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ["id", "legal_entity", "name_ar", "name_en", "code", "business_type", "timezone", "address", "phone",
                  "is_active"]


class OrgView(TenantAPIView):
    """Legal entities and the branches this membership may see."""
    required_permissions = {}

    @extend_schema(responses=inline_serializer("Org", {"legal_entities": LegalEntitySerializer(many=True),
                                                        "branches": BranchSerializer(many=True)}))
    def get(self, request):
        branches = Branch.objects.select_related("legal_entity").order_by("code")
        allowed = request.membership.branch_ids()
        if allowed is not None:
            branches = branches.filter(id__in=allowed)
        return Response({"legal_entities": LegalEntitySerializer(LegalEntity.objects.all(), many=True).data,
                         "branches": BranchSerializer(branches, many=True).data})


class BranchWrite(serializers.ModelSerializer):
    class Meta:
        model = Branch
        fields = ["id", "legal_entity", "name_ar", "name_en", "code", "business_type", "address", "phone", "is_active"]

    def validate_legal_entity(self, value):
        if not LegalEntity.objects.filter(id=value.id).exists():
            raise serializers.ValidationError("unknown legal entity")
        return value


class BranchesView(TenantAPIView):
    required_permissions = {"POST": "org.manage"}

    @extend_schema(request=BranchWrite, responses={201: BranchWrite})
    def post(self, request):
        from django.db import IntegrityError, transaction

        from apps.core.errors import DomainError
        from apps.platform.services.limits import check_limit
        s = BranchWrite(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                check_limit(request.tenant_id, "branches", Branch.objects.filter(is_active=True).count())
                branch = s.save()
        except IntegrityError:
            raise DomainError(code="branch_code_exists")
        return Response(BranchWrite(branch).data, status=201)


class BranchDetailView(TenantAPIView):
    required_permissions = {"PATCH": "org.manage"}

    @extend_schema(request=BranchWrite, responses=BranchWrite)
    def patch(self, request, pk):
        from rest_framework.generics import get_object_or_404

        from apps.platform.services.limits import check_limit
        branch = get_object_or_404(Branch.objects.all(), pk=pk)
        s = BranchWrite(branch, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        if s.validated_data.get("is_active") and not branch.is_active:
            check_limit(request.tenant_id, "branches", Branch.objects.filter(is_active=True).count())
        return Response(BranchWrite(s.save()).data)


class SubscriptionView(TenantAPIView):
    """The tenant's own plan and how much of it is used."""
    required_permissions = {}

    @extend_schema(responses=inline_serializer("SubscriptionOut", {
        "plan": serializers.DictField(), "current_period_end": serializers.DateField(),
        "hosts": serializers.ListField(child=serializers.CharField()), "usage": serializers.DictField(child=serializers.IntegerField())}))
    def get(self, request):
        from apps.platform.models import Subscription
        from apps.staff.models import StaffMember
        sub = Subscription.objects.select_related("plan").filter(tenant_id=request.tenant_id).first()
        if sub is None:
            return Response({"plan": None, "current_period_end": None, "usage": {}})
        p = sub.plan
        return Response({
            "plan": {"code": p.code, "name_ar": p.name_ar, "name_en": p.name_en, "monthly_price": str(p.monthly_price),
                     "max_branches": p.max_branches, "max_staff": p.max_staff},
            "current_period_end": sub.current_period_end,
            "hosts": [d.host for d in sub.tenant.domains.filter(is_active=True).order_by("kind", "id")],
            "usage": {"branches": Branch.objects.filter(is_active=True).count(),
                      "staff": StaffMember.objects.filter(is_active=True).count()}})
