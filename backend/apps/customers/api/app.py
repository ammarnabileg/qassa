"""Customer app API (/api/v1/app/…). The salon is the owner of the host (company domain, D-005); on the platform
host (store app, local testing) the X-Salon header names it. Customers authenticate with
`Authorization: Customer <token>` issued after phone + code (D-003)."""
import math
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import NotAuthenticated
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.audit.services.log import record as audit
from apps.booking.models import Appointment
from apps.booking.services.appointments import ItemSpec, create_appointment, set_status
from apps.booking.services.slots import free_slots
from apps.catalog.models import Service, ServiceCategory
from apps.catalog.services.pricing import price_on
from apps.core.dates import business_date
from apps.core.errors import DomainError
from apps.core.services.infra import idempotent
from apps.customers.models import Beneficiary, Customer
from apps.customers.services import otp
from apps.customers.services.phone import normalize_phone
from apps.tenancy.api.public import resolve
from apps.tenancy.context import set_context
from apps.tenancy.models import Branch

CANCEL_BEFORE = timedelta(hours=1)


class AppView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public"
    customer_required = True

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        tenant = resolve(request, request.headers.get("X-Salon", "").strip().lower() or None)
        request.tenant = tenant
        set_context(tenant.id)
        request.customer = None
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Customer "):
            data = otp.read_token(auth[9:].strip())
            if data and data.get("t") == tenant.id:
                request.customer = Customer.objects.filter(id=data["c"], is_active=True).first()
        if self.customer_required and request.customer is None:
            raise NotAuthenticated("Customer login required")

    def get_throttles(self):
        return [] if self.request.method == "GET" else super().get_throttles()


class PhoneIn(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    lang = serializers.ChoiceField(choices=["ar", "en"], default="ar")

    def validate_phone(self, v):
        try:
            return normalize_phone(v)
        except DomainError as e:
            raise serializers.ValidationError(e.code)


class VerifyIn(PhoneIn):
    code = serializers.CharField(max_length=8)


class OtpRequestView(AppView):
    customer_required = False

    @extend_schema(request=PhoneIn, responses={200: dict})
    def post(self, request):
        s = PhoneIn(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(otp.request_code(request.tenant, s.validated_data["phone"], lang=s.validated_data["lang"],
                                         ip=request.META.get("REMOTE_ADDR")))


class OtpVerifyView(AppView):
    customer_required = False

    @extend_schema(request=VerifyIn, responses={200: dict})
    def post(self, request):
        s = VerifyIn(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(otp.verify_code(request.tenant, s.validated_data["phone"], s.validated_data["code"]))


class ChildIn(serializers.Serializer):
    full_name = serializers.CharField(max_length=120)
    birth_date = serializers.DateField(required=False, allow_null=True)
    gender = serializers.ChoiceField(choices=["", "m", "f"], default="")


class RegisterIn(serializers.Serializer):
    registration_token = serializers.CharField()
    full_name = serializers.CharField(max_length=120)
    lang = serializers.ChoiceField(choices=["ar", "en"], default="ar")
    self_service = serializers.BooleanField(default=True)  # the customer is also served (not only their children)
    children = ChildIn(many=True, required=False, default=list)


class BeneficiaryOut(serializers.ModelSerializer):
    class Meta:
        model = Beneficiary
        fields = ["id", "full_name", "relation", "birth_date", "gender"]


def me_payload(c: Customer) -> dict:
    from apps.core.dates import business_date
    from apps.loyalty.models import CustomerPackage, LoyaltySettings
    from apps.loyalty.services import points
    cfg = LoyaltySettings.objects.first()
    pkgs = (CustomerPackage.objects.select_related("plan").filter(customer=c, voided=False, sessions_left__gt=0,
                                                                expires_on__gte=business_date()).order_by("expires_on"))
    return {"id": c.id, "full_name": c.full_name, "phone": c.phone, "preferred_language": c.preferred_language,
            "beneficiaries": BeneficiaryOut(c.beneficiaries.filter(is_active=True).order_by("id"), many=True).data,
            "points": points.balance(c) if cfg and cfg.enabled else None,
            "points_value": str(cfg.point_value) if cfg and cfg.enabled else None,
            "packages": [{"name_ar": k.plan.name_ar if k.plan_id else "", "name_en": (k.plan.name_en or k.plan.name_ar) if k.plan_id else "",
                          "sessions_left": k.sessions_left, "sessions_total": k.sessions_total, "expires_on": k.expires_on.isoformat()}
                         for k in pkgs]}


class RegisterView(AppView):
    customer_required = False

    @extend_schema(request=RegisterIn, responses={201: dict})
    def post(self, request):
        s = RegisterIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        reg = otp.read_registration(v["registration_token"])
        if reg["t"] != request.tenant.id:
            raise DomainError(code="registration_expired")
        if not v["self_service"] and not v["children"]:
            raise DomainError(code="register_needs_beneficiary")
        with transaction.atomic():
            c, created = Customer.objects.get_or_create(phone=reg["p"], defaults={
                "full_name": v["full_name"].strip(), "preferred_language": v["lang"], "whatsapp_opt_in": True})
            if created:
                if v["self_service"]:
                    Beneficiary.objects.create(customer=c, full_name=c.full_name, relation="self")
                for ch in v["children"]:
                    Beneficiary.objects.create(customer=c, relation="child", full_name=ch["full_name"].strip(),
                                               birth_date=ch.get("birth_date"), gender=ch.get("gender", ""))
                audit("customer.registered", tenant_id=request.tenant.id, obj=c, data={"source": "app"})
        return Response({"token": otp.issue_token(request.tenant, c), "me": me_payload(c)}, status=status.HTTP_201_CREATED)


class MeView(AppView):
    @extend_schema(responses=dict)
    def get(self, request):
        return Response(me_payload(request.customer))


class MyBeneficiariesView(AppView):
    @extend_schema(request=ChildIn, responses={201: dict})
    def post(self, request):
        s = ChildIn(data=request.data)
        s.is_valid(raise_exception=True)
        Beneficiary.objects.create(customer=request.customer, relation="child", **s.validated_data)
        return Response(me_payload(request.customer), status=status.HTTP_201_CREATED)


def _distance_km(lat1, lng1, lat2, lng2):
    p = math.pi / 180
    a = 0.5 - math.cos((lat2 - lat1) * p) / 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lng2 - lng1) * p)) / 2
    return 12742 * math.asin(math.sqrt(a))


class CatalogView(AppView):
    """Branches (nearest first when the app sends its location), categories and services with today's price."""
    customer_required = False

    @extend_schema(parameters=[OpenApiParameter("lat", float), OpenApiParameter("lng", float)], responses=dict)
    def get(self, request):
        today = business_date()
        try:
            lat, lng = float(request.query_params["lat"]), float(request.query_params["lng"])
        except (KeyError, ValueError):
            lat = lng = None
        branches = []
        for b in Branch.objects.filter(is_active=True, online_booking=True).order_by("code"):
            d = (round(_distance_km(lat, lng, float(b.latitude), float(b.longitude)), 1)
                 if lat is not None and b.latitude is not None and b.longitude is not None else None)
            branches.append({"id": b.id, "name_ar": b.name_ar, "name_en": b.name_en, "business_type": b.business_type,
                             "address": b.address, "phone": b.phone, "latitude": b.latitude, "longitude": b.longitude,
                             "opens_at": b.opens_at.strftime("%H:%M"), "closes_at": b.closes_at.strftime("%H:%M"), "distance_km": d})
        branches.sort(key=lambda x: (x["distance_km"] is None, x["distance_km"] or 0))
        if branches and branches[0]["distance_km"] is not None:
            branches[0]["recommended"] = True
        types = {b["business_type"] for b in branches}
        cats = ServiceCategory.objects.filter(business_type__in=types).order_by("sort", "id")
        services = []
        for s in Service.objects.select_related("category").filter(is_active=True, category__business_type__in=types):
            price = price_on(s, None, today)
            if price is not None:
                services.append({"id": s.id, "category": s.category_id, "business_type": s.category.business_type,
                                 "name_ar": s.name_ar, "name_en": s.name_en, "duration_minutes": s.duration_minutes,
                                 "price": str(price)})
        return Response({"salon": {"name": request.tenant.name, "business_type": request.tenant.default_business_type},
                         "branches": branches, "categories": [{"id": c.id, "name_ar": c.name_ar, "name_en": c.name_en,
                                                               "business_type": c.business_type} for c in cats],
                         "services": services})


def _branch_service(branch_id, service_id):
    branch = Branch.objects.filter(id=branch_id, is_active=True, online_booking=True).first()
    service = Service.objects.select_related("category").filter(id=service_id, is_active=True).first()
    if branch is None:
        raise DomainError(code="branch_unknown")
    if service is None or service.category.business_type != branch.business_type:
        raise DomainError(code="service_not_for_branch")
    return branch, service


class SlotsView(AppView):
    customer_required = False

    @extend_schema(parameters=[OpenApiParameter("branch_id", int, required=True), OpenApiParameter("service_id", int, required=True),
                               OpenApiParameter("date", str, required=True), OpenApiParameter("staff_id", int)], responses=dict)
    def get(self, request):
        q = request.query_params
        branch, service = _branch_service(q.get("branch_id"), q.get("service_id"))
        day = date.fromisoformat(q["date"])
        if day < business_date() or day > business_date() + timedelta(days=30):
            raise DomainError(code="date_out_of_range")
        from apps.booking.services.slots import qualified_staff
        staff = [{"id": s.id, "name_ar": s.full_name_ar, "name_en": s.full_name_en} for s in qualified_staff(branch, service)]
        return Response({"staff": staff, "slots": free_slots(branch, service, day, int(q["staff_id"]) if q.get("staff_id") else None),
                         "price": str(price_on(service, branch.id, day) or "")})


class BookIn(serializers.Serializer):
    branch_id = serializers.IntegerField()
    service_id = serializers.IntegerField()
    starts_at = serializers.DateTimeField()
    beneficiary_id = serializers.IntegerField()
    staff_id = serializers.IntegerField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="", max_length=300)


def booking_payload(a: Appointment) -> dict:
    items = sorted(a.items.all(), key=lambda i: i.position)
    return {"id": a.id, "status": a.status, "branch_id": a.branch_id, "starts_at": timezone.localtime(a.starts_at).isoformat(), "ends_at": timezone.localtime(a.ends_at).isoformat(),
            "beneficiary_name": a.beneficiary.full_name if a.beneficiary_id else "",
            "services": [{"name_ar": i.service.name_ar, "name_en": i.service.name_en, "staff_ar": i.staff.full_name_ar,
                          "staff_en": i.staff.full_name_en} for i in items],
            "can_cancel": a.status == Appointment.Status.BOOKED and a.starts_at - timezone.now() > CANCEL_BEFORE}


class MyBookingsView(AppView):
    @extend_schema(responses=dict)
    def get(self, request):
        qs = (Appointment.objects.filter(customer=request.customer).select_related("beneficiary")
              .prefetch_related("items__service", "items__staff").order_by("-starts_at")[:30])
        return Response([booking_payload(a) for a in qs])

    @extend_schema(request=BookIn, responses={201: dict})
    @idempotent
    def post(self, request):
        s = BookIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        branch, service = _branch_service(v["branch_id"], v["service_id"])
        if not request.customer.beneficiaries.filter(id=v["beneficiary_id"], is_active=True).exists():
            raise DomainError(code="beneficiary_unknown")
        start = v["starts_at"]
        local = timezone.localtime(start)
        opening = [x for x in free_slots(branch, service, local.date(), v.get("staff_id"))
                   if x["starts_at"] == local.isoformat()]
        if not opening:
            raise DomainError(code="slot_unavailable", message="This time is no longer available")
        staff_id = v.get("staff_id") or opening[0]["staff_ids"][0]
        appt = create_appointment(branch=branch, starts_at=start, items=[ItemSpec(service.id, staff_id)],
                                  customer_id=request.customer.id, beneficiary_id=v["beneficiary_id"],
                                  source=Appointment.Source.ONLINE, notes=v["notes"])
        appt = Appointment.objects.select_related("beneficiary").prefetch_related("items__service", "items__staff").get(id=appt.id)
        return Response(booking_payload(appt), status=status.HTTP_201_CREATED)


class MyBookingCancelView(AppView):
    @extend_schema(request=None, responses=dict)
    def post(self, request, pk):
        a = Appointment.objects.filter(id=pk, customer=request.customer).first()
        if a is None:
            raise DomainError(code="appointment_unknown")
        if not booking_payload(a)["can_cancel"]:
            raise DomainError(code="cancel_too_late", message="Bookings can be cancelled up to 1 hour before")
        set_status(a, Appointment.Status.CANCELLED, reason="cancelled by customer (app)")
        a = Appointment.objects.select_related("beneficiary").prefetch_related("items__service", "items__staff").get(id=pk)
        return Response(booking_payload(a))
