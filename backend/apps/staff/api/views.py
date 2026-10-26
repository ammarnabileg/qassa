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
        fields = ["id", "full_name_ar", "full_name_en", "phone", "commission_percent", "is_active", "branch_ids", "service_ids"]

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


# ---------- commissions ----------
class CommissionsView(TenantAPIView):
    """Commission balance per staff member and recent entries."""
    required_permissions = {"GET": "commission.view.all"}

    @extend_schema(responses=dict)
    def get(self, request):
        from apps.staff.models import CommissionEntry
        from apps.staff.services import commissions
        rows = []
        for s in _staff_qs():
            entries = CommissionEntry.objects.filter(staff=s).order_by("-id")
            rows.append({"staff_id": s.id, "name_ar": s.full_name_ar, "name_en": s.full_name_en, "rate": str(s.commission_percent),
                         "balance": str(commissions.balance(s)),
                         "recent": [{"kind": e.kind, "amount": str(e.amount), "base": str(e.base), "reference": e.reference,
                                     "created_at": e.created_at} for e in entries[:10]]})
        return Response(rows)


class PayoutIn(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=18, decimal_places=3, min_value=0)
    reference = serializers.CharField(max_length=60)
    branch_id = serializers.IntegerField()


class CommissionPayoutView(TenantAPIView):
    required_permissions = {"POST": "commission.pay"}

    @extend_schema(request=PayoutIn, responses={201: dict})
    def post(self, request, pk):
        from apps.staff.services import commissions
        from apps.tenancy.api.base import branch_for
        staff = get_object_or_404(StaffMember.objects.all(), pk=pk)
        s = PayoutIn(data=request.data)
        s.is_valid(raise_exception=True)
        branch = branch_for(request, s.validated_data["branch_id"])
        commissions.pay_out(staff=staff, amount=s.validated_data["amount"], reference=s.validated_data["reference"],
                            legal_entity_id=branch.legal_entity_id, branch_id=branch.id, user=request.user)
        return Response({"balance": str(commissions.balance(staff))}, status=status.HTTP_201_CREATED)


# ---------- working hours & time off ----------
class HourIn(serializers.Serializer):
    branch_id = serializers.IntegerField()
    weekday = serializers.IntegerField(min_value=0, max_value=6)
    starts_at = serializers.TimeField()
    ends_at = serializers.TimeField()


class ScheduleIn(serializers.Serializer):
    hours = HourIn(many=True)


class StaffScheduleView(TenantAPIView):
    """Weekly hours (replaced as a whole) and time off of one staff member."""
    required_permissions = {"GET": "staff.view", "PUT": "staff.manage"}

    def _out(self, staff):
        from apps.staff.models import TimeOff, WorkingHours
        return {"hours": [{"branch_id": h.branch_id, "weekday": h.weekday, "starts_at": h.starts_at.strftime("%H:%M"),
                           "ends_at": h.ends_at.strftime("%H:%M")} for h in WorkingHours.objects.filter(staff=staff).order_by("weekday", "starts_at")],
                "time_off": [{"id": t.id, "starts_at": t.starts_at, "ends_at": t.ends_at, "reason": t.reason}
                             for t in TimeOff.objects.filter(staff=staff).order_by("-starts_at")[:30]]}

    @extend_schema(responses=dict)
    def get(self, request, pk):
        return Response(self._out(get_object_or_404(StaffMember.objects.all(), pk=pk)))

    @extend_schema(request=ScheduleIn, responses=dict)
    def put(self, request, pk):
        from apps.staff.models import WorkingHours
        staff = get_object_or_404(StaffMember.objects.all(), pk=pk)
        s = ScheduleIn(data=request.data)
        s.is_valid(raise_exception=True)
        linked = set(staff.branch_links.values_list("branch_id", flat=True))
        with transaction.atomic():
            WorkingHours.objects.filter(staff=staff).delete()
            for h in s.validated_data["hours"]:
                if h["branch_id"] not in linked:
                    raise DomainError(code="staff_not_in_branch")
                if h["ends_at"] <= h["starts_at"]:
                    raise DomainError(code="hours_invalid")
                WorkingHours.objects.create(staff=staff, **h)
        return Response(self._out(staff))


class TimeOffIn(serializers.Serializer):
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class StaffTimeOffView(TenantAPIView):
    required_permissions = {"POST": "staff.manage", "DELETE": "staff.manage"}

    @extend_schema(request=TimeOffIn, responses={201: dict})
    def post(self, request, pk):
        from apps.staff.models import TimeOff
        staff = get_object_or_404(StaffMember.objects.all(), pk=pk)
        s = TimeOffIn(data=request.data)
        s.is_valid(raise_exception=True)
        if s.validated_data["ends_at"] <= s.validated_data["starts_at"]:
            raise DomainError(code="hours_invalid")
        TimeOff.objects.create(staff=staff, **s.validated_data)
        return Response(StaffScheduleView()._out(staff), status=status.HTTP_201_CREATED)

    @extend_schema(responses={204: None})
    def delete(self, request, pk, off_id):
        from apps.staff.models import TimeOff
        get_object_or_404(TimeOff.objects.all(), pk=off_id, staff_id=pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
