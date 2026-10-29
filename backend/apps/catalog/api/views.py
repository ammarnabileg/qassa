from datetime import date

from django.db import IntegrityError, transaction
from django.db.models import Prefetch, Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.catalog.models import Service, ServiceCategory, ServicePrice
from apps.catalog.services.pricing import set_price
from apps.core.dates import business_date
from apps.core.errors import DomainError
from apps.core.services.infra import idempotent
from apps.tenancy.api.base import TenantAPIView
from apps.tenancy.models import Branch


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceCategory
        fields = ["id", "name_ar", "name_en", "business_type", "sort"]
        validators = []  # duplicate names are reported as category_name_exists by the view


class PriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServicePrice
        fields = ["id", "branch", "price", "valid_from", "valid_to"]


class ServiceSerializer(serializers.ModelSerializer):
    current_price = serializers.SerializerMethodField()
    business_type = serializers.CharField(source="category.business_type", read_only=True)

    class Meta:
        model = Service
        fields = ["id", "category", "business_type", "name_ar", "name_en", "duration_minutes", "home_visit",
                  "is_active", "current_price"]
        validators = []  # duplicate names are reported as service_name_exists by the view

    def get_current_price(self, obj) -> str | None:
        """Company default price valid today (branch overrides are listed under /prices)."""
        today = self.context["today"]
        for p in obj.prices.all():
            if p.branch_id is None and p.valid_from <= today and (p.valid_to is None or p.valid_to > today):
                return str(p.price)
        return None

    def validate_category(self, value):
        if not ServiceCategory.objects.filter(id=value.id).exists():  # scoped: other tenants' rows are invisible
            raise serializers.ValidationError("unknown category")
        return value


class ServiceIn(ServiceSerializer):
    price = serializers.DecimalField(max_digits=18, decimal_places=3, min_value=0, write_only=True, required=False)

    class Meta(ServiceSerializer.Meta):
        fields = ServiceSerializer.Meta.fields + ["price"]


class PriceIn(serializers.Serializer):
    price = serializers.DecimalField(max_digits=18, decimal_places=3, min_value=0)
    branch_id = serializers.IntegerField(required=False, allow_null=True)
    valid_from = serializers.DateField(required=False)


class CategoriesView(TenantAPIView):
    required_permissions = {"GET": "catalog.view", "POST": "catalog.manage"}

    @extend_schema(responses=CategorySerializer(many=True))
    def get(self, request):
        return Response(CategorySerializer(ServiceCategory.objects.order_by("business_type", "sort", "id"), many=True).data)

    @extend_schema(request=CategorySerializer, responses={201: CategorySerializer})
    def post(self, request):
        s = CategorySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                cat = s.save()
        except IntegrityError:
            raise DomainError(code="category_name_exists")
        return Response(CategorySerializer(cat).data, status=status.HTTP_201_CREATED)


def _services():
    return Service.objects.select_related("category").prefetch_related(
        Prefetch("prices", queryset=ServicePrice.objects.all())).order_by("category__sort", "id")


class ServicesView(TenantAPIView):
    required_permissions = {"GET": "catalog.view", "POST": "catalog.manage"}

    @extend_schema(parameters=[OpenApiParameter("business_type", str), OpenApiParameter("q", str)],
                   responses=ServiceSerializer(many=True))
    def get(self, request):
        qs = _services()
        if bt := request.query_params.get("business_type"):
            qs = qs.filter(category__business_type=bt)
        if q := request.query_params.get("q"):
            qs = qs.filter(Q(name_ar__icontains=q) | Q(name_en__icontains=q))
        return Response(ServiceSerializer(qs, many=True, context={"today": business_date()}).data)

    @extend_schema(request=ServiceIn, responses={201: ServiceSerializer})
    def post(self, request):
        s = ServiceIn(data=request.data, context={"today": business_date()})
        s.is_valid(raise_exception=True)
        price = s.validated_data.pop("price", None)
        try:
            with transaction.atomic():
                service = s.save()
        except IntegrityError:
            raise DomainError(code="service_name_exists")
        if price is not None:
            if not request.membership.has_perm("catalog.price.change"):
                raise DomainError(code="permission_price_change")
            set_price(service, price=price, user=request.user)
        return Response(ServiceSerializer(_services().get(id=service.id), context={"today": business_date()}).data,
                        status=status.HTTP_201_CREATED)


class ServiceDetailView(TenantAPIView):
    required_permissions = {"PATCH": "catalog.manage"}

    @extend_schema(request=ServiceSerializer, responses=ServiceSerializer)
    def patch(self, request, pk):
        service = get_object_or_404(Service.objects.all(), pk=pk)
        s = ServiceSerializer(service, data=request.data, partial=True, context={"today": business_date()})
        s.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                s.save()
        except IntegrityError:
            raise DomainError(code="service_name_exists")
        return Response(ServiceSerializer(_services().get(id=pk), context={"today": business_date()}).data)


class ServicePricesView(TenantAPIView):
    required_permissions = {"GET": "catalog.view", "POST": "catalog.price.change"}

    @extend_schema(responses=PriceSerializer(many=True))
    def get(self, request, pk):
        service = get_object_or_404(Service.objects.all(), pk=pk)
        return Response(PriceSerializer(service.prices.order_by("branch_id", "-valid_from"), many=True).data)

    @extend_schema(request=PriceIn, responses={201: PriceSerializer})
    @idempotent
    def post(self, request, pk):
        service = get_object_or_404(Service.objects.all(), pk=pk)
        s = PriceIn(data=request.data)
        s.is_valid(raise_exception=True)
        branch_id = s.validated_data.get("branch_id")
        if branch_id is not None and not Branch.objects.filter(id=branch_id).exists():
            raise DomainError(code="branch_unknown")
        row = set_price(service, price=s.validated_data["price"], branch_id=branch_id,
                        valid_from=s.validated_data.get("valid_from"), user=request.user)
        return Response(PriceSerializer(row).data, status=status.HTTP_201_CREATED)
