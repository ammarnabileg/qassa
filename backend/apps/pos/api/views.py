from datetime import date

from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.core.dates import business_date
from apps.core.services.infra import idempotent
from apps.pos.models import CashSession, Invoice
from apps.pos.services import sales
from apps.tenancy.api.base import TenantAPIView, branch_for

AMOUNT = dict(max_digits=18, decimal_places=3)


class SessionOut(serializers.ModelSerializer):
    expected_now = serializers.SerializerMethodField()

    class Meta:
        model = CashSession
        fields = ["id", "branch", "status", "opened_by", "opened_at", "opening_float", "closed_by", "closed_at",
                  "expected_cash", "counted_cash", "denominations", "variance", "variance_status", "variance_approved_by", "notes",
                  "expected_now"]

    def get_expected_now(self, obj) -> str | None:
        return str(sales.expected_cash(obj)) if obj.status == CashSession.Status.OPEN else None


class OpenIn(serializers.Serializer):
    branch_id = serializers.IntegerField()
    opening_float = serializers.DecimalField(**AMOUNT, min_value=0)


class CloseIn(serializers.Serializer):
    counted_cash = serializers.DecimalField(**AMOUNT, min_value=0, required=False, allow_null=True)
    denominations = serializers.DictField(child=serializers.IntegerField(min_value=0), required=False, default=dict)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class SessionsView(TenantAPIView):
    required_permissions = {"GET": "cash.session.open", "POST": "cash.session.open"}

    @extend_schema(parameters=[OpenApiParameter("branch_id", int, required=True)], responses=SessionOut(many=True))
    def get(self, request):
        branch = branch_for(request, request.query_params.get("branch_id"))
        return Response(SessionOut(CashSession.objects.filter(branch=branch).order_by("-id")[:30], many=True).data)

    @extend_schema(request=OpenIn, responses={201: SessionOut})
    def post(self, request):
        s = OpenIn(data=request.data)
        s.is_valid(raise_exception=True)
        session = sales.open_session(branch_for(request, s.validated_data["branch_id"]), s.validated_data["opening_float"], request.user)
        return Response(SessionOut(session).data, status=status.HTTP_201_CREATED)


class SessionCloseView(TenantAPIView):
    required_permissions = {"POST": "cash.session.open"}

    @extend_schema(request=CloseIn, responses=SessionOut)
    def post(self, request, pk):
        session = get_object_or_404(CashSession.objects.all(), pk=pk)
        branch_for(request, session.branch_id)
        s = CloseIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        return Response(SessionOut(sales.close_session(session, v.get("counted_cash"), request.user, v["notes"],
                                                       denominations=v["denominations"])).data)


class SessionApproveView(TenantAPIView):
    required_permissions = {"POST": "cash.variance.approve"}

    @extend_schema(request=None, responses=SessionOut)
    def post(self, request, pk):
        session = get_object_or_404(CashSession.objects.all(), pk=pk)
        branch_for(request, session.branch_id)
        return Response(SessionOut(sales.approve_variance(session, request.user, request.membership)).data)


class SaleLineIn(serializers.Serializer):
    service_id = serializers.IntegerField(required=False, allow_null=True)
    product_id = serializers.IntegerField(required=False, allow_null=True)
    package_plan_id = serializers.IntegerField(required=False, allow_null=True)
    redeem_package_id = serializers.IntegerField(required=False, allow_null=True)
    qty = serializers.IntegerField(min_value=1, max_value=50, default=1)
    discount = serializers.DecimalField(**AMOUNT, min_value=0, default="0")
    staff_id = serializers.IntegerField(required=False, allow_null=True)


class SalePaymentIn(serializers.Serializer):
    method = serializers.ChoiceField(choices=["cash", "knet", "transfer"])
    amount = serializers.DecimalField(**AMOUNT, min_value=0)
    reference = serializers.CharField(required=False, allow_blank=True, default="", max_length=60)


class CheckoutIn(serializers.Serializer):
    branch_id = serializers.IntegerField()
    lines = SaleLineIn(many=True)
    payments = SalePaymentIn(many=True, required=False, default=list)
    customer_id = serializers.IntegerField(required=False, allow_null=True)
    beneficiary_id = serializers.IntegerField(required=False, allow_null=True)
    appointment_id = serializers.IntegerField(required=False, allow_null=True)
    expected_total = serializers.DecimalField(**AMOUNT, required=False, allow_null=True)
    coupon_code = serializers.CharField(required=False, allow_blank=True, default="", max_length=30)
    redeem_points = serializers.IntegerField(required=False, min_value=0, default=0)
    tip = serializers.DecimalField(**AMOUNT, min_value=0, required=False, default="0")
    tip_staff_id = serializers.IntegerField(required=False, allow_null=True)

    def validate_lines(self, lines):
        for ln in lines:
            if sum(1 for k in ("service_id", "product_id", "package_plan_id") if ln.get(k)) != 1:
                raise serializers.ValidationError("each line needs exactly one of service_id, product_id, package_plan_id")
        return lines


class InvoiceLineOut(serializers.Serializer):
    id = serializers.IntegerField()
    kind = serializers.CharField()
    service_id = serializers.IntegerField(allow_null=True)
    product_id = serializers.IntegerField(allow_null=True)
    redeemed_package_id = serializers.IntegerField(allow_null=True)
    staff_id = serializers.IntegerField(allow_null=True)
    name_ar = serializers.CharField()
    name_en = serializers.CharField()
    qty = serializers.IntegerField()
    unit_price = serializers.DecimalField(**AMOUNT)
    discount = serializers.DecimalField(**AMOUNT)
    line_total = serializers.DecimalField(**AMOUNT)
    returned = serializers.SerializerMethodField()

    def get_returned(self, obj) -> str:
        return str(sum((c.amount for c in obj.credit_lines.all()), 0))


class PaymentOut(serializers.Serializer):
    id = serializers.IntegerField()
    direction = serializers.CharField()
    method = serializers.CharField()
    amount = serializers.DecimalField(**AMOUNT)
    reference = serializers.CharField()
    received_at = serializers.DateTimeField()
    credit_note_id = serializers.IntegerField(allow_null=True)


class CreditNoteOut(serializers.Serializer):
    id = serializers.IntegerField()
    number = serializers.CharField()
    reason = serializers.CharField()
    total = serializers.DecimalField(**AMOUNT)
    issued_at = serializers.DateTimeField()


class InvoiceOut(serializers.ModelSerializer):
    lines = InvoiceLineOut(many=True)
    payments = PaymentOut(many=True)
    credit_notes = CreditNoteOut(many=True)
    customer_name = serializers.SerializerMethodField()
    customer_phone = serializers.SerializerMethodField()
    beneficiary_name = serializers.SerializerMethodField()
    issued_by_name = serializers.SerializerMethodField()
    state = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = ["id", "number", "branch", "customer", "customer_name", "customer_phone", "beneficiary", "beneficiary_name",
                  "appointment", "subtotal", "discount_total", "total", "tip", "points_redeemed", "is_credit", "business_date", "issued_at",
                  "issued_by_name", "lines", "payments", "credit_notes", "state"]

    def get_customer_name(self, obj) -> str:
        return obj.customer.full_name if obj.customer_id else ""

    def get_customer_phone(self, obj) -> str:
        return obj.customer.phone if obj.customer_id else ""

    def get_beneficiary_name(self, obj) -> str:
        return obj.beneficiary.full_name if obj.beneficiary_id else ""

    def get_issued_by_name(self, obj) -> str:
        return obj.issued_by.full_name or obj.issued_by.email

    def get_state(self, obj) -> dict:
        return {k: str(v) for k, v in sales.invoice_state(obj).items()}


def _invoices():
    return Invoice.objects.select_related("customer", "beneficiary", "issued_by").prefetch_related(
        "lines__credit_lines", "payments", "credit_notes")


def _invoice(request, pk):
    inv = get_object_or_404(_invoices(), pk=pk)
    branch_for(request, inv.branch_id)
    return inv


class CheckoutView(TenantAPIView):
    required_permissions = {"POST": "pos.sell"}

    @extend_schema(request=CheckoutIn, responses={201: InvoiceOut})
    @idempotent
    def post(self, request):
        s = CheckoutIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        inv = sales.checkout(sales.CheckoutIn(
            branch=branch_for(request, v["branch_id"]), lines=[sales.LineIn(**x) for x in v["lines"]],
            payments=[sales.PaymentIn(**x) for x in v["payments"]], customer_id=v.get("customer_id"),
            beneficiary_id=v.get("beneficiary_id"), appointment_id=v.get("appointment_id"),
            expected_total=v.get("expected_total"), coupon_code=v["coupon_code"], redeem_points=v["redeem_points"],
            tip=v["tip"], tip_staff_id=v.get("tip_staff_id")), user=request.user, membership=request.membership)
        return Response(InvoiceOut(_invoices().get(id=inv.id)).data, status=status.HTTP_201_CREATED)


class QuoteView(TenantAPIView):
    required_permissions = {"POST": "pos.sell"}

    @extend_schema(request=CheckoutIn, responses=dict)
    def post(self, request):
        s = CheckoutIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        return Response(sales.quote(sales.CheckoutIn(
            branch=branch_for(request, v["branch_id"]), lines=[sales.LineIn(**x) for x in v["lines"]],
            customer_id=v.get("customer_id"), coupon_code=v["coupon_code"], redeem_points=v["redeem_points"])))


class InvoicesView(TenantAPIView):
    required_permissions = {"GET": "pos.invoices.view"}

    @extend_schema(parameters=[OpenApiParameter("branch_id", int), OpenApiParameter("date", str), OpenApiParameter("q", str),
                               OpenApiParameter("unpaid", bool)], responses=InvoiceOut(many=True))
    def get(self, request):
        qs = _invoices().order_by("-id")
        if request.query_params.get("branch_id"):
            qs = qs.filter(branch=branch_for(request, request.query_params["branch_id"]))
        else:
            allowed = request.membership.branch_ids()
            if allowed is not None:
                qs = qs.filter(branch_id__in=allowed)
        if q := request.query_params.get("q", "").strip():
            qs = qs.filter(Q(number__icontains=q) | Q(customer__full_name__icontains=q) | Q(customer__phone__contains=q))
        elif request.query_params.get("unpaid") == "true":
            qs = qs.filter(is_credit=True)
        else:
            day = date.fromisoformat(request.query_params["date"]) if request.query_params.get("date") else business_date()
            qs = qs.filter(business_date=day)
        return Response(InvoiceOut(qs[:200], many=True).data)


class InvoiceDetailView(TenantAPIView):
    required_permissions = {"GET": "pos.invoices.view"}

    @extend_schema(responses=InvoiceOut)
    def get(self, request, pk):
        return Response(InvoiceOut(_invoice(request, pk)).data)


class CollectIn(serializers.Serializer):
    payments = SalePaymentIn(many=True)


class InvoicePaymentsView(TenantAPIView):
    required_permissions = {"POST": "pos.sell"}

    @extend_schema(request=CollectIn, responses={201: InvoiceOut})
    @idempotent
    def post(self, request, pk):
        inv = _invoice(request, pk)
        s = CollectIn(data=request.data)
        s.is_valid(raise_exception=True)
        sales.collect(inv, [sales.PaymentIn(**x) for x in s.validated_data["payments"]], user=request.user)
        return Response(InvoiceOut(_invoices().get(id=pk)).data, status=status.HTTP_201_CREATED)


class ReturnLineIn(serializers.Serializer):
    invoice_line_id = serializers.IntegerField()
    amount = serializers.DecimalField(**AMOUNT, min_value=0)
    restock_qty = serializers.IntegerField(min_value=0, default=0)


class CreditNoteIn(serializers.Serializer):
    lines = ReturnLineIn(many=True)
    reason = serializers.CharField(max_length=300)
    refund = SalePaymentIn(required=False, allow_null=True)


class InvoiceCreditNotesView(TenantAPIView):
    required_permissions = {"POST": "pos.return"}

    @extend_schema(request=CreditNoteIn, responses={201: InvoiceOut})
    @idempotent
    def post(self, request, pk):
        inv = _invoice(request, pk)
        s = CreditNoteIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        refund = sales.PaymentIn(**v["refund"]) if v.get("refund") else None
        if refund and refund.method == "cash" and not request.membership.has_perm("pos.sell"):
            raise PermissionDenied("Cash refunds need POS access")
        sales.credit_note(inv, lines=[(x["invoice_line_id"], x["amount"], x["restock_qty"]) for x in v["lines"]], reason=v["reason"],
                          refund=refund, user=request.user)
        return Response(InvoiceOut(_invoices().get(id=pk)).data, status=status.HTTP_201_CREATED)
