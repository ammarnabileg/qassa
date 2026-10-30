"""Reports (branch and company), salon settings and data export."""
import csv
import io
from datetime import date

from django.http import HttpResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers
from rest_framework.response import Response

from apps.core.dates import business_date
from apps.core.errors import DomainError
from apps.pos.services import reports
from apps.tenancy.api.base import TenantAPIView, branch_for


def _range(request):
    try:
        d_to = date.fromisoformat(request.query_params.get("to") or business_date().isoformat())
        d_from = date.fromisoformat(request.query_params.get("from") or d_to.replace(day=1).isoformat())
    except ValueError:
        raise DomainError(code="bad_dates")
    if d_from > d_to or (d_to - d_from).days > 366:
        raise DomainError(code="date_out_of_range")
    return d_from, d_to


def _scope(request):
    """A branch (if asked, and allowed), else every branch the member can see."""
    if request.query_params.get("branch_id"):
        return [branch_for(request, request.query_params["branch_id"]).id]
    allowed = request.membership.branch_ids()
    return None if allowed is None else sorted(allowed)


class SalesReportView(TenantAPIView):
    required_permissions = {"GET": "pos.invoices.view"}

    @extend_schema(parameters=[OpenApiParameter("from", str), OpenApiParameter("to", str), OpenApiParameter("branch_id", int)], responses=dict)
    def get(self, request):
        d_from, d_to = _range(request)
        return Response(reports.sales(d_from=d_from, d_to=d_to, branch_ids=_scope(request),
                                      show_cost=request.membership.has_perm("report.view.cost_profit")))


class BranchesReportView(TenantAPIView):
    required_permissions = {"GET": "pos.invoices.view"}

    @extend_schema(responses=dict)
    def get(self, request):
        today = business_date()
        return Response(reports.branches(today=today, month_start=today.replace(day=1), branch_ids=_scope(request)))


class SalonSettingsSerializer(serializers.Serializer):
    receipt_header_ar = serializers.CharField(max_length=120, required=False, allow_blank=True)
    receipt_footer_ar = serializers.CharField(max_length=200, required=False, allow_blank=True)
    receipt_footer_en = serializers.CharField(max_length=200, required=False, allow_blank=True)
    commercial_registration = serializers.CharField(max_length=40, required=False, allow_blank=True)
    show_staff_on_receipt = serializers.BooleanField(required=False)


class SalonSettingsView(TenantAPIView):
    """Receipt texts. Read by every till; changed by the owner / operations."""
    required_permissions = {"GET": "pos.sell", "PATCH": "org.manage"}

    @extend_schema(responses=SalonSettingsSerializer)
    def get(self, request):
        from apps.tenancy.models import SalonSettings
        return Response(SalonSettingsSerializer(SalonSettings.objects.get_or_create(tenant_id=request.tenant_id)[0]).data)

    @extend_schema(request=SalonSettingsSerializer, responses=SalonSettingsSerializer)
    def patch(self, request):
        from apps.audit.services.log import record as audit
        from apps.tenancy.models import SalonSettings
        s = SalonSettingsSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        obj = SalonSettings.objects.get_or_create(tenant_id=request.tenant_id)[0]
        for k, v in s.validated_data.items():
            setattr(obj, k, v)
        obj.save()
        audit("org.salon_settings", tenant_id=request.tenant_id, actor=request.user, obj=obj, data=s.validated_data)
        return Response(SalonSettingsSerializer(obj).data)


class ExportView(TenantAPIView):
    """CSV (UTF-8 with BOM, opens in Excel) of the company's customers or invoices. Audited."""
    required_permissions = {"GET": "data.export"}

    @extend_schema(parameters=[OpenApiParameter("from", str), OpenApiParameter("to", str)], responses={200: bytes})
    def get(self, request, kind):
        from apps.audit.services.log import record as audit
        buf = io.StringIO()
        w = csv.writer(buf)
        if kind == "customers":
            from apps.customers.models import Customer
            w.writerow(["id", "name", "phone", "email", "language", "whatsapp_opt_in", "marketing_opt_in", "beneficiaries", "created_at"])
            for c in Customer.objects.prefetch_related("beneficiaries").order_by("id"):
                w.writerow([c.id, c.full_name, c.phone, c.email, c.preferred_language, c.whatsapp_opt_in, c.marketing_opt_in,
                            " | ".join(b.full_name for b in c.beneficiaries.all()), c.created_at.isoformat()])
        elif kind == "invoices":
            from apps.pos.models import Invoice
            d_from, d_to = _range(request)
            w.writerow(["number", "date", "branch", "customer", "subtotal", "discount", "total", "tip", "credit", "offline_ref"])
            qs = Invoice.objects.filter(business_date__gte=d_from, business_date__lte=d_to).select_related("branch", "customer").order_by("id")
            allowed = request.membership.branch_ids()
            if allowed is not None:
                qs = qs.filter(branch_id__in=allowed)
            for i in qs:
                w.writerow([i.number, i.business_date.isoformat(), i.branch.name_ar, i.customer.full_name if i.customer_id else "",
                            i.subtotal, i.discount_total, i.total, i.tip, i.is_credit, i.offline_ref])
        else:
            raise DomainError(code="bad_action")
        audit("data.exported", tenant_id=request.tenant_id, actor=request.user, data={"kind": kind})
        resp = HttpResponse("﻿" + buf.getvalue(), content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="qassa-{kind}.csv"'
        return resp
