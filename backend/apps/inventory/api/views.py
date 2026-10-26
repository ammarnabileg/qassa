from decimal import Decimal

from django.db import IntegrityError, transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.core.errors import DomainError
from apps.core.services.infra import idempotent
from apps.inventory.models import GoodsReceipt, Product, StockLevel, StockMove, Supplier, SupplierBill
from apps.inventory.services import purchasing
from apps.tenancy.api.base import TenantAPIView, branch_for


class ProductSerializer(serializers.ModelSerializer):
    stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ["id", "sku", "name_ar", "name_en", "kind", "unit", "sale_price", "is_active", "stock"]
        validators = []

    def get_stock(self, obj) -> dict:
        """Quantity (and average cost for people allowed to see costs) at the requested branch."""
        branch_id = self.context.get("branch_id")
        lvl = next((x for x in obj.levels.all() if x.branch_id == branch_id), None) if branch_id else None
        out = {"qty": str(lvl.qty if lvl else 0)}
        if self.context.get("show_cost"):
            out["avg_cost"] = str(lvl.avg_cost if lvl else 0)
        return out


class ProductsView(TenantAPIView):
    required_permissions = {"GET": "inventory.view", "POST": "inventory.purchase"}

    @extend_schema(parameters=[OpenApiParameter("branch_id", int)], responses=ProductSerializer(many=True))
    def get(self, request):
        branch_id = int(request.query_params["branch_id"]) if request.query_params.get("branch_id") else None
        if branch_id:
            branch_for(request, branch_id)
        qs = Product.objects.prefetch_related("levels").order_by("kind", "name_ar")
        return Response(ProductSerializer(qs, many=True, context={
            "branch_id": branch_id, "show_cost": request.membership.has_perm("report.view.cost_profit")}).data)

    @extend_schema(request=ProductSerializer, responses={201: ProductSerializer})
    def post(self, request):
        s = ProductSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                p = s.save()
        except IntegrityError:
            raise DomainError(code="sku_exists")
        return Response(ProductSerializer(p).data, status=status.HTTP_201_CREATED)


class ProductDetailView(TenantAPIView):
    required_permissions = {"PATCH": "inventory.purchase"}

    @extend_schema(request=ProductSerializer, responses=ProductSerializer)
    def patch(self, request, pk):
        p = get_object_or_404(Product.objects.all(), pk=pk)
        s = ProductSerializer(p, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                s.save()
        except IntegrityError:
            raise DomainError(code="sku_exists")
        return Response(ProductSerializer(p).data)


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "name", "phone", "is_active"]


class SuppliersView(TenantAPIView):
    required_permissions = {"GET": "inventory.view", "POST": "inventory.purchase"}

    @extend_schema(responses=SupplierSerializer(many=True))
    def get(self, request):
        return Response(SupplierSerializer(Supplier.objects.order_by("name"), many=True).data)

    @extend_schema(request=SupplierSerializer, responses={201: SupplierSerializer})
    def post(self, request):
        s = SupplierSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(SupplierSerializer(s.save()).data, status=status.HTTP_201_CREATED)


class GrnLineIn(serializers.Serializer):
    product_id = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=Decimal("0.001"))
    unit_cost = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=0)


class GrnIn(serializers.Serializer):
    branch_id = serializers.IntegerField()
    supplier_id = serializers.IntegerField()
    lines = GrnLineIn(many=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="", max_length=300)


class GrnOut(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name")
    lines = serializers.SerializerMethodField()
    bill = serializers.SerializerMethodField()

    class Meta:
        model = GoodsReceipt
        fields = ["id", "number", "branch", "supplier", "supplier_name", "received_on", "total", "notes", "lines", "bill"]

    def get_lines(self, obj) -> list[dict]:
        return [{"product_id": ln.product_id, "name_ar": ln.product.name_ar, "qty": str(ln.qty), "unit_cost": str(ln.unit_cost),
                 "line_total": str(ln.line_total)} for ln in obj.lines.all()]

    def get_bill(self, obj) -> dict | None:
        b = getattr(obj, "bill", None)
        return {"id": b.id, "supplier_ref": b.supplier_ref, "amount": str(b.amount), "due_date": b.due_date,
                "balance": str(purchasing.bill_balance(b))} if b else None


def _grns():
    return GoodsReceipt.objects.select_related("supplier", "bill").prefetch_related("lines__product").order_by("-id")


class ReceiptsView(TenantAPIView):
    required_permissions = {"GET": "inventory.view", "POST": "inventory.purchase"}

    @extend_schema(responses=GrnOut(many=True))
    def get(self, request):
        return Response(GrnOut(_grns()[:100], many=True).data)

    @extend_schema(request=GrnIn, responses={201: GrnOut})
    @idempotent
    def post(self, request):
        s = GrnIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        grn = purchasing.receive_goods(branch=branch_for(request, v["branch_id"]), supplier_id=v["supplier_id"], user=request.user,
                                       notes=v["notes"], lines=[purchasing.ReceiptLineIn(**x) for x in v["lines"]])
        return Response(GrnOut(_grns().get(id=grn.id)).data, status=status.HTTP_201_CREATED)


class BillIn(serializers.Serializer):
    supplier_ref = serializers.CharField(max_length=60)
    amount = serializers.DecimalField(max_digits=18, decimal_places=3, min_value=0)
    due_date = serializers.DateField(required=False, allow_null=True)


class ReceiptBillView(TenantAPIView):
    required_permissions = {"POST": "inventory.purchase"}

    @extend_schema(request=BillIn, responses={201: GrnOut})
    @idempotent
    def post(self, request, pk):
        grn = get_object_or_404(_grns(), pk=pk)
        s = BillIn(data=request.data)
        s.is_valid(raise_exception=True)
        purchasing.record_bill(receipt=grn, user=request.user, **s.validated_data)
        return Response(GrnOut(_grns().get(id=pk)).data, status=status.HTTP_201_CREATED)


class BillPayIn(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=18, decimal_places=3, min_value=0)
    reference = serializers.CharField(max_length=60)


class BillPaymentView(TenantAPIView):
    required_permissions = {"POST": "inventory.purchase"}

    @extend_schema(request=BillPayIn, responses={201: GrnOut})
    @idempotent
    def post(self, request, pk):
        bill = get_object_or_404(SupplierBill.objects.all(), pk=pk)
        s = BillPayIn(data=request.data)
        s.is_valid(raise_exception=True)
        purchasing.pay_bill(bill=bill, user=request.user, **s.validated_data)
        return Response(GrnOut(_grns().get(id=bill.receipt_id)).data, status=status.HTTP_201_CREATED)


class AdjustIn(serializers.Serializer):
    branch_id = serializers.IntegerField()
    product_id = serializers.IntegerField()
    qty_delta = serializers.DecimalField(max_digits=12, decimal_places=3)
    reason = serializers.CharField(max_length=200)


class AdjustView(TenantAPIView):
    required_permissions = {"POST": "inventory.adjust"}

    @extend_schema(request=AdjustIn, responses={201: dict})
    def post(self, request):
        s = AdjustIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        if v["qty_delta"] == 0:
            raise DomainError(code="stock_qty_invalid")
        move = purchasing.adjust(branch=branch_for(request, v["branch_id"]), product_id=v["product_id"], qty_delta=v["qty_delta"],
                                 reason=v["reason"], user=request.user)
        lvl = StockLevel.objects.get(branch_id=move.branch_id, product_id=move.product_id)
        return Response({"qty": str(lvl.qty)}, status=status.HTTP_201_CREATED)


class MovesView(TenantAPIView):
    required_permissions = {"GET": "inventory.view"}

    @extend_schema(parameters=[OpenApiParameter("branch_id", int, required=True), OpenApiParameter("product_id", int)], responses=dict)
    def get(self, request):
        branch = branch_for(request, request.query_params.get("branch_id"))
        qs = StockMove.objects.filter(branch=branch).select_related("product").order_by("-id")
        if request.query_params.get("product_id"):
            qs = qs.filter(product_id=request.query_params["product_id"])
        show_cost = request.membership.has_perm("report.view.cost_profit")
        return Response([{"id": m.id, "product": m.product.name_ar, "kind": m.kind, "qty": str(m.qty), "reason": m.reason,
                          "ref": m.source_type, "created_at": m.created_at, **({"value": str(m.value)} if show_cost else {})}
                         for m in qs[:200]])
