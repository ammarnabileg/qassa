"""Phase 5 API: expenses, fixed assets, depreciation, clearing settlements, statements, periods and year close,
frozen report versions."""
from datetime import date

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.accounting.models import Account, ClearingSettlement, Expense, FiscalPeriod, FiscalYear, FixedAsset, ReportVersion
from apps.accounting.services import finance
from apps.core.errors import DomainError
from apps.core.services.infra import idempotent
from apps.tenancy.api.base import TenantAPIView
from apps.tenancy.models import Branch, LegalEntity


def _entity(request):
    return get_object_or_404(LegalEntity.objects.all(), pk=request.query_params.get("legal_entity_id") or 0)


def _date(v, name="date"):
    try:
        return date.fromisoformat(v)
    except (TypeError, ValueError):
        raise DomainError(f"{name} must be YYYY-MM-DD", code="bad_dates")


def _company_wide(request):
    if request.membership.branch_ids() is not None:
        raise DomainError("Company-wide statements need access to all branches", code="all_branches_required")


def _branch(request, branch_id):
    if not branch_id:
        return None
    b = get_object_or_404(Branch.objects.all(), pk=branch_id)
    allowed = request.membership.branch_ids()
    if allowed is not None and b.id not in allowed:
        raise DomainError(code="branch_forbidden")
    return b


# ---------- expenses ----------
class ExpenseOut(serializers.ModelSerializer):
    account_code = serializers.CharField(source="account.code")
    account_name_ar = serializers.CharField(source="account.name_ar")
    account_name_en = serializers.CharField(source="account.name_en")

    class Meta:
        model = Expense
        fields = ["id", "branch", "expense_date", "account", "account_code", "account_name_ar", "account_name_en", "description",
                  "amount", "paid_from", "reference", "paid_on", "paid_reference", "created_at"]


class ExpenseIn(serializers.Serializer):
    branch_id = serializers.IntegerField(required=False, allow_null=True)
    expense_date = serializers.DateField()
    account_id = serializers.IntegerField()
    description = serializers.CharField(max_length=200)
    amount = serializers.DecimalField(max_digits=18, decimal_places=3)
    paid_from = serializers.ChoiceField(choices=Expense.PaidFrom.choices)
    reference = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")


class ExpensesView(TenantAPIView):
    required_permissions = {"GET": "accounting.view", "POST": "accounting.journal.post"}

    @extend_schema(parameters=[OpenApiParameter("legal_entity_id", int, required=True)], responses=ExpenseOut(many=True))
    def get(self, request):
        qs = Expense.objects.filter(legal_entity=_entity(request)).select_related("account")
        allowed = request.membership.branch_ids()
        if allowed is not None:
            qs = qs.filter(branch_id__in=allowed)
        return Response(ExpenseOut(qs[:300], many=True).data)

    @extend_schema(parameters=[OpenApiParameter("legal_entity_id", int, required=True)], request=ExpenseIn, responses={201: ExpenseOut})
    @idempotent
    def post(self, request):
        s = ExpenseIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        entity = _entity(request)
        e = finance.record_expense(entity=entity, branch=_branch(request, v.get("branch_id")), expense_date=v["expense_date"],
                                   account=get_object_or_404(Account.objects.filter(legal_entity=entity), pk=v["account_id"]),
                                   amount=v["amount"], paid_from=v["paid_from"], description=v["description"],
                                   reference=v["reference"], user=request.user)
        return Response(ExpenseOut(e).data, status=status.HTTP_201_CREATED)


class PayIn(serializers.Serializer):
    paid_on = serializers.DateField()
    reference = serializers.CharField(max_length=80)


class ExpensePayView(TenantAPIView):
    required_permissions = {"POST": "accounting.journal.post"}

    @extend_schema(request=PayIn, responses=ExpenseOut)
    @idempotent
    def post(self, request, pk):
        s = PayIn(data=request.data)
        s.is_valid(raise_exception=True)
        e = finance.pay_accrued(get_object_or_404(Expense.objects.all(), pk=pk), user=request.user, **s.validated_data)
        return Response(ExpenseOut(Expense.objects.select_related("account").get(id=e.id)).data)


# ---------- fixed assets ----------
class AssetIn(serializers.Serializer):
    branch_id = serializers.IntegerField(required=False, allow_null=True)
    name = serializers.CharField(max_length=150)
    acquired_on = serializers.DateField()
    cost = serializers.DecimalField(max_digits=18, decimal_places=3)
    residual_value = serializers.DecimalField(max_digits=18, decimal_places=3, required=False, default=0)
    life_months = serializers.IntegerField(min_value=1, max_value=600)
    paid_from = serializers.ChoiceField(choices=["bank", "payable"])
    reference = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")


def _asset_out(a: FixedAsset, today: date):
    acc = finance.accumulated(a, today)
    return {"id": a.id, "name": a.name, "branch": a.branch_id, "acquired_on": a.acquired_on.isoformat(), "cost": str(a.cost),
            "residual_value": str(a.residual_value), "life_months": a.life_months, "paid_from": a.paid_from,
            "reference": a.reference, "monthly": str(finance._q3((a.cost - a.residual_value) / a.life_months)),
            "accumulated": str(acc), "book_value": str(a.cost - acc)}


class AssetsView(TenantAPIView):
    required_permissions = {"GET": "accounting.view", "POST": "accounting.journal.post"}

    @extend_schema(parameters=[OpenApiParameter("legal_entity_id", int, required=True)], responses=dict)
    def get(self, request):
        from apps.core.dates import business_date
        today = business_date()
        return Response([_asset_out(a, today) for a in FixedAsset.objects.filter(legal_entity=_entity(request))])

    @extend_schema(parameters=[OpenApiParameter("legal_entity_id", int, required=True)], request=AssetIn, responses={201: dict})
    @idempotent
    def post(self, request):
        from apps.core.dates import business_date
        s = AssetIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = dict(s.validated_data)
        branch = _branch(request, v.pop("branch_id", None))
        a = finance.add_asset(entity=_entity(request), branch=branch, user=request.user, **v)
        return Response(_asset_out(a, business_date()), status=status.HTTP_201_CREATED)


class DepreciationIn(serializers.Serializer):
    month = serializers.RegexField(r"^\d{4}-\d{2}$")


class DepreciationView(TenantAPIView):
    required_permissions = {"POST": "accounting.journal.post"}

    @extend_schema(parameters=[OpenApiParameter("legal_entity_id", int, required=True)], request=DepreciationIn, responses=dict)
    def post(self, request):
        s = DepreciationIn(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(finance.run_depreciation(_entity(request), _date(s.validated_data["month"] + "-01", "month"), request.user))


# ---------- clearing settlements ----------
class SettlementIn(serializers.Serializer):
    channel = serializers.ChoiceField(choices=["knet", "gateway"])
    settled_on = serializers.DateField()
    gross = serializers.DecimalField(max_digits=18, decimal_places=3)
    fees = serializers.DecimalField(max_digits=18, decimal_places=3, required=False, default=0)
    reference = serializers.CharField(max_length=80)


class SettlementsView(TenantAPIView):
    required_permissions = {"GET": "accounting.view", "POST": "accounting.journal.post"}

    @extend_schema(parameters=[OpenApiParameter("legal_entity_id", int, required=True)], responses=dict)
    def get(self, request):
        entity = _entity(request)
        rows = [{"id": s.id, "channel": s.channel, "settled_on": s.settled_on, "gross": str(s.gross), "fees": str(s.fees),
                 "net": str(s.gross - s.fees), "reference": s.reference} for s in ClearingSettlement.objects.filter(legal_entity=entity)[:200]]
        return Response({"status": finance.clearing_status(entity), "settlements": rows})

    @extend_schema(parameters=[OpenApiParameter("legal_entity_id", int, required=True)], request=SettlementIn, responses={201: dict})
    @idempotent
    def post(self, request):
        from django.db import IntegrityError
        s = SettlementIn(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            st = finance.settle_clearing(entity=_entity(request), user=request.user, **s.validated_data)
        except IntegrityError:
            raise DomainError(code="settlement_duplicate")
        return Response({"id": st.id}, status=status.HTTP_201_CREATED)


# ---------- statements ----------
class IncomeStatementView(TenantAPIView):
    required_permissions = {"GET": "accounting.view"}

    @extend_schema(parameters=[OpenApiParameter("legal_entity_id", int, required=True), OpenApiParameter("from", str, required=True),
                               OpenApiParameter("to", str, required=True), OpenApiParameter("branch_id", int)], responses=dict)
    def get(self, request):
        branch = _branch(request, request.query_params.get("branch_id"))
        if branch is None:
            _company_wide(request)
        return Response(finance.income_statement(_entity(request), _date(request.query_params.get("from"), "from"),
                                                 _date(request.query_params.get("to"), "to"), branch.id if branch else None))


class BalanceSheetView(TenantAPIView):
    required_permissions = {"GET": "accounting.view"}

    @extend_schema(parameters=[OpenApiParameter("legal_entity_id", int, required=True), OpenApiParameter("as_of", str, required=True)], responses=dict)
    def get(self, request):
        _company_wide(request)
        return Response(finance.balance_sheet(_entity(request), _date(request.query_params.get("as_of"), "as_of")))


# ---------- periods and year close ----------
class PeriodsView(TenantAPIView):
    required_permissions = {"GET": "accounting.view"}

    @extend_schema(parameters=[OpenApiParameter("legal_entity_id", int, required=True)], responses=dict)
    def get(self, request):
        entity = _entity(request)
        out = []
        for fy in FiscalYear.objects.filter(legal_entity=entity).order_by("-start_date"):
            from apps.accounting.models import JournalEntry
            out.append({"id": fy.id, "name": fy.name, "start_date": fy.start_date, "end_date": fy.end_date,
                        "closing_entry": JournalEntry.objects.filter(source_type=finance.CLOSING, source_id=str(fy.id))
                        .values_list("number", flat=True).first(),
                        "periods": [{"id": p.id, "number": p.number, "start_date": p.start_date, "end_date": p.end_date,
                                     "status": p.status, "closed_at": p.closed_at}
                                    for p in FiscalPeriod.objects.filter(fiscal_year=fy).order_by("number")]})
        return Response(out)


class YearCloseView(TenantAPIView):
    required_permissions = {"POST": "accounting.period.close"}

    @extend_schema(request=None, responses=dict)
    def post(self, request, pk):
        je = finance.close_year(get_object_or_404(FiscalYear.objects.all(), pk=pk), request.user)
        return Response({"entry": je.number}, status=status.HTTP_201_CREATED)


# ---------- frozen report versions ----------
class FreezeIn(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["income_statement", "balance_sheet", "xbrl"])
    params = serializers.DictField()
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class ReportVersionsView(TenantAPIView):
    """POST regenerates the report on the server (the client never sends figures) and freezes it."""
    required_permissions = {"GET": "accounting.view", "POST": "accounting.journal.post"}

    @extend_schema(operation_id="v1_accounting_report_versions_list",
                   parameters=[OpenApiParameter("legal_entity_id", int, required=True)], responses=dict)
    def get(self, request):
        return Response([{"id": r.id, "kind": r.kind, "params": r.params, "note": r.note, "sha256": r.sha256,
                          "created_at": r.created_at, "created_by": r.created_by.full_name or r.created_by.email}
                         for r in ReportVersion.objects.filter(legal_entity=_entity(request)).select_related("created_by")[:200]])

    @extend_schema(parameters=[OpenApiParameter("legal_entity_id", int, required=True)], request=FreezeIn, responses={201: dict})
    def post(self, request):
        from apps.accounting.services import xbrl
        _company_wide(request)
        s = FreezeIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        entity, p = _entity(request), v["params"]
        if v["kind"] == "income_statement":
            params = {"from": p.get("from"), "to": p.get("to")}
            data = finance.income_statement(entity, _date(params["from"], "from"), _date(params["to"], "to"))
        elif v["kind"] == "balance_sheet":
            params = {"as_of": p.get("as_of")}
            data = finance.balance_sheet(entity, _date(params["as_of"], "as_of"))
        else:
            params = {"year_end": p.get("year_end")}
            data = xbrl.report(entity, _date(params["year_end"], "year_end"))
        rv = finance.freeze(entity=entity, kind=v["kind"], params=params, data=data, note=v["note"], user=request.user)
        return Response({"id": rv.id, "sha256": rv.sha256}, status=status.HTTP_201_CREATED)


class ReportVersionDetailView(TenantAPIView):
    required_permissions = {"GET": "accounting.view"}

    @extend_schema(responses=dict)
    def get(self, request, pk):
        rv = get_object_or_404(ReportVersion.objects.select_related("created_by"), pk=pk)
        return Response({"id": rv.id, "kind": rv.kind, "params": rv.params, "data": rv.data, "sha256": rv.sha256,
                         "intact": finance.verify(rv), "note": rv.note, "created_at": rv.created_at,
                         "created_by": rv.created_by.full_name or rv.created_by.email})
