from datetime import date

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.booking.models import Appointment
from apps.booking.services.appointments import ItemSpec, create_appointment, reschedule, set_status
from apps.core.dates import business_date
from apps.core.services.infra import idempotent
from apps.tenancy.api.base import TenantAPIView, branch_for


class ItemOut(serializers.Serializer):
    id = serializers.IntegerField()
    service_id = serializers.IntegerField()
    staff_id = serializers.IntegerField()
    service_name_ar = serializers.CharField(source="service.name_ar")
    service_name_en = serializers.CharField(source="service.name_en")
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()


class AppointmentOut(serializers.ModelSerializer):
    items = serializers.SerializerMethodField()
    customer_name = serializers.SerializerMethodField()
    beneficiary_name = serializers.SerializerMethodField()
    customer_phone = serializers.SerializerMethodField()
    invoice_id = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = ["id", "branch", "customer", "beneficiary", "walk_in_name", "customer_name", "beneficiary_name",
                  "customer_phone", "status", "source", "starts_at", "ends_at", "business_date", "notes", "status_reason",
                  "invoice_id", "items"]

    def get_items(self, obj) -> list[dict]:
        return ItemOut(sorted(obj.items.all(), key=lambda i: i.position), many=True).data

    def get_customer_name(self, obj) -> str:
        return obj.customer.full_name if obj.customer_id else obj.walk_in_name

    def get_beneficiary_name(self, obj) -> str:
        return obj.beneficiary.full_name if obj.beneficiary_id else ""

    def get_customer_phone(self, obj) -> str:
        return obj.customer.phone if obj.customer_id else ""

    def get_invoice_id(self, obj) -> int | None:
        inv = getattr(obj, "invoice", None)
        return inv.id if inv else None


class ItemIn(serializers.Serializer):
    service_id = serializers.IntegerField()
    staff_id = serializers.IntegerField()


class AppointmentIn(serializers.Serializer):
    branch_id = serializers.IntegerField()
    starts_at = serializers.DateTimeField()
    items = ItemIn(many=True)
    customer_id = serializers.IntegerField(required=False, allow_null=True)
    beneficiary_id = serializers.IntegerField(required=False, allow_null=True)
    walk_in_name = serializers.CharField(required=False, allow_blank=True, default="")
    source = serializers.ChoiceField(choices=[Appointment.Source.RECEPTION, Appointment.Source.WALK_IN], default="reception")
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class RescheduleIn(serializers.Serializer):
    starts_at = serializers.DateTimeField()
    items = ItemIn(many=True)


class StatusIn(serializers.Serializer):
    status = serializers.ChoiceField(choices=Appointment.Status.choices)
    reason = serializers.CharField(required=False, allow_blank=True, default="")


def _qs():
    return Appointment.objects.select_related("customer", "beneficiary", "invoice").prefetch_related("items__service")


def _get(request, pk):
    appt = get_object_or_404(_qs(), pk=pk)
    branch_for(request, appt.branch_id)
    return appt


class AppointmentsView(TenantAPIView):
    required_permissions = {"GET": "booking.view", "POST": "booking.manage"}

    @extend_schema(parameters=[OpenApiParameter("branch_id", int, required=True), OpenApiParameter("date", str)],
                   responses=AppointmentOut(many=True))
    def get(self, request):
        branch = branch_for(request, request.query_params.get("branch_id"))
        day = date.fromisoformat(request.query_params["date"]) if request.query_params.get("date") else business_date()
        qs = _qs().filter(branch=branch, business_date=day).order_by("starts_at")
        return Response(AppointmentOut(qs, many=True).data)

    @extend_schema(request=AppointmentIn, responses={201: AppointmentOut})
    @idempotent
    def post(self, request):
        s = AppointmentIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        appt = create_appointment(branch=branch_for(request, v["branch_id"]), starts_at=v["starts_at"],
                                  items=[ItemSpec(**i) for i in v["items"]], customer_id=v.get("customer_id"),
                                  beneficiary_id=v.get("beneficiary_id"), walk_in_name=v["walk_in_name"],
                                  source=v["source"], notes=v["notes"], user=request.user)
        return Response(AppointmentOut(_qs().get(id=appt.id)).data, status=status.HTTP_201_CREATED)


class AppointmentDetailView(TenantAPIView):
    required_permissions = {"GET": "booking.view", "PATCH": "booking.manage"}

    @extend_schema(responses=AppointmentOut)
    def get(self, request, pk):
        return Response(AppointmentOut(_get(request, pk)).data)

    @extend_schema(request=RescheduleIn, responses=AppointmentOut)
    def patch(self, request, pk):
        appt = _get(request, pk)
        s = RescheduleIn(data=request.data)
        s.is_valid(raise_exception=True)
        reschedule(appt, starts_at=s.validated_data["starts_at"], items=[ItemSpec(**i) for i in s.validated_data["items"]],
                   user=request.user)
        return Response(AppointmentOut(_qs().get(id=pk)).data)


class AppointmentStatusView(TenantAPIView):
    required_permissions = {"POST": "booking.manage"}

    @extend_schema(request=StatusIn, responses=AppointmentOut)
    def post(self, request, pk):
        appt = _get(request, pk)
        s = StatusIn(data=request.data)
        s.is_valid(raise_exception=True)
        set_status(appt, s.validated_data["status"], user=request.user, reason=s.validated_data["reason"])
        return Response(AppointmentOut(_qs().get(id=pk)).data)
