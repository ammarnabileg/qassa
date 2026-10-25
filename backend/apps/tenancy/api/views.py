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
        fields = ["id", "legal_entity", "name_ar", "name_en", "code", "business_type", "timezone", "is_active"]


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
