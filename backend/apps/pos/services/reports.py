"""Operational reports from issued documents (invoices, credit notes, payments) — reference screens v-rep, v-c-home, v-c-rep.
Money in strings; cost and profit only for members allowed to see them (report.view.cost_profit)."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.utils import timezone

from apps.pos.models import CashSession, CreditNote, Invoice, InvoiceLine, Payment

ZERO = Decimal("0.000")


def _s(v) -> str:
    return str((v or ZERO).quantize(Decimal("0.001")))


def sales(*, d_from: date, d_to: date, branch_ids: list[int] | None, show_cost: bool) -> dict:
    """Stats, daily series, top items, by staff, payment methods, peak hours and (optionally) a profit summary."""
    inv = Invoice.objects.filter(business_date__gte=d_from, business_date__lte=d_to)
    cn = CreditNote.objects.filter(business_date__gte=d_from, business_date__lte=d_to)
    pay = Payment.objects.filter(business_date__gte=d_from, business_date__lte=d_to)
    lines = InvoiceLine.objects.filter(invoice__business_date__gte=d_from, invoice__business_date__lte=d_to)
    if branch_ids is not None:
        inv, cn, pay = inv.filter(branch_id__in=branch_ids), cn.filter(invoice__branch_id__in=branch_ids), pay.filter(branch_id__in=branch_ids)
        lines = lines.filter(invoice__branch_id__in=branch_ids)
    agg = inv.aggregate(total=Sum("total"), n=Count("id"), disc=Sum("discount_total"), tips=Sum("tip"), customers=Count("customer", distinct=True))
    returns = cn.aggregate(s=Sum("total"))["s"] or ZERO
    gross = agg["total"] or ZERO
    net = gross - returns
    days = defaultdict(lambda: ZERO)
    for d, t in inv.values_list("business_date").annotate(t=Sum("total")):
        days[d] += t
    for d, t in cn.values_list("business_date").annotate(t=Sum("total")):
        days[d] -= t
    series, d = [], d_from
    while d <= d_to and len(series) < 400:
        series.append({"date": d.isoformat(), "total": _s(days.get(d))})
        d += timedelta(days=1)
    items = [{"name_ar": r["name_ar"], "name_en": r["name_en"], "qty": r["q"], "total": _s(r["t"])}
             for r in lines.values("name_ar", "name_en").annotate(q=Sum("qty"), t=Sum("line_total")).order_by("-t")[:10]]
    staff = [{"staff_id": r["staff_id"], "name_ar": r["staff__full_name_ar"], "name_en": r["staff__full_name_en"], "count": r["n"], "total": _s(r["t"])}
             for r in lines.filter(staff__isnull=False).values("staff_id", "staff__full_name_ar", "staff__full_name_en")
             .annotate(n=Count("id"), t=Sum("line_total")).order_by("-t")[:15]]
    methods = defaultdict(lambda: ZERO)
    for m, direction, t in pay.values_list("method", "direction").annotate(t=Sum("amount")):
        methods[m] += t if direction == "in" else -t
    hours = defaultdict(int)
    for at in inv.values_list("issued_at", flat=True):
        hours[timezone.localtime(at).hour] += 1
    out = {
        "from": d_from.isoformat(), "to": d_to.isoformat(),
        "stats": {"sales": _s(net), "invoices": agg["n"], "average": _s(net / agg["n"] if agg["n"] else ZERO),
                  "discounts": _s(agg["disc"]), "returns": _s(returns), "tips": _s(agg["tips"]), "customers": agg["customers"]},
        "days": series, "items": items, "staff": staff,
        "methods": [{"method": k, "total": _s(v)} for k, v in sorted(methods.items(), key=lambda x: -x[1])],
        "hours": [{"hour": h, "invoices": hours[h]} for h in sorted(hours)],
    }
    if show_cost:
        out["profit"] = _profit(d_from, d_to, branch_ids, net, lines)
    return out


def _profit(d_from, d_to, branch_ids, net_sales, lines):
    from apps.accounting.models import Expense
    from apps.staff.models import CommissionEntry
    cogs = sum((l.unit_cost * l.qty for l in lines.filter(kind="product").only("unit_cost", "qty")), Decimal("0"))
    # accruals and reversals of the invoices in range (payouts are not an expense, they settle the payable)
    com = CommissionEntry.objects.filter(invoice_line__invoice__business_date__gte=d_from,
                                         invoice_line__invoice__business_date__lte=d_to).exclude(kind="payout")
    exp = Expense.objects.filter(expense_date__gte=d_from, expense_date__lte=d_to)
    if branch_ids is not None:
        com = com.filter(invoice_line__invoice__branch_id__in=branch_ids)
        exp = exp.filter(branch_id__in=branch_ids)
    commissions = com.aggregate(s=Sum("amount"))["s"] or ZERO
    expenses = exp.aggregate(s=Sum("amount"))["s"] or ZERO
    cogs = cogs.quantize(Decimal("0.001"))
    return {"sales": _s(net_sales), "cogs": _s(cogs), "commissions": _s(commissions), "expenses": _s(expenses),
            "net": _s(net_sales - cogs - commissions - expenses),
            "note": "operational view; the income statement (accounting) is the reference"}


def branches(*, today: date, month_start: date, branch_ids: list[int] | None) -> list[dict]:
    """Per branch: today's sales and invoices, waiting queue, month's sales (company home / branch comparison)."""
    from apps.booking.models import Appointment
    from apps.tenancy.models import Branch
    qs = Branch.objects.filter(is_active=True).order_by("id")
    if branch_ids is not None:
        qs = qs.filter(id__in=branch_ids)
    open_drawers = set(CashSession.objects.filter(status="open").values_list("branch_id", flat=True))
    out = []
    for b in qs:
        def net(frm):
            t = Invoice.objects.filter(branch=b, business_date__gte=frm, business_date__lte=today).aggregate(s=Sum("total"))["s"] or ZERO
            r = CreditNote.objects.filter(invoice__branch=b, business_date__gte=frm, business_date__lte=today).aggregate(s=Sum("total"))["s"] or ZERO
            return t - r
        out.append({"branch_id": b.id, "name_ar": b.name_ar, "name_en": b.name_en, "business_type": b.business_type, "address": b.address,
                    "invoices_month": Invoice.objects.filter(branch=b, business_date__gte=month_start, business_date__lte=today).count(),
                    "today": _s(net(today)), "invoices_today": Invoice.objects.filter(branch=b, business_date=today).count(),
                    "waiting": Appointment.objects.filter(branch=b, business_date=today, status__in=["booked", "arrived"]).count(),
                    "in_service": Appointment.objects.filter(branch=b, business_date=today, status="in_service").count(),
                    "month": _s(net(month_start)),
                    "drawer_open": b.id in open_drawers})
    return out
