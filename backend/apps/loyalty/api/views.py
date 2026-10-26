from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.core.errors import DomainError
from apps.customers.models import Customer
from apps.loyalty.models import Coupon, CustomerPackage, LoyaltySettings, PackagePlan, PointsEntry
from apps.loyalty.services import points
from apps.tenancy.api.base import TenantAPIView


class PackagePlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = PackagePlan
        fields = ["id", "name_ar", "name_en", "service", "sessions", "price", "validity_days", "is_active"]

    def validate_service(self, v):
        from apps.catalog.models import Service
        if not Service.objects.filter(id=v.id).exists():
            raise serializers.ValidationError("unknown service")
        return v


class PlansView(TenantAPIView):
    required_permissions = {"GET": "catalog.view", "POST": "marketing.manage"}

    @extend_schema(responses=PackagePlanSerializer(many=True))
    def get(self, request):
        return Response(PackagePlanSerializer(PackagePlan.objects.order_by("-is_active", "name_ar"), many=True).data)

    @extend_schema(request=PackagePlanSerializer, responses={201: PackagePlanSerializer})
    def post(self, request):
        s = PackagePlanSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(PackagePlanSerializer(s.save()).data, status=status.HTTP_201_CREATED)


class PlanDetailView(TenantAPIView):
    required_permissions = {"PATCH": "marketing.manage"}

    @extend_schema(request=PackagePlanSerializer, responses=PackagePlanSerializer)
    def patch(self, request, pk):
        plan = get_object_or_404(PackagePlan.objects.all(), pk=pk)
        s = PackagePlanSerializer(plan, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        return Response(PackagePlanSerializer(s.save()).data)


class CustomerWalletView(TenantAPIView):
    """What a customer can use at the till: active packages and the points balance."""
    required_permissions = {"GET": "customers.view"}

    @extend_schema(responses=dict)
    def get(self, request, pk):
        c = get_object_or_404(Customer.objects.all(), pk=pk)
        pkgs = CustomerPackage.objects.filter(customer=c, voided=False).select_related("plan", "service").order_by("expires_on")
        return Response({
            "points": points.balance(c),
            "packages": [{"id": p.id, "name_ar": p.plan.name_ar, "name_en": p.plan.name_en, "service_id": p.service_id,
                          "sessions_left": p.sessions_left, "sessions_total": p.sessions_total, "session_value": str(p.session_value),
                          "expires_on": p.expires_on} for p in pkgs],
            "history": [{"kind": e.kind, "points": e.points, "invoice": e.invoice.number if e.invoice_id else "", "created_at": e.created_at}
                        for e in PointsEntry.objects.filter(customer=c).select_related("invoice").order_by("-id")[:20]]})


class SettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoyaltySettings
        fields = ["enabled", "points_per_kd", "point_value", "min_redeem"]


class LoyaltySettingsView(TenantAPIView):
    required_permissions = {"GET": "customers.view", "PATCH": "marketing.manage"}

    @extend_schema(responses=SettingsSerializer)
    def get(self, request):
        return Response(SettingsSerializer(LoyaltySettings.objects.first() or LoyaltySettings()).data)

    @extend_schema(request=SettingsSerializer, responses=SettingsSerializer)
    def patch(self, request):
        obj = LoyaltySettings.objects.first() or LoyaltySettings()
        s = SettingsSerializer(obj, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        return Response(SettingsSerializer(s.save()).data)


class CouponSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coupon
        fields = ["id", "code", "kind", "value", "min_total", "valid_from", "valid_to", "max_uses", "used_count", "is_active"]
        read_only_fields = ["used_count"]
        validators = []

    def validate_code(self, v):
        return v.strip().upper()

    def validate(self, data):
        if data.get("kind", getattr(self.instance, "kind", None)) == "percent" and data.get("value", 0) > 100:
            raise serializers.ValidationError({"value": "max 100"})
        if data.get("valid_to") and data.get("valid_from") and data["valid_to"] < data["valid_from"]:
            raise serializers.ValidationError({"valid_to": "before valid_from"})
        return data


class CouponsView(TenantAPIView):
    required_permissions = {"GET": "catalog.view", "POST": "marketing.manage"}

    @extend_schema(responses=CouponSerializer(many=True))
    def get(self, request):
        return Response(CouponSerializer(Coupon.objects.order_by("-id"), many=True).data)

    @extend_schema(request=CouponSerializer, responses={201: CouponSerializer})
    def post(self, request):
        from django.db import IntegrityError, transaction
        s = CouponSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                c = s.save()
        except IntegrityError:
            raise DomainError(code="coupon_code_exists")
        return Response(CouponSerializer(c).data, status=status.HTTP_201_CREATED)


class CouponDetailView(TenantAPIView):
    required_permissions = {"PATCH": "marketing.manage"}

    @extend_schema(request=CouponSerializer, responses=CouponSerializer)
    def patch(self, request, pk):
        c = get_object_or_404(Coupon.objects.all(), pk=pk)
        s = CouponSerializer(c, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        return Response(CouponSerializer(s.save()).data)
