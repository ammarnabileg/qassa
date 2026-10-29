from datetime import date

from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_field, inline_serializer
from rest_framework import serializers, status
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from apps.accounting.models import Account, FiscalPeriod, JournalEntry
from apps.accounting.services.ledger import close_period, reopen_period, trial_balance
from apps.accounting.services.posting import Line, post_entry, reverse_entry
from apps.core.errors import DomainError
from apps.core.services.infra import idempotent
from apps.tenancy.api.base import TenantAPIView
from apps.tenancy.models import LegalEntity


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = ["id", "legal_entity", "code", "name_ar", "name_en", "type", "parent", "is_postable", "is_control",
                  "is_active"]


class LineIn(serializers.Serializer):
    account_id = serializers.IntegerField()
    debit = serializers.DecimalField(max_digits=18, decimal_places=3, min_value=0, default="0")
    credit = serializers.DecimalField(max_digits=18, decimal_places=3, min_value=0, default="0")
    description = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    branch_id = serializers.IntegerField(required=False, allow_null=True)


class EntryIn(serializers.Serializer):
    legal_entity_id = serializers.IntegerField()
    entry_date = serializers.DateField()
    memo = serializers.CharField(required=False, allow_blank=True, default="")
    branch_id = serializers.IntegerField(required=False, allow_null=True)
    lines = LineIn(many=True)


class LineOut(serializers.Serializer):
    line_no = serializers.IntegerField()
    account_id = serializers.IntegerField()
    account_code = serializers.CharField(source="account.code")
    debit = serializers.DecimalField(max_digits=18, decimal_places=3)
    credit = serializers.DecimalField(max_digits=18, decimal_places=3)
    description = serializers.CharField()
    branch_id = serializers.IntegerField(allow_null=True)


class EntryOut(serializers.ModelSerializer):
    lines = LineOut(many=True)
    reversed_by_id = serializers.SerializerMethodField()

    class Meta:
        model = JournalEntry
        fields = ["id", "number", "legal_entity", "branch", "entry_date", "status", "kind", "memo", "source_type",
                  "source_id", "event_type", "reversal_of", "reversed_by_id", "posted_at", "lines"]

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_reversed_by_id(self, obj):
        rev = getattr(obj, "reversed_by", None) if hasattr(obj, "reversed_by") else None
        return rev.id if rev else None


def _entity(request, entity_id):
    return get_object_or_404(LegalEntity.objects.all(), pk=entity_id)  # scoped manager → 404 for other tenants


def _check_branch(request, branch_id):
    allowed = request.membership.branch_ids()
    if branch_id and allowed is not None and branch_id not in allowed:
        raise DomainError("No access to this branch", code="branch_forbidden")


class AccountListView(TenantAPIView):
    required_permissions = {"GET": "accounting.view"}

    @extend_schema(parameters=[OpenApiParameter("legal_entity_id", int, required=True)],
                   responses=AccountSerializer(many=True))
    def get(self, request):
        entity = _entity(request, request.query_params.get("legal_entity_id") or 0)
        return Response(AccountSerializer(Account.objects.filter(legal_entity=entity), many=True).data)


class JournalEntryListCreateView(TenantAPIView):
    required_permissions = {"GET": "accounting.view", "POST": "accounting.journal.post"}

    @extend_schema(parameters=[OpenApiParameter("legal_entity_id", int, required=True)], responses=EntryOut(many=True))
    def get(self, request):
        entity = _entity(request, request.query_params.get("legal_entity_id") or 0)
        qs = (JournalEntry.objects.filter(legal_entity=entity).select_related("reversed_by")
              .prefetch_related("lines__account").order_by("-entry_date", "-id")[:200])
        return Response(EntryOut(qs, many=True).data)

    @extend_schema(request=EntryIn, responses=EntryOut)
    @idempotent
    def post(self, request):
        s = EntryIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        entity = _entity(request, v["legal_entity_id"])
        _check_branch(request, v.get("branch_id"))
        accounts = {a.id: a for a in Account.objects.filter(legal_entity=entity,
                                                            id__in=[l["account_id"] for l in v["lines"]])}
        lines = []
        for i, l in enumerate(v["lines"], start=1):
            if l["account_id"] not in accounts:
                raise DomainError("Unknown account", code="je_unknown_account", details={"line": i})
            _check_branch(request, l.get("branch_id"))
            lines.append(Line(account=accounts[l["account_id"]], debit=l["debit"], credit=l["credit"],
                              description=l["description"], branch_id=l.get("branch_id")))
        entry = post_entry(legal_entity_id=entity.id, entry_date=v["entry_date"], lines=lines, memo=v["memo"],
                           user=request.user, branch_id=v.get("branch_id"), kind="manual")
        return Response(EntryOut(entry).data, status=status.HTTP_201_CREATED)


class ReverseIn(serializers.Serializer):
    on = serializers.DateField(required=False)
    reason = serializers.CharField(min_length=3)


class JournalEntryReverseView(TenantAPIView):
    required_permissions = {"POST": "accounting.journal.reverse"}

    @extend_schema(request=ReverseIn, responses=EntryOut)
    @idempotent
    def post(self, request, pk):
        entry = get_object_or_404(JournalEntry.objects.all(), pk=pk)
        s = ReverseIn(data=request.data)
        s.is_valid(raise_exception=True)
        rev = reverse_entry(entry, on=s.validated_data.get("on") or date.today(), user=request.user,
                            reason=s.validated_data["reason"])
        return Response(EntryOut(rev).data, status=status.HTTP_201_CREATED)


class TrialBalanceView(TenantAPIView):
    required_permissions = {"GET": "accounting.view"}

    @extend_schema(parameters=[OpenApiParameter("legal_entity_id", int, required=True),
                               OpenApiParameter("from", str, required=True), OpenApiParameter("to", str, required=True),
                               OpenApiParameter("branch_id", int)],
                   responses=inline_serializer("TrialBalance", {
                       "rows": inline_serializer("TBRow", {"account_id": serializers.IntegerField(), "code": serializers.CharField(),
                           "name_ar": serializers.CharField(), "name_en": serializers.CharField(), "type": serializers.CharField(),
                           "opening": serializers.DecimalField(18, 3), "debit": serializers.DecimalField(18, 3),
                           "credit": serializers.DecimalField(18, 3), "closing": serializers.DecimalField(18, 3),
                           "normal_side": serializers.CharField()}, many=True),
                       "total_debit": serializers.DecimalField(18, 3), "total_credit": serializers.DecimalField(18, 3),
                       "balanced": serializers.BooleanField()}))
    def get(self, request):
        entity = _entity(request, request.query_params.get("legal_entity_id") or 0)
        try:
            d_from = date.fromisoformat(request.query_params["from"])
            d_to = date.fromisoformat(request.query_params["to"])
        except (KeyError, ValueError):
            raise DomainError("from/to dates are required (YYYY-MM-DD)", code="bad_dates")
        branch_id = request.query_params.get("branch_id")
        branch_id = int(branch_id) if branch_id else None
        _check_branch(request, branch_id)
        if branch_id is None and request.membership.branch_ids() is not None:
            raise DomainError("Choose one of your branches", code="branch_required")
        tb = trial_balance(entity.id, d_from, d_to, branch_id)
        for r in tb["rows"]:
            for k in ("opening", "debit", "credit", "closing"):
                r[k] = str(r[k])
        tb["total_debit"], tb["total_credit"] = str(tb["total_debit"]), str(tb["total_credit"])
        return Response(tb)


class PeriodActionIn(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")


def _open_drawers(period):
    """A period cannot close while a cash drawer opened in it is still open or awaiting variance approval."""
    import datetime

    from django.utils import timezone

    from apps.pos.models import CashSession
    end = timezone.make_aware(datetime.datetime.combine(period.end_date + datetime.timedelta(days=1), datetime.time(4)))
    from django.db.models import Q
    n = (CashSession.objects.filter(branch__legal_entity_id=period.legal_entity_id, opened_at__lt=end)
         .filter(Q(status="open") | Q(variance_status="pending")).count())
    return f"{n} cash drawer(s) still open or awaiting approval" if n else None


class PeriodCloseView(TenantAPIView):
    required_permissions = {"POST": "accounting.period.close"}

    @extend_schema(request=PeriodActionIn, responses=inline_serializer("PeriodStatus", {"id": serializers.IntegerField(), "status": serializers.CharField()}))
    def post(self, request, pk, action):
        period = get_object_or_404(FiscalPeriod.objects.all(), pk=pk)
        s = PeriodActionIn(data=request.data)
        s.is_valid(raise_exception=True)
        if action == "close":
            p = close_period(period, request.user, pending_checks=[_open_drawers])
        elif action == "reopen":
            p = reopen_period(period, request.user, s.validated_data["reason"])
        else:
            raise DomainError("Unknown action", code="bad_action")
        return Response({"id": p.id, "status": p.status})


class XbrlReportView(TenantAPIView):
    """MOCI annual statements in the template's order (draft from the ledger, for the accountant to transfer)."""
    required_permissions = {"GET": "accounting.view"}

    @extend_schema(parameters=[OpenApiParameter("legal_entity_id", int, required=True),
                               OpenApiParameter("year_end", str, required=True)], responses=dict)
    def get(self, request):
        from apps.accounting.services import xbrl
        if request.membership.branch_ids() is not None:
            raise DomainError("Company-wide statements need access to all branches", code="all_branches_required")
        entity = _entity(request, request.query_params.get("legal_entity_id") or 0)
        try:
            year_end = date.fromisoformat(request.query_params["year_end"])
        except (KeyError, ValueError):
            raise DomainError("year_end is required (YYYY-MM-DD)", code="bad_dates")
        return Response(xbrl.report(entity, year_end))


class XbrlMappingIn(serializers.Serializer):
    account_id = serializers.IntegerField()
    tag = serializers.CharField(max_length=200, allow_blank=True)


class XbrlMappingView(TenantAPIView):
    """Which MOCI line each account goes to. PUT with an empty tag returns the account to its default."""
    required_permissions = {"GET": "accounting.view", "PUT": "accounting.setup"}

    @extend_schema(parameters=[OpenApiParameter("legal_entity_id", int, required=True)], responses=dict)
    def get(self, request):
        from apps.accounting.models import XbrlMapping
        from apps.accounting.services import xbrl
        entity = _entity(request, request.query_params.get("legal_entity_id") or 0)
        tags = xbrl.mapping(entity.id)
        custom = set(XbrlMapping.objects.filter(legal_entity=entity).values_list("account_id", flat=True))
        accounts = [{"account_id": a.id, "code": a.code, "name_ar": a.name_ar, "name_en": a.name_en, "type": a.type,
                     "tag": tags.get(a.id), "custom": a.id in custom}
                    for a in Account.objects.filter(legal_entity=entity, is_postable=True).order_by("code")]
        lines = [{"statement": c["statement"], "section": c["section"], "tag": c["tag"], "label_ar": c["label_ar"]}
                 for c in xbrl.CATALOG if c["statement"] in ("fp", "pl")]
        return Response({"accounts": accounts, "lines": lines})

    @extend_schema(parameters=[OpenApiParameter("legal_entity_id", int, required=True)], request=XbrlMappingIn, responses=dict)
    def put(self, request):
        from apps.accounting.models import XbrlMapping
        from apps.accounting.services import xbrl
        from apps.audit.services.log import record as audit
        entity = _entity(request, request.query_params.get("legal_entity_id") or 0)
        s = XbrlMappingIn(data=request.data)
        s.is_valid(raise_exception=True)
        acc = get_object_or_404(Account.objects.filter(legal_entity=entity, is_postable=True), pk=s.validated_data["account_id"])
        tag = s.validated_data["tag"]
        if not tag:
            XbrlMapping.objects.filter(legal_entity=entity, account=acc).delete()
        else:
            statement = "fp" if acc.type in xbrl.FP_TYPES else "pl"
            if (statement, tag) not in xbrl.TAGS:
                raise DomainError("This line does not belong to the account's statement", code="xbrl_tag_invalid")
            XbrlMapping.objects.update_or_create(legal_entity=entity, account=acc, defaults={"tag": tag})
        audit("accounting.xbrl_mapping", tenant_id=request.tenant_id, actor=request.user, obj=acc, data={"tag": tag})
        return self.get(request)
