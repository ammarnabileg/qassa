from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.catalog.models import Service
from apps.core.errors import DomainError
from apps.platform.services.limits import check_limit
from apps.staff.models import StaffBranch, StaffMember, StaffSkill
from apps.tenancy.api.base import TenantAPIView
from apps.tenancy.models import Branch


class StaffSerializer(serializers.ModelSerializer):
    branch_ids = serializers.ListField(child=serializers.IntegerField(), required=False)
    service_ids = serializers.ListField(child=serializers.IntegerField(), required=False)

    class Meta:
        model = StaffMember
        fields = ["id", "full_name_ar", "full_name_en", "phone", "is_active", "branch_ids", "service_ids"]

    def to_representation(self, obj):
        data = super().to_representation(obj)
        data["branch_ids"] = sorted(link.branch_id for link in obj.branch_links.all())
        data["service_ids"] = sorted(link.service_id for link in obj.skill_links.all())
        return data


def _save_links(staff, branch_ids, service_ids):
    if branch_ids is not None:
        if Branch.objects.filter(id__in=branch_ids).count() != len(set(branch_ids)):
            raise DomainError(code="branch_unknown")
        StaffBranch.objects.filter(staff=staff).exclude(branch_id__in=branch_ids).delete()
        for b in set(branch_ids) - set(staff.branch_links.values_list("branch_id", flat=True)):
            StaffBranch.objects.create(staff=staff, branch_id=b)
    if service_ids is not None:
        if Service.objects.filter(id__in=service_ids).count() != len(set(service_ids)):
            raise DomainError(code="service_unknown")
        StaffSkill.objects.filter(staff=staff).exclude(service_id__in=service_ids).delete()
        for sv in set(service_ids) - set(staff.skill_links.values_list("service_id", flat=True)):
            StaffSkill.objects.create(staff=staff, service_id=sv)


def _staff_qs():
    return StaffMember.objects.prefetch_related("branch_links", "skill_links").order_by("full_name_ar")


class StaffListView(TenantAPIView):
    required_permissions = {"GET": "staff.view", "POST": "staff.manage"}

    @extend_schema(responses=StaffSerializer(many=True))
    def get(self, request):
        qs = _staff_qs()
        allowed = request.membership.branch_ids()
        if allowed is not None:  # branch-scoped members only see staff of their branches
            qs = qs.filter(branch_links__branch_id__in=allowed).distinct()
        return Response(StaffSerializer(qs, many=True).data)

    @extend_schema(request=StaffSerializer, responses={201: StaffSerializer})
    def post(self, request):
        s = StaffSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        with transaction.atomic():
            check_limit(request.tenant_id, "staff", StaffMember.objects.filter(is_active=True).count())
            branch_ids = s.validated_data.pop("branch_ids", [])
            service_ids = s.validated_data.pop("service_ids", [])
            staff = StaffMember.objects.create(**s.validated_data)
            _save_links(staff, branch_ids, service_ids)
        return Response(StaffSerializer(_staff_qs().get(id=staff.id)).data, status=status.HTTP_201_CREATED)


class StaffDetailView(TenantAPIView):
    required_permissions = {"PATCH": "staff.manage"}

    @extend_schema(request=StaffSerializer, responses=StaffSerializer)
    def patch(self, request, pk):
        staff = get_object_or_404(StaffMember.objects.all(), pk=pk)
        s = StaffSerializer(staff, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        with transaction.atomic():
            branch_ids = s.validated_data.pop("branch_ids", None)
            service_ids = s.validated_data.pop("service_ids", None)
            if s.validated_data.get("is_active") and not staff.is_active:
                check_limit(request.tenant_id, "staff", StaffMember.objects.filter(is_active=True).count())
            for k, v in s.validated_data.items():
                setattr(staff, k, v)
            staff.save()
            _save_links(staff, branch_ids, service_ids)
        return Response(StaffSerializer(_staff_qs().get(id=pk)).data)
