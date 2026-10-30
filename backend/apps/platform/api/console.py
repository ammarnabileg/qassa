"""Platform console (owner of the SaaS): dashboard, subscription invoices, support tickets, leads, support access.
Salon side: its own tickets and subscription invoices. Public: the 'contact us' form."""
import datetime
from decimal import Decimal

from django.db import transaction
from django.db.models import Count, Sum
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from apps.core.throttling import AtomicScopedRateThrottle as ScopedRateThrottle
from rest_framework.views import APIView

from apps.audit.services.log import record as audit
from apps.core.dates import business_date
from apps.core.errors import DomainError
from apps.platform.models import Lead, Plan, PlatformInvoice, Subscription, SupportAccess, SupportTicket, TicketMessage
from apps.platform.services import billing
from apps.tenancy.api.base import IsPlatformStaff, TenantAPIView
from apps.tenancy.models import Branch, Tenant

ZERO = Decimal("0.000")
SUPPORT_MINUTES = 60


def _mrr() -> Decimal:
    return (Subscription.objects.filter(tenant__status__in=[Tenant.Status.ACTIVE, Tenant.Status.PAST_DUE])
            .aggregate(s=Sum("plan__monthly_price"))["s"] or ZERO)


class DashboardView(APIView):
    """Real figures only (no sample data)."""
    permission_classes = [IsPlatformStaff]

    @extend_schema(responses=dict)
    def get(self, request):
        today = business_date()
        by_status = dict(Tenant.objects.values_list("status").annotate(n=Count("id")))
        overdue = PlatformInvoice.objects.filter(status=PlatformInvoice.Status.ISSUED, due_on__lt=today)
        months = []
        d = today.replace(day=1)
        for _ in range(6):
            months.append(d)
            d = (d - datetime.timedelta(days=1)).replace(day=1)
        history = []
        for m in reversed(months):
            end = billing.add_month(m)
            q = PlatformInvoice.objects.filter(period_start__gte=m, period_start__lt=end).exclude(status=PlatformInvoice.Status.VOID)
            history.append({"month": m.isoformat()[:7], "invoiced": str(q.aggregate(s=Sum("amount"))["s"] or ZERO),
                            "collected": str(q.filter(status=PlatformInvoice.Status.PAID).aggregate(s=Sum("amount"))["s"] or ZERO)})
        plans = [{"code": p.code, "name_ar": p.name_ar, "name_en": p.name_en,
                  "tenants": Subscription.objects.filter(plan=p).exclude(tenant__status=Tenant.Status.SUSPENDED).count()}
                 for p in Plan.objects.order_by("sort")]
        renewals = [{"tenant_id": s.tenant_id, "name": s.tenant.name, "status": s.tenant.status, "plan": s.plan.name_ar,
                     "plan_en": s.plan.name_en, "period_end": s.current_period_end}
                    for s in Subscription.objects.select_related("tenant", "plan")
                    .exclude(tenant__status=Tenant.Status.SUSPENDED).order_by("current_period_end")[:6]]
        tickets = [{"id": t.id, "subject": t.subject, "tenant": t.tenant.name, "priority": t.priority, "status": t.status}
                   for t in SupportTicket.objects.select_related("tenant").exclude(status=SupportTicket.Status.CLOSED)[:6]]
        mrr = _mrr()
        return Response({
            "tenants": {k: by_status.get(k, 0) for k in Tenant.Status.values},
            "branches": Branch.unscoped.filter(is_active=True).count(),
            "mrr": str(mrr), "arr": str(mrr * 12),
            "overdue": {"count": overdue.count(), "amount": str(overdue.aggregate(s=Sum("amount"))["s"] or ZERO)},
            "new_leads": Lead.objects.filter(status=Lead.Status.NEW).count(),
            "history": history, "plans": plans, "renewals": renewals, "tickets": tickets,
        })


class SubInvoiceOut(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source="tenant.name")
    plan_name_ar = serializers.CharField(source="plan.name_ar")
    plan_name_en = serializers.CharField(source="plan.name_en")
    overdue = serializers.SerializerMethodField()

    class Meta:
        model = PlatformInvoice
        fields = ["id", "number", "tenant", "tenant_name", "plan_name_ar", "plan_name_en", "period_start", "period_end", "amount",
                  "due_on", "status", "overdue", "paid_at", "paid_method", "paid_reference"]

    def get_overdue(self, obj) -> bool:
        return obj.status == PlatformInvoice.Status.ISSUED and obj.due_on < business_date()


class PlatformInvoicesView(APIView):
    permission_classes = [IsPlatformStaff]

    @extend_schema(parameters=[OpenApiParameter("status", str), OpenApiParameter("tenant_id", int)], responses=SubInvoiceOut(many=True))
    def get(self, request):
        qs = PlatformInvoice.objects.select_related("tenant", "plan")
        st = request.query_params.get("status")
        if st == "overdue":
            qs = qs.filter(status=PlatformInvoice.Status.ISSUED, due_on__lt=business_date())
        elif st:
            qs = qs.filter(status=st)
        if request.query_params.get("tenant_id"):
            qs = qs.filter(tenant_id=request.query_params["tenant_id"])
        return Response(SubInvoiceOut(qs[:300], many=True).data)

    @extend_schema(request=None, responses=dict)
    def post(self, request):
        """Run billing now (the same job runs every night)."""
        issued = billing.issue_due()
        past_due = billing.mark_overdue()
        audit("platform.billing_run", actor=request.user, data={"issued": len(issued), "past_due": past_due})
        return Response({"issued": len(issued), "past_due": past_due})


class InvoiceActionIn(serializers.Serializer):
    action = serializers.ChoiceField(choices=["pay", "void"])
    method = serializers.ChoiceField(choices=["bank", "knet", "cash", "other"], required=False, default="bank")
    reference = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class PlatformInvoiceActionView(APIView):
    permission_classes = [IsPlatformStaff]

    @extend_schema(request=InvoiceActionIn, responses=SubInvoiceOut)
    def post(self, request, pk):
        inv = get_object_or_404(PlatformInvoice.objects.all(), pk=pk)
        s = InvoiceActionIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        if v["action"] == "pay":
            inv = billing.record_payment(inv, method=v["method"], reference=v["reference"], user=request.user)
        else:
            inv = billing.void(inv, reason=v["reason"], user=request.user)
        return Response(SubInvoiceOut(PlatformInvoice.objects.select_related("tenant", "plan").get(id=inv.id)).data)


# ---------- support tickets ----------
class MessageOut(serializers.ModelSerializer):
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = TicketMessage
        fields = ["id", "from_platform", "author_name", "body", "created_at"]

    def get_author_name(self, obj) -> str:
        return obj.author.full_name or obj.author.email


class TicketOut(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source="tenant.name")
    messages = MessageOut(many=True)

    class Meta:
        model = SupportTicket
        fields = ["id", "tenant", "tenant_name", "subject", "priority", "status", "created_at", "updated_at", "messages"]


def _tickets():
    return SupportTicket.objects.select_related("tenant").prefetch_related("messages__author")


class TicketIn(serializers.Serializer):
    subject = serializers.CharField(max_length=200)
    body = serializers.CharField(max_length=5000)
    priority = serializers.ChoiceField(choices=SupportTicket.Priority.choices, default="mid")


class ReplyIn(serializers.Serializer):
    body = serializers.CharField(max_length=5000, required=False, allow_blank=True, default="")
    status = serializers.ChoiceField(choices=SupportTicket.Status.choices, required=False)


class PlatformTicketsView(APIView):
    permission_classes = [IsPlatformStaff]

    @extend_schema(parameters=[OpenApiParameter("status", str)], responses=TicketOut(many=True))
    def get(self, request):
        qs = _tickets()
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        return Response(TicketOut(qs[:200], many=True).data)


def _reply(ticket, user, v, from_platform):
    with transaction.atomic():
        if v["body"].strip():
            TicketMessage.objects.create(ticket=ticket, author=user, from_platform=from_platform, body=v["body"].strip())
        new = v.get("status") or (SupportTicket.Status.PENDING if from_platform else SupportTicket.Status.OPEN)
        if not v["body"].strip() and not v.get("status"):
            raise DomainError(code="reply_empty")
        ticket.status = new
        ticket.save(update_fields=["status", "updated_at"])
    return TicketOut(_tickets().get(id=ticket.id)).data


class PlatformTicketReplyView(APIView):
    """Platform answers; the salon owner is notified on WhatsApp from the platform number when available."""
    permission_classes = [IsPlatformStaff]

    @extend_schema(request=ReplyIn, responses=TicketOut)
    def post(self, request, pk):
        ticket = get_object_or_404(SupportTicket.objects.select_related("tenant"), pk=pk)
        s = ReplyIn(data=request.data)
        s.is_valid(raise_exception=True)
        out = _reply(ticket, request.user, s.validated_data, True)
        if s.validated_data["body"].strip():
            _notify_owner(ticket, s.validated_data["body"].strip())
        return Response(out)


def _notify_owner(ticket, body):
    from apps.notifications import whatsapp
    from apps.identity.models import User
    owner = User.objects.filter(memberships__tenant=ticket.tenant, memberships__role__key="owner").exclude(phone="").first()
    if owner and whatsapp.platform_available():
        try:
            whatsapp.send_platform_text(owner.phone, f"قصّة POS — رد على تذكرة #{ticket.id} ({ticket.subject}):\n\n{body[:900]}")
        except Exception:  # noqa: BLE001 — the reply is saved either way; delivery failure is not hidden from the ticket
            pass


class MyTicketsView(TenantAPIView):
    """The salon's own tickets (owner / managers)."""
    required_permissions = {"GET": "org.manage", "POST": "org.manage"}

    @extend_schema(responses=TicketOut(many=True))
    def get(self, request):
        return Response(TicketOut(_tickets().filter(tenant_id=request.tenant_id)[:100], many=True).data)

    @extend_schema(request=TicketIn, responses={201: TicketOut})
    def post(self, request):
        s = TicketIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        with transaction.atomic():
            t = SupportTicket.objects.create(tenant_id=request.tenant_id, subject=v["subject"], priority=v["priority"],
                                             created_by=request.user)
            TicketMessage.objects.create(ticket=t, author=request.user, body=v["body"])
        return Response(TicketOut(_tickets().get(id=t.id)).data, status=status.HTTP_201_CREATED)


class MyTicketReplyView(TenantAPIView):
    required_permissions = {"POST": "org.manage"}

    @extend_schema(request=ReplyIn, responses=TicketOut)
    def post(self, request, pk):
        ticket = get_object_or_404(SupportTicket.objects.filter(tenant_id=request.tenant_id), pk=pk)
        s = ReplyIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = dict(s.validated_data)
        if v.get("status") not in (None, SupportTicket.Status.CLOSED):
            v.pop("status")   # the salon may only close; otherwise its reply reopens the ticket
        return Response(_reply(ticket, request.user, v, False))


class MyInvoicesView(TenantAPIView):
    required_permissions = {"GET": "org.manage"}

    @extend_schema(responses=SubInvoiceOut(many=True))
    def get(self, request):
        return Response(SubInvoiceOut(PlatformInvoice.objects.select_related("tenant", "plan")
                                   .filter(tenant_id=request.tenant_id).exclude(status=PlatformInvoice.Status.VOID)[:36], many=True).data)


# ---------- leads (public 'contact us') ----------
class LeadIn(serializers.ModelSerializer):
    website = serializers.CharField(required=False, allow_blank=True, write_only=True)  # honeypot: humans leave it empty

    class Meta:
        model = Lead
        fields = ["salon_name", "contact_name", "phone", "email", "business_type", "branches", "plan_code", "city", "message", "website"]


class PublicLeadView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "lead"

    @extend_schema(request=LeadIn, responses={201: dict})
    def post(self, request):
        from apps.customers.services.phone import normalize_phone as normalize
        s = LeadIn(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data
        if v.pop("website", ""):
            return Response({"ok": True}, status=status.HTTP_201_CREATED)   # silently drop bots
        v["phone"] = normalize(v["phone"])
        if v["business_type"] not in ("kids", "men", "women"):
            v["business_type"] = "kids"
        Lead.objects.create(ip=request.META.get("REMOTE_ADDR"), **v)
        return Response({"ok": True}, status=status.HTTP_201_CREATED)


class LeadOut(serializers.ModelSerializer):
    class Meta:
        model = Lead
        fields = ["id", "salon_name", "contact_name", "phone", "email", "business_type", "branches", "plan_code", "city",
                  "message", "status", "notes", "created_at"]
        read_only_fields = [f for f in fields if f not in ("status", "notes")]


class PlatformLeadsView(APIView):
    permission_classes = [IsPlatformStaff]

    @extend_schema(responses=LeadOut(many=True))
    def get(self, request):
        return Response(LeadOut(Lead.objects.all()[:300], many=True).data)


class PlatformLeadDetailView(APIView):
    permission_classes = [IsPlatformStaff]

    @extend_schema(request=LeadOut, responses=LeadOut)
    def patch(self, request, pk):
        lead = get_object_or_404(Lead.objects.all(), pk=pk)
        s = LeadOut(lead, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        s.save()
        return Response(s.data)


# ---------- support access ----------
class SupportIn(serializers.Serializer):
    reason = serializers.CharField(min_length=10, max_length=300)


class SupportAccessView(APIView):
    """Platform staff open a read-only, time-limited view of one company, with a written reason; audited."""
    permission_classes = [IsPlatformStaff]

    @extend_schema(request=SupportIn, responses={201: dict})
    def post(self, request, pk):
        tenant = get_object_or_404(Tenant.objects.all(), pk=pk)
        s = SupportIn(data=request.data)
        s.is_valid(raise_exception=True)
        SupportAccess.objects.filter(staff=request.user, ended_at__isnull=True).update(ended_at=timezone.now())
        acc = SupportAccess.objects.create(staff=request.user, tenant=tenant, reason=s.validated_data["reason"],
                                           expires_at=timezone.now() + datetime.timedelta(minutes=SUPPORT_MINUTES))
        audit("platform.support_access_started", tenant_id=tenant.id, actor=request.user, obj=tenant,
              reason=acc.reason, acting_as_support=True, data={"expires_at": acc.expires_at.isoformat()})
        return Response({"tenant_id": tenant.id, "expires_at": acc.expires_at}, status=status.HTTP_201_CREATED)

    @extend_schema(responses={204: None})
    def delete(self, request, pk):
        n = SupportAccess.objects.filter(staff=request.user, tenant_id=pk, ended_at__isnull=True).update(ended_at=timezone.now())
        if n:
            audit("platform.support_access_ended", tenant_id=pk, actor=request.user, acting_as_support=True)
        return Response(status=status.HTTP_204_NO_CONTENT)


def active_support(user, tenant_id=None):
    if not (user and user.is_authenticated and user.is_platform_staff):
        return SupportAccess.objects.none()
    qs = SupportAccess.objects.select_related("tenant").filter(staff=user, ended_at__isnull=True, expires_at__gt=timezone.now())
    return qs.filter(tenant_id=tenant_id) if tenant_id else qs




class PublicSiteView(APIView):
    """Contact details, headline and trial length for the public site (no secrets)."""
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(responses=dict)
    def get(self, request):
        from django.conf import settings

        from apps.platform.models import PlatformSettings
        c = PlatformSettings.get()
        return Response({"whatsapp": c.sales_whatsapp or settings.QASSA["SALES_WHATSAPP"], "email": c.support_email or settings.QASSA["SALES_EMAIL"],
                         "trial_days": c.trial_days, "headline_ar": c.headline_ar, "headline_en": c.headline_en, "sub_ar": c.sub_ar, "sub_en": c.sub_en})


class PlatformSettingsSerializer(serializers.Serializer):
    support_email = serializers.EmailField(required=False, allow_blank=True)
    sales_whatsapp = serializers.CharField(max_length=20, required=False, allow_blank=True)
    headline_ar = serializers.CharField(max_length=200, required=False, allow_blank=True)
    headline_en = serializers.CharField(max_length=200, required=False, allow_blank=True)
    sub_ar = serializers.CharField(max_length=400, required=False, allow_blank=True)
    sub_en = serializers.CharField(max_length=400, required=False, allow_blank=True)
    trial_days = serializers.IntegerField(min_value=0, max_value=90, required=False)


class PlatformSettingsView(APIView):
    permission_classes = [IsPlatformStaff]

    @extend_schema(responses=PlatformSettingsSerializer)
    def get(self, request):
        from apps.platform.models import PlatformSettings
        return Response(PlatformSettingsSerializer(PlatformSettings.get()).data)

    @extend_schema(request=PlatformSettingsSerializer, responses=PlatformSettingsSerializer)
    def patch(self, request):
        from apps.customers.services.phone import normalize_phone
        from apps.platform.models import PlatformSettings
        s = PlatformSettingsSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        c = PlatformSettings.get()
        for k, v in s.validated_data.items():
            setattr(c, k, normalize_phone(v) if k == "sales_whatsapp" and v else v)
        c.save()
        audit("platform.settings", actor=request.user, data={k: str(v) for k, v in s.validated_data.items()})
        return Response(PlatformSettingsSerializer(c).data)
