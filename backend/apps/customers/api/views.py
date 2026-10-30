from django.db import IntegrityError, transaction
from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.core.errors import DomainError
from apps.customers.models import Beneficiary, Customer
from apps.customers.services.phone import normalize_phone
from apps.tenancy.api.base import TenantAPIView


class BeneficiarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Beneficiary
        fields = ["id", "full_name", "relation", "birth_date", "gender", "notes", "is_active"]


class CustomerSerializer(serializers.ModelSerializer):
    beneficiaries = BeneficiarySerializer(many=True, read_only=True)
    add_self = serializers.BooleanField(write_only=True, default=True)

    class Meta:
        model = Customer
        fields = ["id", "full_name", "phone", "email", "preferred_language", "whatsapp_opt_in", "marketing_opt_in",
                  "notes", "is_active", "created_at", "beneficiaries", "add_self"]
        read_only_fields = ["created_at"]

    def validate_phone(self, value):
        try:
            return normalize_phone(value)
        except DomainError as e:
            raise serializers.ValidationError(e.code)


def _qs():
    return Customer.objects.prefetch_related("beneficiaries").order_by("-id")


def _save(serializer, **extra):
    try:
        with transaction.atomic():
            return serializer.save(**extra)
    except IntegrityError:
        raise DomainError(code="customer_phone_exists", message="A customer with this phone already exists")


class CustomersView(TenantAPIView):
    required_permissions = {"GET": "customers.view", "POST": "customers.manage"}

    @extend_schema(parameters=[OpenApiParameter("q", str)], responses=CustomerSerializer(many=True))
    def get(self, request):
        qs = _qs()
        if q := request.query_params.get("q", "").strip():
            digits = "".join(ch for ch in q if ch.isdigit())
            cond = Q(full_name__icontains=q) | Q(beneficiaries__full_name__icontains=q)
            if len(digits) >= 3:
                cond |= Q(phone__contains=digits)
            qs = qs.filter(cond).distinct()
        return Response(CustomerSerializer(qs[:100], many=True).data)

    @extend_schema(request=CustomerSerializer, responses={201: CustomerSerializer})
    def post(self, request):
        s = CustomerSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        add_self = s.validated_data.pop("add_self")
        with transaction.atomic():
            customer = _save(s)
            if add_self:
                Beneficiary.objects.create(customer=customer, full_name=customer.full_name, relation="self")
        return Response(CustomerSerializer(_qs().get(id=customer.id)).data, status=status.HTTP_201_CREATED)


class CustomerDetailView(TenantAPIView):
    required_permissions = {"GET": "customers.view", "PATCH": "customers.manage"}

    @extend_schema(responses=CustomerSerializer)
    def get(self, request, pk):
        return Response(CustomerSerializer(get_object_or_404(_qs(), pk=pk)).data)

    @extend_schema(request=CustomerSerializer, responses=CustomerSerializer)
    def patch(self, request, pk):
        customer = get_object_or_404(Customer.objects.all(), pk=pk)
        s = CustomerSerializer(customer, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.validated_data.pop("add_self", None)
        _save(s)
        return Response(CustomerSerializer(_qs().get(id=pk)).data)


class BeneficiariesView(TenantAPIView):
    required_permissions = {"POST": "customers.manage"}

    @extend_schema(request=BeneficiarySerializer, responses={201: BeneficiarySerializer})
    def post(self, request, pk):
        customer = get_object_or_404(Customer.objects.all(), pk=pk)
        s = BeneficiarySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        if s.validated_data["relation"] == "self" and customer.beneficiaries.filter(relation="self").exists():
            raise DomainError(code="beneficiary_self_exists")
        return Response(BeneficiarySerializer(s.save(customer=customer)).data, status=status.HTTP_201_CREATED)


class BeneficiaryDetailView(TenantAPIView):
    required_permissions = {"PATCH": "customers.manage"}

    @extend_schema(request=BeneficiarySerializer, responses=BeneficiarySerializer)
    def patch(self, request, pk):
        b = get_object_or_404(Beneficiary.objects.all(), pk=pk)
        s = BeneficiarySerializer(b, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        return Response(BeneficiarySerializer(s.save()).data)


class KidsView(TenantAPIView):
    """Kids salons (reference "العملاء الصغار"): one row per child with the guardian, visits, spend and last visit."""
    required_permissions = {"GET": "customers.view"}

    @extend_schema(parameters=[OpenApiParameter("q", str)], responses=dict)
    def get(self, request):
        from django.db.models import Count, Max, Sum
        from apps.pos.models import Invoice
        qs = Beneficiary.objects.filter(is_active=True).exclude(relation="self").select_related("customer").order_by("-id")
        if q := request.query_params.get("q", "").strip():
            digits = "".join(ch for ch in q if ch.isdigit())
            cond = Q(full_name__icontains=q) | Q(customer__full_name__icontains=q)
            if len(digits) >= 3:
                cond |= Q(customer__phone__contains=digits)
            qs = qs.filter(cond)
        rows = list(qs[:300])
        stats = {r["beneficiary_id"]: r for r in Invoice.objects.filter(beneficiary_id__in=[b.id for b in rows])
                 .values("beneficiary_id").annotate(n=Count("id"), total=Sum("total"), last=Max("business_date"))}
        return Response([{"id": b.id, "customer_id": b.customer_id, "name": b.full_name, "birth_date": b.birth_date, "gender": b.gender,
                          "notes": b.notes, "guardian": b.customer.full_name, "phone": b.customer.phone,
                          "whatsapp_opt_in": b.customer.whatsapp_opt_in,
                          "visits": stats.get(b.id, {}).get("n", 0), "total": str(stats.get(b.id, {}).get("total") or "0.000"),
                          "last_visit": stats.get(b.id, {}).get("last")} for b in rows])
