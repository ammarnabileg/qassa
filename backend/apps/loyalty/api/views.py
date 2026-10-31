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
        fields = ["enabled", "points_per_kd", "point_value", "min_redeem", "tiers", "welcome_points", "birthday_points", "expiry_months"]

    def validate_tiers(self, v):
        if not isinstance(v, list) or len(v) > 6:
            raise serializers.ValidationError("max 6 tiers")
        out = []
        for t in v:
            try:
                row = {"name_ar": str(t["name_ar"]).strip()[:40], "name_en": str(t.get("name_en", "")).strip()[:40],
                       "min": int(t["min"]), "mul": float(t["mul"])}
            except (KeyError, TypeError, ValueError):
                raise serializers.ValidationError("each tier needs name_ar, min, mul")
            if not row["name_ar"] or row["min"] < 0 or not (1 <= row["mul"] <= 5):
                raise serializers.ValidationError("name required, min >= 0, multiplier 1–5")
            out.append(row)
        out.sort(key=lambda t: t["min"])
        if out and out[0]["min"] != 0:
            raise serializers.ValidationError("the first tier must start at 0")
        if len({t["min"] for t in out}) != len(out):
            raise serializers.ValidationError("tiers must start at different points")
        return out


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


class PointsOverviewView(TenantAPIView):
    """Reference "النقاط والولاء": program status, outstanding points and their value, balances and latest movements."""
    required_permissions = {"GET": "customers.view"}

    @extend_schema(responses=dict)
    def get(self, request):
        from django.db.models import Q, Sum
        from apps.core.dates import business_date
        from apps.customers.models import Customer
        from apps.loyalty.models import PointsEntry
        cfg = LoyaltySettings.objects.first() or LoyaltySettings()
        from decimal import Decimal
        pv = Decimal(str(cfg.point_value))   # an unsaved default holds the string "0.010"
        month = business_date().replace(day=1)
        per = {r["customer_id"]: r for r in PointsEntry.objects.values("customer_id").annotate(
            bal=Sum("points"), earned=Sum("points", filter=Q(kind="earn")), used=Sum("points", filter=Q(kind="redeem")),
            life=Sum("points", filter=Q(kind__in=["earn", "reverse", "gift"])))}
        tiers = sorted(cfg.tiers or [], key=lambda t: t["min"])
        tier_of = {cid: points.tier_for(cfg, r["life"] or 0) for cid, r in per.items()}
        outstanding = sum(max(r["bal"] or 0, 0) for r in per.values())
        names = {c.id: c for c in Customer.objects.filter(id__in=list(per)).prefetch_related("beneficiaries")}
        rows = sorted(per.values(), key=lambda r: -(r["bal"] or 0))[:100]
        recent = PointsEntry.objects.select_related("customer", "invoice").order_by("-id")[:15]
        return Response({
            "settings": SettingsSerializer(cfg).data,
            "outstanding": outstanding, "outstanding_value": str((pv * outstanding).quantize(Decimal("0.001"))),
            "tiers": [{**t, "customers": sum(1 for x in tier_of.values() if x is not None and x["min"] == t["min"])} for t in tiers],
            "redeemed_month": -(PointsEntry.objects.filter(kind="redeem", created_at__date__gte=month).aggregate(s=Sum("points"))["s"] or 0),
            "balances": [{"customer_id": r["customer_id"], "name": names[r["customer_id"]].full_name, "phone": names[r["customer_id"]].phone,
                          "kids": [b.full_name for b in names[r["customer_id"]].beneficiaries.all() if b.relation != "self"],
                          "tier": tier_of[r["customer_id"]]["name_ar"] if tier_of[r["customer_id"]] else "",
                          "tier_en": (tier_of[r["customer_id"]] or {}).get("name_en", ""),
                          "balance": r["bal"] or 0, "earned": r["earned"] or 0, "used": -(r["used"] or 0),
                          "value": str((pv * max(r["bal"] or 0, 0)).quantize(Decimal("0.001")))} for r in rows],
            "recent": [{"id": e.id, "name": e.customer.full_name, "kind": e.kind, "points": e.points, "at": e.created_at,
                        "invoice": e.invoice.number if e.invoice_id else "", "note": e.note} for e in recent],
        })


class PointsAdjustIn(serializers.Serializer):
    customer_id = serializers.IntegerField()
    points = serializers.IntegerField()
    note = serializers.CharField(max_length=200)


class PointsAdjustView(TenantAPIView):
    """Manual add / deduct with a reason; audited. A deduction can't take the balance below zero."""
    required_permissions = {"POST": "marketing.manage"}

    @extend_schema(request=PointsAdjustIn, responses=dict)
    def post(self, request):
        from django.db import transaction
        from apps.audit.services.log import record as audit
        from apps.customers.models import Customer
        from apps.loyalty.services import points as pts
        s = PointsAdjustIn(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        if d["points"] == 0:
            raise DomainError(code="points_zero")
        with transaction.atomic():
            customer = Customer.objects.select_for_update().filter(id=d["customer_id"]).first()
            if customer is None:
                raise DomainError(code="not_found")
            if pts.balance(customer) + d["points"] < 0:
                raise DomainError(code="points_insufficient", details={"balance": pts.balance(customer)})
            pts.record(customer, d["points"], "adjust", note=d["note"])
        audit("loyalty.points_adjusted", tenant_id=request.tenant_id, actor=request.user, obj=customer, data={"points": d["points"], "note": d["note"]})
        return Response({"balance": pts.balance(customer)})
