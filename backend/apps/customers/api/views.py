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


class CustomerLoginLinkView(TenantAPIView):
    """Front desk: after checking the customer in person, issue a one-time app login link (15 minutes)."""
    required_permissions = {"POST": "customers.manage"}

    @extend_schema(request=None, responses={201: dict})
    def post(self, request, pk):
        import hashlib
        import secrets
        from datetime import timedelta

        from django.utils import timezone

        from apps.audit.services.log import record as audit
        from apps.customers.models import CustomerLoginLink
        from apps.platform.models import TenantDomain
        customer = get_object_or_404(Customer.objects.all(), pk=pk)
        raw = secrets.token_urlsafe(24)
        CustomerLoginLink.objects.create(customer=customer, token_hash=hashlib.sha256(raw.encode()).hexdigest(),
                                         issued_by=request.user, expires_at=timezone.now() + timedelta(minutes=15))
        host = (TenantDomain.objects.filter(tenant_id=request.tenant_id, is_active=True).order_by("-kind").values_list("host", flat=True).first())
        audit("customer.login_link_issued", tenant_id=request.tenant_id, actor=request.user, obj=customer)
        return Response({"url": f"https://{host}/?login={raw}" if host else None, "token": raw, "expires_in": 900},
                        status=status.HTTP_201_CREATED)
