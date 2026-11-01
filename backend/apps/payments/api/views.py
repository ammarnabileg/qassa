"""Salon, public, webhook and platform endpoints for KlickPay online payments (D-017)."""
import json
import secrets

from django.conf import settings
from django.db.models import Count, Q, Sum
from django.http import FileResponse, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from drf_spectacular.utils import OpenApiTypes, extend_schema
from rest_framework import serializers
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services.log import record as audit
from apps.core.errors import DomainError
from apps.core.secrets import decrypt, encrypt
from apps.core.throttling import AtomicScopedRateThrottle as ScopedRateThrottle
from apps.payments.models import GatewayAccount, KycDocument, KycDocumentType, OnlinePayment
from apps.payments.services import kyc, links
from apps.tenancy.api.base import IsPlatformStaff, TenantAPIView
from apps.tenancy.context import tenant_context


def webhook_url(acc) -> str:
    return f"{settings.QASSA['PUBLIC_ADMIN_URL'].rstrip('/')}/api/v1/payments/klickpay/webhook/{acc.webhook_token}" if acc.webhook_token else ""


def doc_out(d):
    return None if d is None else {"id": d.id, "status": d.status, "note": d.note, "name": d.original_name,
                                   "uploaded_at": d.uploaded_at, "reviewed_at": d.reviewed_at}


def checklist_out():
    return [{"type": {"id": t.id, "code": t.code, "name_ar": t.name_ar, "name_en": t.name_en, "help_ar": t.help_ar,
                      "help_en": t.help_en, "required": t.required}, "doc": doc_out(d)} for t, d in kyc.checklist()]


def op_out(op):
    return {"id": op.id, "reference": op.reference, "invoice": op.invoice.number, "invoice_id": op.invoice_id, "amount": str(op.amount),
            "status": op.status, "method": op.method, "detail": op.detail, "payment_url": op.payment_url,
            "created_at": op.created_at, "settled_at": op.settled_at,
            "customer": op.invoice.customer.full_name if op.invoice.customer_id else ""}


# ---------- salon ----------
class AccountView(TenantAPIView):
    """The salon's KlickPay account: where the opening stands and the documents checklist."""
    required_permissions = {"GET": "org.manage"}

    @extend_schema(responses=dict)
    def get(self, request):
        acc = kyc.account()
        return Response({"status": acc.status, "review_note": acc.review_note, "active": acc.status == GatewayAccount.Status.ACTIVE,
                         "submitted_at": acc.submitted_at, "activated_at": acc.activated_at, "checklist": checklist_out()})


class KycUploadView(TenantAPIView):
    parser_classes = [MultiPartParser]
    required_permissions = {"POST": "org.manage"}

    @extend_schema(request={"multipart/form-data": OpenApiTypes.OBJECT}, responses=dict)
    def post(self, request):
        f = request.FILES.get("file")
        if f is None:
            raise DomainError(code="kyc_file_type")
        d = kyc.upload(request.data.get("doc_type"), f, request.user)
        audit("payments.kyc_uploaded", tenant_id=request.tenant_id, actor=request.user, obj=d, data={"type": d.doc_type.code})
        return Response(doc_out(d), status=201)


class KycSubmitView(TenantAPIView):
    required_permissions = {"POST": "org.manage"}

    @extend_schema(request=None, responses=dict)
    def post(self, request):
        acc = kyc.submit(request.user)
        audit("payments.kyc_submitted", tenant_id=request.tenant_id, actor=request.user, obj=acc)
        return Response({"status": acc.status})


class KycFileView(TenantAPIView):
    required_permissions = {"GET": "org.manage"}

    @extend_schema(responses={200: OpenApiTypes.BINARY})
    def get(self, request, pk):
        d = get_object_or_404(KycDocument.objects.all(), pk=pk)
        return FileResponse(d.file.open("rb"), as_attachment=False, filename=d.original_name)


class OnlinePaymentsView(TenantAPIView):
    required_permissions = {"GET": "pos.invoices.view"}

    @extend_schema(responses=dict)
    def get(self, request):
        qs = OnlinePayment.objects.select_related("invoice__customer").order_by("-id")
        allowed = request.membership.branch_ids()
        if allowed is not None:
            qs = qs.filter(invoice__branch_id__in=allowed)
        if request.query_params.get("invoice"):
            qs = qs.filter(invoice_id=request.query_params["invoice"])
        return Response([op_out(o) for o in qs[:200]])


class PayLinkIn(serializers.Serializer):
    send = serializers.BooleanField(default=False)


class InvoicePayLinkView(TenantAPIView):
    """Issue (or reuse) a KlickPay link for the invoice balance; optionally send it from the salon's WhatsApp number."""
    required_permissions = {"POST": "pos.sell"}

    @extend_schema(request=PayLinkIn, responses=dict)
    def post(self, request, pk):
        from apps.notifications import whatsapp
        from apps.pos.api.views import _invoice
        s = PayLinkIn(data=request.data)
        s.is_valid(raise_exception=True)
        inv = _invoice(request, pk)
        op = links.create_invoice_link(inv, request.user)
        lang = inv.customer.preferred_language
        text = (f"أهلاً {inv.customer.full_name.split(' ')[0]}، ده لينك دفع فاتورة {inv.number} بمبلغ {op.amount} د.ك:\n{op.payment_url}" if lang == "ar"
                else f"Hi {inv.customer.full_name.split(' ')[0]}, here is the payment link for invoice {inv.number} ({op.amount} KWD):\n{op.payment_url}")
        sent = False
        if s.validated_data["send"] and inv.customer.whatsapp_opt_in:
            try:
                whatsapp.send_text(inv.customer.phone, text, kind="pay_link", preview=f"pay link {inv.number}")
                sent = True
            except DomainError:
                sent = False
        return Response({**op_out(op), "sent": sent, "text": text, "phone": inv.customer.phone})


# ---------- public ----------
class PublicPayResultView(APIView):
    """The page KlickPay redirects to: shows the state and asks for a server-side check (never trusts the redirect)."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public"

    @extend_schema(responses=dict)
    def get(self, request, ref):
        op = OnlinePayment.unscoped.select_related("invoice", "tenant").filter(reference=ref).first()
        if op is None:
            _not_found()
        with tenant_context(op.tenant_id):
            if op.status == OnlinePayment.Status.CREATED:
                from apps.core.services.infra import enqueue
                import time
                enqueue("klickpay.confirm", {"online_payment_id": op.id}, tenant_id=op.tenant_id,
                        dedupe_key=f"op:{op.id}:check:{int(time.time()) // 20}")
            return Response({"status": op.status, "amount": str(op.amount), "invoice": op.invoice.number, "salon": op.tenant.name})


def _not_found():
    e = DomainError(code="payment_not_found")
    e.status_code = 404
    raise e


@csrf_exempt
@require_POST
def klickpay_webhook(request, token):
    """Signed with the salon's own webhook secret (HMAC-SHA256 over the raw body). Answers fast; work goes to the outbox."""
    acc = GatewayAccount.unscoped.filter(webhook_token=token).first()
    if acc is None:
        return HttpResponse(status=404)
    raw = request.body
    if not links.verify(raw, request.headers.get("X-KlickPay-Signature", ""), request.headers.get("X-KlickPay-Timestamp", ""),
                        decrypt(acc.webhook_secret_enc)):
        return HttpResponse("signature", status=401)
    try:
        body = json.loads(raw)
        assert isinstance(body, dict)
    except (ValueError, AssertionError):
        return HttpResponse("body", status=400)
    return JsonResponse({"result": links.accept_webhook(acc, body, request.headers.get("X-KlickPay-Event", ""))})


# ---------- platform ----------
class PlatformAccountsView(APIView):
    """Every salon's KlickPay opening status, for the platform team acting as KlickPay's agent."""
    permission_classes = [IsPlatformStaff]

    @extend_schema(responses=dict, operation_id="platform_payments_accounts_list")
    def get(self, request):
        from apps.tenancy.models import Tenant
        accs = {a.tenant_id: a for a in GatewayAccount.unscoped.all()}
        docs = {r["tenant_id"]: r for r in KycDocument.unscoped.filter(is_current=True).values("tenant_id").annotate(
            n=Count("id"), rejected=Count("id", filter=Q(status="rejected")), accepted=Count("id", filter=Q(status="accepted")))}
        out = []
        for t in Tenant.objects.order_by("name"):
            a = accs.get(t.id)
            d = docs.get(t.id, {})
            out.append({"tenant_id": t.id, "tenant": t.name, "slug": t.slug, "status": a.status if a else "not_started",
                        "environment": a.environment if a else "staging", "docs": d.get("n", 0), "accepted": d.get("accepted", 0),
                        "rejected": d.get("rejected", 0), "has_credentials": bool(a and a.client_id and a.client_secret_enc),
                        "commission_percent": str(a.commission_percent) if a else "0.00",
                        "commission_fixed": str(a.commission_fixed) if a else "0.000", "submitted_at": a.submitted_at if a else None})
        return Response({"accounts": out, "required_types": KycDocumentType.objects.filter(is_active=True).count()})


class AccountAdminIn(serializers.Serializer):
    status = serializers.ChoiceField(choices=GatewayAccount.Status.choices, required=False)
    review_note = serializers.CharField(max_length=500, required=False, allow_blank=True)
    environment = serializers.ChoiceField(choices=GatewayAccount.Env.choices, required=False)
    client_id = serializers.CharField(max_length=200, required=False, allow_blank=True)
    client_secret = serializers.CharField(max_length=500, required=False, allow_blank=True, write_only=True)
    merchant_token = serializers.CharField(max_length=200, required=False, allow_blank=True)
    commission_percent = serializers.DecimalField(max_digits=5, decimal_places=2, min_value=0, max_value=100, required=False)
    commission_fixed = serializers.DecimalField(max_digits=18, decimal_places=3, min_value=0, required=False)
    new_webhook_secret = serializers.BooleanField(default=False)


class PlatformAccountView(APIView):
    permission_classes = [IsPlatformStaff]

    def _out(self, acc, secret=None):
        with tenant_context(acc.tenant_id):
            return {"tenant_id": acc.tenant_id, "status": acc.status, "review_note": acc.review_note, "environment": acc.environment,
                    "client_id": acc.client_id, "has_secret": bool(acc.client_secret_enc), "merchant_token": acc.merchant_token,
                    "commission_percent": str(acc.commission_percent), "commission_fixed": str(acc.commission_fixed),
                    "webhook_url": webhook_url(acc), "has_webhook_secret": bool(acc.webhook_secret_enc),
                    **({"webhook_secret": secret} if secret else {}), "checklist": checklist_out()}

    @extend_schema(responses=dict)
    def get(self, request, tenant_id):
        with tenant_context(tenant_id):
            return Response(self._out(kyc.account()))

    @extend_schema(request=AccountAdminIn, responses=dict)
    def patch(self, request, tenant_id):
        from django.utils import timezone
        s = AccountAdminIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        with tenant_context(tenant_id):
            acc = kyc.account()
            for k in ("review_note", "environment", "client_id", "merchant_token", "commission_percent", "commission_fixed"):
                if k in v:
                    setattr(acc, k, v[k].strip() if isinstance(v[k], str) else v[k])
            if v.get("client_secret"):
                acc.client_secret_enc = encrypt(v["client_secret"].strip())
            secret = None
            if v["new_webhook_secret"]:
                secret = secrets.token_urlsafe(32)        # shown once, to be set at KlickPay (/webhooks/config)
                acc.webhook_secret_enc, acc.webhook_token = encrypt(secret), acc.webhook_token or secrets.token_urlsafe(24)
            if "status" in v:
                if v["status"] == GatewayAccount.Status.ACTIVE and not (acc.client_id and acc.client_secret_enc and acc.webhook_secret_enc):
                    raise DomainError(code="gateway_incomplete")
                if v["status"] == GatewayAccount.Status.NEEDS_CHANGES and not (v.get("review_note") or acc.review_note):
                    raise DomainError(code="kyc_note_required")
                if v["status"] == GatewayAccount.Status.ACTIVE and acc.status != GatewayAccount.Status.ACTIVE:
                    acc.activated_at = timezone.now()
                acc.status = v["status"]
            acc.save()
            audit("platform.gateway_account", tenant_id=tenant_id, actor=request.user, obj=acc,
                  data={k: str(x) for k, x in v.items() if k != "client_secret"} | {"secret_changed": bool(v.get("client_secret"))})
            return Response(self._out(acc, secret))


class ReviewIn(serializers.Serializer):
    accept = serializers.BooleanField()
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class PlatformKycReviewView(APIView):
    permission_classes = [IsPlatformStaff]

    @extend_schema(request=ReviewIn, responses=dict)
    def post(self, request, pk):
        s = ReviewIn(data=request.data)
        s.is_valid(raise_exception=True)
        d = get_object_or_404(KycDocument.unscoped.all(), pk=pk, is_current=True)
        with tenant_context(d.tenant_id):
            kyc.review(d, s.validated_data["accept"], s.validated_data["note"])
            acc = kyc.account()
            if not s.validated_data["accept"] and acc.status == GatewayAccount.Status.UNDER_REVIEW:
                acc.status = GatewayAccount.Status.NEEDS_CHANGES   # the salon sees exactly which document to fix
                acc.save(update_fields=["status", "updated_at"])
            audit("platform.kyc_review", tenant_id=d.tenant_id, actor=request.user, obj=d,
                  data={"accept": s.validated_data["accept"], "note": s.validated_data["note"]})
            return Response({**doc_out(d), "account_status": acc.status})


class PlatformKycFileView(APIView):
    permission_classes = [IsPlatformStaff]

    @extend_schema(responses={200: OpenApiTypes.BINARY})
    def get(self, request, pk):
        d = get_object_or_404(KycDocument.unscoped.all(), pk=pk)
        audit("platform.kyc_viewed", tenant_id=d.tenant_id, actor=request.user, obj=d)
        return FileResponse(d.file.open("rb"), as_attachment=False, filename=d.original_name)


class PlatformPaymentsReportView(APIView):
    """Per salon for a month: successful and failed online payments, and the platform's commission on the successful ones."""
    permission_classes = [IsPlatformStaff]

    @extend_schema(responses=dict)
    def get(self, request):
        import datetime
        from decimal import Decimal
        from apps.core.money import money
        from apps.tenancy.models import Tenant
        m = request.query_params.get("month") or datetime.date.today().strftime("%Y-%m")
        try:
            y, mo = map(int, m.split("-"))
            start = datetime.date(y, mo, 1)
        except ValueError:
            raise DomainError(code="month_invalid")
        end = datetime.date(y + (mo == 12), mo % 12 + 1, 1)
        rows = {r["tenant_id"]: r for r in OnlinePayment.unscoped.filter(created_at__date__gte=start, created_at__date__lt=end)
                .values("tenant_id").annotate(
                    paid_n=Count("id", filter=Q(status="paid")), paid=Sum("amount", filter=Q(status="paid")),
                    failed_n=Count("id", filter=Q(status__in=["declined", "failed", "voided"])),
                    failed=Sum("amount", filter=Q(status__in=["declined", "failed", "voided"])),
                    pending_n=Count("id", filter=Q(status="created")), review_n=Count("id", filter=Q(status="review")))}
        accs = {a.tenant_id: a for a in GatewayAccount.unscoped.all()}
        names = dict(Tenant.objects.values_list("id", "name"))
        out, tot = [], {"paid": Decimal(0), "commission": Decimal(0), "paid_n": 0, "failed_n": 0}
        for tid in sorted(set(rows) | {t for t, a in accs.items() if a.status == "active"}, key=lambda x: names.get(x, "")):
            r, a = rows.get(tid, {}), accs.get(tid)
            paid = money(r.get("paid") or 0)
            pct, fixed = (a.commission_percent, a.commission_fixed) if a else (Decimal(0), Decimal(0))
            comm = money(paid * pct / 100 + fixed * (r.get("paid_n") or 0))
            out.append({"tenant_id": tid, "tenant": names.get(tid, ""), "paid_count": r.get("paid_n", 0), "paid_amount": str(paid),
                        "failed_count": r.get("failed_n", 0), "failed_amount": str(money(r.get("failed") or 0)),
                        "pending_count": r.get("pending_n", 0), "review_count": r.get("review_n", 0),
                        "commission_percent": str(pct), "commission_fixed": str(fixed), "commission": str(comm)})
            tot["paid"] += paid; tot["commission"] += comm; tot["paid_n"] += r.get("paid_n", 0); tot["failed_n"] += r.get("failed_n", 0)
        return Response({"month": m, "rows": out, "totals": {k: (str(money(v)) if isinstance(v, Decimal) else v) for k, v in tot.items()}})
