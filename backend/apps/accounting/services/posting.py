"""The only way to write to the general ledger.

Rules enforced here (and again by database constraints/triggers):
- at least two lines, each strictly debit or credit, amounts are Decimal with 3 places (no floats);
- total debit == total credit;
- accounts belong to the entry's legal entity, are active and postable;
- control accounts (AR/AP/inventory…) cannot be used by manual entries;
- the period containing the date is open;
- a (source_type, source_id, event_type) is posted at most once;
- posted entries are immutable: corrections are reversals.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounting.models import Account, AccountRoleMapping, FiscalPeriod, JournalEntry, JournalLine
from apps.audit.services.log import record as audit
from apps.core.errors import ConflictError, DomainError
from apps.core.money import money
from apps.core.services.infra import next_number

ZERO = Decimal("0.000")


@dataclass
class Line:
    account: Account | str  # Account instance, or an account role such as "CASH_DRAWER"
    debit: Decimal | str = ZERO
    credit: Decimal | str = ZERO
    description: str = ""
    branch_id: int | None = None


class DuplicatePosting(ConflictError):
    code = "duplicate_posting"


def resolve_role(legal_entity_id, role: str) -> Account:
    m = AccountRoleMapping.objects.select_related("account").filter(legal_entity_id=legal_entity_id, role=role).first()
    if m is None:
        raise DomainError(f"No account mapped for role {role}", code="account_role_unmapped", details={"role": role})
    return m.account


def find_open_period(legal_entity_id, on: date, lock=False) -> FiscalPeriod:
    qs = FiscalPeriod.objects.filter(legal_entity_id=legal_entity_id, start_date__lte=on, end_date__gte=on)
    if lock:
        qs = qs.select_for_update()  # serialises with close_period()
    period = qs.first()
    if period is None:
        raise DomainError("No fiscal period covers this date", code="no_fiscal_period", details={"date": str(on)})
    if period.status != FiscalPeriod.Status.OPEN:
        raise DomainError("The fiscal period is closed", code="period_closed", details={"period": period.id})
    return period


def post_entry(*, legal_entity_id: int, entry_date: date, lines: list[Line], memo="", user=None, branch_id=None,
               kind="manual", source_type="", source_id="", event_type="", reversal_of=None) -> JournalEntry:
    if len(lines) < 2:
        raise DomainError("A journal entry needs at least two lines", code="je_too_few_lines")
    if (source_type or source_id or event_type) and not (source_type and source_id and event_type):
        raise DomainError("source_type, source_id and event_type go together", code="je_bad_source")

    norm = []
    for i, ln in enumerate(lines, start=1):
        d, c = money(ln.debit), money(ln.credit)
        if d < 0 or c < 0 or (d == 0) == (c == 0):
            raise DomainError("Each line must be either a positive debit or a positive credit",
                              code="je_bad_line", details={"line": i})
        norm.append((i, ln, d, c))
    total_d = sum((d for _, _, d, _ in norm), ZERO)
    total_c = sum((c for _, _, _, c in norm), ZERO)
    if total_d != total_c:
        raise DomainError("Debits and credits are not equal", code="je_unbalanced",
                          details={"debit": str(total_d), "credit": str(total_c)})

    try:
        with transaction.atomic():
            period = find_open_period(legal_entity_id, entry_date, lock=True)
            entry = JournalEntry.objects.create(
                legal_entity_id=legal_entity_id, branch_id=branch_id, period=period, entry_date=entry_date,
                kind=kind, source_type=source_type, source_id=str(source_id), event_type=event_type, memo=memo,
                created_by=user, status=JournalEntry.Status.DRAFT, reversal_of=reversal_of)
            for i, ln, d, c in norm:
                acc = resolve_role(legal_entity_id, ln.account) if isinstance(ln.account, str) else ln.account
                acc = Account.objects.get(pk=acc.pk)  # re-read inside the tenant scope
                if acc.legal_entity_id != legal_entity_id:
                    raise DomainError("Account belongs to another legal entity", code="je_account_entity",
                                      details={"line": i})
                if not acc.is_active or not acc.is_postable:
                    raise DomainError("Account is not postable", code="je_account_not_postable",
                                      details={"line": i, "account": acc.code})
                if kind == "manual" and acc.is_control:
                    raise DomainError("Control accounts accept system postings only", code="je_control_account",
                                      details={"line": i, "account": acc.code})
                JournalLine.objects.create(entry=entry, line_no=i, account=acc, debit=d, credit=c,
                                           description=ln.description[:255], branch_id=ln.branch_id or branch_id)
            year = period.fiscal_year.name
            entry.number = f"JE-{year}-{next_number(entry.tenant_id, f'je:{legal_entity_id}:{year}'):06d}"
            entry.status, entry.posted_by, entry.posted_at = JournalEntry.Status.POSTED, user, timezone.now()
            entry.save()
            audit("journal.posted", tenant_id=entry.tenant_id, actor=user, obj=entry,
                  data={"number": entry.number, "debit": str(total_d), "source": [source_type, str(source_id), event_type]})
            return entry
    except IntegrityError as exc:
        if "uniq_je_source_event" in str(exc):
            raise DuplicatePosting("This event was already posted",
                                   details={"source_type": source_type, "source_id": str(source_id),
                                            "event_type": event_type}) from exc
        raise


def reverse_entry(entry: JournalEntry, *, on: date, user=None, reason="") -> JournalEntry:
    if not reason:
        raise DomainError("A reason is required to reverse an entry", code="reason_required")
    if entry.status != JournalEntry.Status.POSTED:
        raise DomainError("Only posted entries can be reversed", code="je_not_posted")
    if entry.reversal_of_id is not None:
        raise DomainError("A reversal cannot itself be reversed; post a new entry", code="je_reverse_reversal")
    if JournalEntry.objects.filter(reversal_of=entry).exists():
        raise ConflictError("Entry already reversed", code="je_already_reversed")
    lines = [Line(account=l.account, debit=l.credit, credit=l.debit, description=f"Reversal: {l.description}"[:255],
                  branch_id=l.branch_id) for l in entry.lines.all().order_by("line_no")]
    with transaction.atomic():
        rev = post_entry(legal_entity_id=entry.legal_entity_id, entry_date=on, lines=lines, user=user,
                         branch_id=entry.branch_id, kind="auto" if entry.kind == "auto" else "reversal",
                         memo=f"Reversal of {entry.number}: {reason}",
                         source_type="accounting.journal_entry", source_id=str(entry.pk), event_type="reversed",
                         reversal_of=entry)
        audit("journal.reversed", tenant_id=entry.tenant_id, actor=user, obj=entry, reason=reason,
              data={"reversal": rev.number})
        return rev
