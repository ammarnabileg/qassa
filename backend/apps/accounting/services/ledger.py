"""Read side (trial balance) and period/year administration."""
import calendar
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.accounting.coa_template import SALON_COA
from apps.accounting.models import (DEBIT_NORMAL, Account, AccountRoleMapping, FiscalPeriod, FiscalYear,
                                    JournalEntry, JournalLine)
from apps.audit.services.log import record as audit
from apps.core.errors import DomainError

ZERO = Decimal("0.000")


def install_chart(legal_entity) -> int:
    """Create the starter salon chart and role mappings for a legal entity (idempotent)."""
    by_code = {a.code: a for a in Account.objects.filter(legal_entity=legal_entity)}
    for code, ar, en, typ, parent, postable, control, role in SALON_COA:
        acc = by_code.get(code)
        if acc is None:
            acc = Account.objects.create(legal_entity=legal_entity, code=code, name_ar=ar, name_en=en, type=typ,
                                         parent=by_code.get(parent), is_postable=postable, is_control=control)
            by_code[code] = acc
        if role:
            AccountRoleMapping.objects.get_or_create(legal_entity=legal_entity, role=role, defaults={"account": acc})
    return len(by_code)


def create_fiscal_year(legal_entity, year: int) -> FiscalYear:
    start_month = legal_entity.fiscal_year_start_month
    start = date(year, start_month, 1)
    end_year, end_month = (year, 12) if start_month == 1 else (year + 1, start_month - 1)
    end = date(end_year, end_month, calendar.monthrange(end_year, end_month)[1])
    fy, _ = FiscalYear.objects.get_or_create(legal_entity=legal_entity, name=str(year),
                                             defaults={"start_date": start, "end_date": end})
    y, m = start.year, start.month
    for n in range(1, 13):
        last = calendar.monthrange(y, m)[1]
        FiscalPeriod.objects.get_or_create(fiscal_year=fy, number=n, defaults={
            "legal_entity": legal_entity, "start_date": date(y, m, 1), "end_date": date(y, m, last)})
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return fy


def close_period(period: FiscalPeriod, user, *, pending_checks=None) -> FiscalPeriod:
    """Close a period. `pending_checks` lets later phases veto closing (unposted events, unreconciled cash…)."""
    with transaction.atomic():
        p = FiscalPeriod.objects.select_for_update().get(pk=period.pk)
        if p.status == FiscalPeriod.Status.CLOSED:
            return p
        if JournalEntry.objects.filter(period=p, status=JournalEntry.Status.DRAFT).exists():
            raise DomainError("The period has draft entries", code="period_has_drafts")
        for check in pending_checks or []:
            problem = check(p)
            if problem:
                raise DomainError(problem, code="period_close_blocked")
        p.status, p.closed_at, p.closed_by = FiscalPeriod.Status.CLOSED, timezone.now(), user
        p.save(update_fields=["status", "closed_at", "closed_by"])
        audit("period.closed", tenant_id=p.tenant_id, actor=user, obj=p)
        return p


def reopen_period(period: FiscalPeriod, user, reason: str) -> FiscalPeriod:
    if not reason:
        raise DomainError("A reason is required to reopen a period", code="reason_required")
    with transaction.atomic():
        p = FiscalPeriod.objects.select_for_update().get(pk=period.pk)
        p.status, p.closed_at, p.closed_by = FiscalPeriod.Status.OPEN, None, None
        p.save(update_fields=["status", "closed_at", "closed_by"])
        audit("period.reopened", tenant_id=p.tenant_id, actor=user, obj=p, reason=reason)
        return p


def trial_balance(legal_entity_id, date_from: date, date_to: date, branch_id=None) -> dict:
    """Opening, movement and closing per account, from posted ledger lines only."""
    base = JournalLine.objects.filter(entry__legal_entity_id=legal_entity_id, entry__status=JournalEntry.Status.POSTED)
    if branch_id:
        base = base.filter(branch_id=branch_id)
    opening = {r["account_id"]: (r["d"] or ZERO) - (r["c"] or ZERO) for r in
               base.filter(entry__entry_date__lt=date_from).values("account_id").annotate(d=Sum("debit"), c=Sum("credit"))}
    moves = {r["account_id"]: (r["d"] or ZERO, r["c"] or ZERO) for r in
             base.filter(entry__entry_date__gte=date_from, entry__entry_date__lte=date_to)
             .values("account_id").annotate(d=Sum("debit"), c=Sum("credit"))}
    rows, td, tc = [], ZERO, ZERO
    for acc in Account.objects.filter(legal_entity_id=legal_entity_id, is_postable=True).order_by("code"):
        op = opening.get(acc.id, ZERO)
        d, c = moves.get(acc.id, (ZERO, ZERO))
        if op == 0 and d == 0 and c == 0:
            continue
        closing = op + d - c  # signed, debit positive
        rows.append({"account_id": acc.id, "code": acc.code, "name_ar": acc.name_ar, "name_en": acc.name_en,
                     "type": acc.type, "opening": op, "debit": d, "credit": c, "closing": closing,
                     "normal_side": "debit" if acc.type in DEBIT_NORMAL else "credit"})
        td += d
        tc += c
    return {"rows": rows, "total_debit": td, "total_credit": tc, "balanced": td == tc}
