"""Phase 5: expenses and accruals, fixed assets and depreciation, clearing settlements, statements,
year-end closing and frozen report versions. Every posting is a proposal under the accountant's policies (D-011)."""
import hashlib
import json
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Sum

from apps.accounting.models import (Account, ClearingSettlement, Expense, FiscalPeriod, FiscalYear, FixedAsset, JournalEntry, JournalLine,
                                    ReportVersion)
from apps.accounting.services.posting import DuplicatePosting, Line, post_entry, resolve_role
from apps.audit.services.log import record as audit
from apps.core.errors import DomainError
from apps.core.money import money

ZERO = Decimal("0.000")
CLOSING = "fiscal_year"   # source_type of year-end closing entries (excluded from period activity)
PAY_ROLE = {"bank": "BANK", "cash": "CASH_DRAWER", "accrued": "ACCRUED_EXPENSES"}


def _q3(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


# ---------- expenses ----------
def record_expense(*, entity, branch, expense_date: date, account: Account, amount, paid_from: str, description: str,
                   reference: str, user) -> Expense:
    amount = money(amount)
    if amount <= 0:
        raise DomainError(code="amount_invalid")
    if account.legal_entity_id != entity.id or account.type != "expense" or not account.is_postable or account.is_control:
        raise DomainError(code="expense_account_invalid")
    if paid_from == "cash" and branch is None:
        raise DomainError(code="branch_required")
    with transaction.atomic():
        e = Expense.objects.create(legal_entity=entity, branch=branch, expense_date=expense_date, account=account, amount=amount,
                                   paid_from=paid_from, description=description, reference=reference, created_by=user,
                                   paid_on=expense_date if paid_from != "accrued" else None)
        post_entry(legal_entity_id=entity.id, entry_date=expense_date, branch_id=branch.id if branch else None, kind="auto",
                   source_type="expense", source_id=str(e.id), event_type="recorded", user=user, memo=description,
                   lines=[Line(account, debit=amount, description=description), Line(PAY_ROLE[paid_from], credit=amount)])
        audit("expense.recorded", tenant_id=e.tenant_id, actor=user, obj=e, data={"amount": str(amount), "paid_from": paid_from})
    return e


def pay_accrued(expense: Expense, *, paid_on: date, reference: str, user) -> Expense:
    if not reference.strip():
        raise DomainError(code="payment_reference_required")
    with transaction.atomic():
        e = Expense.objects.select_for_update().get(id=expense.id)
        if e.paid_from != Expense.PaidFrom.ACCRUED or e.paid_on:
            raise DomainError(code="expense_not_accrued")
        e.paid_on, e.paid_reference = paid_on, reference.strip()
        e.save(update_fields=["paid_on", "paid_reference"])
        post_entry(legal_entity_id=e.legal_entity_id, entry_date=paid_on, branch_id=e.branch_id, kind="auto",
                   source_type="expense", source_id=str(e.id), event_type="paid", user=user, memo=f"{e.description} — {reference}",
                   lines=[Line("ACCRUED_EXPENSES", debit=e.amount), Line("BANK", credit=e.amount)])
    return e


# ---------- fixed assets (example 12) ----------
def add_asset(*, entity, branch, name: str, acquired_on: date, cost, residual_value, life_months: int, paid_from: str,
              reference: str, user, in_service_on: date | None = None) -> FixedAsset:
    cost, residual = money(cost), money(residual_value or 0)
    if cost <= 0 or residual < 0 or residual >= cost or life_months <= 0:
        raise DomainError(code="asset_values_invalid")
    in_service_on = in_service_on or acquired_on
    if in_service_on < acquired_on:
        raise DomainError(code="asset_in_service_before_purchase")
    with transaction.atomic():
        a = FixedAsset.objects.create(legal_entity=entity, branch=branch, name=name, acquired_on=acquired_on, in_service_on=in_service_on, cost=cost,
                                      residual_value=residual, life_months=life_months, paid_from=paid_from, reference=reference,
                                      created_by=user)
        post_entry(legal_entity_id=entity.id, entry_date=acquired_on, branch_id=branch.id if branch else None, kind="auto",
                   source_type="asset", source_id=str(a.id), event_type="acquired", user=user, memo=name,
                   lines=[Line("FIXED_ASSETS", debit=cost, description=name),
                          Line("BANK" if paid_from == "bank" else "AP_SUPPLIERS", credit=cost)])
        audit("asset.added", tenant_id=a.tenant_id, actor=user, obj=a, data={"cost": str(cost)})
    return a


def _months_between(a: date, b: date) -> int:
    return (b.year - a.year) * 12 + b.month - a.month


def depreciation_for(asset: FixedAsset, month: date) -> Decimal:
    """Straight line, monthly, starting with the month the asset is ready for use (in_service_on; older assets without
    it: the month after acquisition, as before). The last month absorbs rounding."""
    start = asset.in_service_on
    n = (_months_between(start, month) + 1) if start else _months_between(asset.acquired_on, month)   # 1 = first month depreciated
    if n < 1 or n > asset.life_months or (asset.disposed_on and asset.disposed_on < month):
        return ZERO
    base = asset.cost - asset.residual_value
    monthly = _q3(base / asset.life_months)
    return base - monthly * (asset.life_months - 1) if n == asset.life_months else monthly


def accumulated(asset: FixedAsset, upto: date) -> Decimal:
    return (JournalLine.objects.filter(entry__source_type="asset", entry__source_id=str(asset.id),
                                       entry__event_type__startswith="dep:", entry__entry_date__lte=upto,
                                       entry__status=JournalEntry.Status.POSTED, credit__gt=0)
            .aggregate(s=Sum("credit"))["s"] or ZERO)


def run_depreciation(entity, month: date, user) -> dict:
    """Post the month's depreciation for every asset (idempotent: one entry per asset and month)."""
    month = month.replace(day=1)
    end = (month.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    posted, skipped, total = 0, 0, ZERO
    for a in FixedAsset.objects.filter(legal_entity=entity, acquired_on__lt=month):
        amount = depreciation_for(a, month)
        if amount <= 0:
            continue
        try:
            post_entry(legal_entity_id=entity.id, entry_date=end, branch_id=a.branch_id, kind="auto", source_type="asset",
                       source_id=str(a.id), event_type=f"dep:{month:%Y-%m}", user=user, memo=f"{a.name} — {month:%Y-%m}",
                       lines=[Line("DEPRECIATION_EXPENSE", debit=amount), Line("ACCUMULATED_DEPRECIATION", credit=amount)])
            posted += 1
            total += amount
        except DuplicatePosting:
            skipped += 1
    return {"month": f"{month:%Y-%m}", "posted": posted, "already_posted": skipped, "total": str(total)}


# ---------- clearing settlement (example 11) ----------
def balance_of(entity_id, account: Account, upto: date | None = None) -> Decimal:
    q = JournalLine.objects.filter(account=account, entry__status=JournalEntry.Status.POSTED, entry__legal_entity_id=entity_id)
    if upto:
        q = q.filter(entry__entry_date__lte=upto)
    s = q.aggregate(d=Sum("debit"), c=Sum("credit"))
    return (s["d"] or ZERO) - (s["c"] or ZERO)


def settle_clearing(*, entity, channel: str, settled_on: date, gross, fees, reference: str, user, refunds=0) -> ClearingSettlement:
    """Provider settlement: gross sales cleared, less fees, less refunds it deducted for refunds made after an earlier
    settlement (those sit in PSP_PAYABLE). Bank receives gross - fees - refunds."""
    gross, fees, refunds = money(gross), money(fees or 0), money(refunds or 0)
    if gross <= 0 or fees < 0 or refunds < 0 or fees + refunds >= gross:
        raise DomainError(code="settlement_values_invalid")
    if refunds > 0:
        owed = -balance_of(entity.id, resolve_role(entity.id, "PSP_PAYABLE"), settled_on)
        if refunds > owed:
            raise DomainError(code="settlement_refunds_exceed", details={"owed": str(owed)})
    role = "KNET_CLEARING" if channel == "knet" else "GATEWAY_CLEARING"
    acc = resolve_role(entity.id, role)
    with transaction.atomic():
        open_balance = balance_of(entity.id, acc, settled_on)
        if gross > open_balance:
            raise DomainError(code="settlement_exceeds_clearing", details={"open": str(open_balance)})
        s = ClearingSettlement.objects.create(legal_entity=entity, channel=channel, settled_on=settled_on, gross=gross,
                                              fees=fees, reference=reference, created_by=user)
        lines = [Line("BANK", debit=gross - fees - refunds, description=reference)]
        if fees:
            lines.append(Line("PAYMENT_FEES", debit=fees))
        if refunds:
            lines.append(Line("PSP_PAYABLE", debit=refunds, description="refunds deducted by the provider"))
        lines.append(Line(role, credit=gross))
        post_entry(legal_entity_id=entity.id, entry_date=settled_on, kind="auto", source_type="settlement", source_id=str(s.id),
                   event_type="settled", user=user, memo=f"{channel} settlement {reference}", lines=lines)
    return s


def clearing_status(entity) -> list[dict]:
    """What is still in each clearing account: collected but not yet settled (or unexplained differences)."""
    out = []
    for channel, role in (("knet", "KNET_CLEARING"), ("gateway", "GATEWAY_CLEARING")):
        acc = resolve_role(entity.id, role)
        out.append({"channel": channel, "account": acc.code, "open_balance": str(balance_of(entity.id, acc)),
                    "last_settlement": ClearingSettlement.objects.filter(legal_entity=entity, channel=channel)
                    .values_list("settled_on", flat=True).first()})
    return out


# ---------- statements ----------
def _activity(entity_id, d_from, d_to, branch_id=None, exclude_closing=True):
    q = JournalLine.objects.filter(entry__legal_entity_id=entity_id, entry__status=JournalEntry.Status.POSTED,
                                   entry__entry_date__gte=d_from, entry__entry_date__lte=d_to)
    if exclude_closing:   # closing entries and their reversals (a reopened year) are not the year's activity
        q = q.exclude(entry__source_type=CLOSING).exclude(entry__reversal_of__source_type=CLOSING)
    if branch_id:
        q = q.filter(branch_id=branch_id)
    return {r["account_id"]: (r["d"] or ZERO) - (r["c"] or ZERO) for r in q.values("account_id").annotate(d=Sum("debit"), c=Sum("credit"))}


def _balances(entity_id, as_of):
    q = JournalLine.objects.filter(entry__legal_entity_id=entity_id, entry__status=JournalEntry.Status.POSTED,
                                   entry__entry_date__lte=as_of)
    return {r["account_id"]: (r["d"] or ZERO) - (r["c"] or ZERO) for r in q.values("account_id").annotate(d=Sum("debit"), c=Sum("credit"))}


def _rows(accounts, values, sign):
    rows = [{"account_id": a.id, "code": a.code, "name_ar": a.name_ar, "name_en": a.name_en, "amount": sign * values.get(a.id, ZERO)}
            for a in accounts if values.get(a.id)]
    return rows, sum((r["amount"] for r in rows), ZERO)


def income_statement(entity, d_from: date, d_to: date, branch_id=None) -> dict:
    act = _activity(entity.id, d_from, d_to, branch_id)
    accs = list(Account.objects.filter(legal_entity=entity, is_postable=True).order_by("code"))
    revenue, rev_total = _rows([a for a in accs if a.type == "revenue"], act, -1)
    expenses, exp_total = _rows([a for a in accs if a.type == "expense"], act, 1)
    cogs_codes = {resolve_role(entity.id, r).id for r in ("COGS_PRODUCTS", "COST_OF_SERVICES_SUPPLIES")}
    direct = sum((r["amount"] for r in expenses if r["account_id"] in cogs_codes), ZERO)
    out = {"from": d_from.isoformat(), "to": d_to.isoformat(), "branch_id": branch_id,
           "revenue": revenue, "total_revenue": rev_total, "expenses": expenses, "total_expenses": exp_total,
           "gross_profit": rev_total - direct, "net_profit": rev_total - exp_total}
    return _stringify(out)


def balance_sheet(entity, as_of: date) -> dict:
    bal = _balances(entity.id, as_of)
    accs = list(Account.objects.filter(legal_entity=entity, is_postable=True).order_by("code"))
    assets, ta = _rows([a for a in accs if a.type == "asset"], bal, 1)
    liabilities, tl = _rows([a for a in accs if a.type == "liability"], bal, -1)
    equity, te = _rows([a for a in accs if a.type == "equity"], bal, -1)
    unclosed = -sum((bal.get(a.id, ZERO) for a in accs if a.type in ("revenue", "expense")), ZERO)
    out = {"as_of": as_of.isoformat(), "assets": assets, "total_assets": ta, "liabilities": liabilities, "total_liabilities": tl,
           "equity": equity, "unclosed_profit": unclosed, "total_equity": te + unclosed,
           "balanced": ta == tl + te + unclosed}
    return _stringify(out)


def _stringify(v):
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, dict):
        return {k: _stringify(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_stringify(x) for x in v]
    return v


# ---------- year-end closing ----------
def active_closing(fy: FiscalYear):
    """The year's closing entry that is in force (not reversed), if any."""
    return (JournalEntry.objects.filter(legal_entity_id=fy.legal_entity_id, source_type=CLOSING, status=JournalEntry.Status.POSTED,
                                        entry_date=fy.end_date, reversal_of__isnull=True)
            .exclude(reversed_by__isnull=False).filter(source_id__startswith=str(fy.id)).order_by("-id").first())


def _closing_lines(fy):
    act = _activity(fy.legal_entity_id, fy.start_date, fy.end_date)
    accs = Account.objects.filter(legal_entity_id=fy.legal_entity_id, is_postable=True, type__in=["revenue", "expense"]).order_by("code")
    lines, net, preview = [], ZERO, []
    for a in accs:
        v = act.get(a.id, ZERO)
        if v > 0:
            lines.append(Line(a, credit=v))
        elif v < 0:
            lines.append(Line(a, debit=-v))
        if v:
            preview.append({"code": a.code, "name_ar": a.name_ar, "name_en": a.name_en, "debit": str(-v if v < 0 else ZERO), "credit": str(v if v > 0 else ZERO)})
        net += v
    if net > 0:      # debit balance overall = loss
        lines.append(Line("RETAINED_EARNINGS", debit=net, description="loss for the year"))
    elif net < 0:
        lines.append(Line("RETAINED_EARNINGS", credit=-net, description="profit for the year"))
    return lines, net, preview


def closing_preview(fy: FiscalYear) -> dict:
    """What closing would post, without posting: each P&L account, and the profit (or loss) going to retained earnings."""
    lines, net, preview = _closing_lines(fy)
    return {"year": fy.name, "date": fy.end_date.isoformat(), "lines": preview, "result": str(-net),
            "outcome": "profit" if net < 0 else "loss" if net > 0 else "nil", "closed": active_closing(fy) is not None,
            "open_periods": fy.periods.filter(status="open").count()}


def close_year(fy: FiscalYear, user, *, period_checks=()) -> JournalEntry:
    """Move the year's revenue and expense balances to retained earnings on the last day, then close every period of
    the year in the same transaction — so nothing can be posted into a closed year afterwards. Reopening the year
    reverses the closing entry (reopen_year)."""
    from apps.accounting.services.ledger import close_period
    with transaction.atomic():
        FiscalYear.objects.select_for_update().get(id=fy.id)
        if active_closing(fy) is not None:
            raise DomainError(code="year_already_closed")
        lines, net, _ = _closing_lines(fy)
        if not lines:
            raise DomainError(code="nothing_to_close")
        attempt = JournalEntry.objects.filter(legal_entity_id=fy.legal_entity_id, source_type=CLOSING, source_id__startswith=str(fy.id)).count()
        je = post_entry(legal_entity_id=fy.legal_entity_id, entry_date=fy.end_date, kind="auto", source_type=CLOSING,
                        source_id=str(fy.id) if attempt == 0 else f"{fy.id}:{attempt + 1}", event_type="closing", user=user,
                        memo=f"Year-end closing {fy.name}", lines=lines)
        for p in fy.periods.filter(status="open").order_by("number"):
            close_period(p, user, pending_checks=list(period_checks))   # a blocked period undoes the whole close
    audit("fiscal_year.closed", tenant_id=fy.tenant_id, actor=user, obj=fy, data={"entry": je.number, "result": str(-net)})
    return je


def reopen_year(fy: FiscalYear, user, reason: str) -> JournalEntry:
    """Undo a year-end close: reopen the last period and reverse the closing entry (kept, with its reversal). Late
    entries can then be posted and the year closed again from fresh balances."""
    from apps.accounting.services.posting import reverse_entry
    if not reason.strip():
        raise DomainError(code="reason_required")
    with transaction.atomic():
        FiscalYear.objects.select_for_update().get(id=fy.id)
        je = active_closing(fy)
        if je is None:
            raise DomainError(code="year_not_closed")
        last = fy.periods.order_by("-number").first()
        FiscalPeriod.objects.filter(id=last.id).update(status=FiscalPeriod.Status.OPEN, closed_at=None, closed_by=None)
        rev = reverse_entry(je, on=fy.end_date, user=user, reason=reason)
    audit("fiscal_year.reopened", tenant_id=fy.tenant_id, actor=user, obj=fy, reason=reason, data={"reversed": je.number})
    return rev


# ---------- frozen versions ----------
def freeze(*, entity, kind: str, params: dict, data: dict, note: str, user) -> ReportVersion:
    blob = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    rv = ReportVersion.objects.create(legal_entity=entity, kind=kind, params=params, data=data,
                                      sha256=hashlib.sha256(blob.encode()).hexdigest(), note=note, created_by=user)
    audit("report.frozen", tenant_id=rv.tenant_id, actor=user, obj=rv, data={"kind": kind, "sha256": rv.sha256})
    return rv


def verify(rv: ReportVersion) -> bool:
    blob = json.dumps(rv.data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest() == rv.sha256
