"""Staff commissions: accrued when the invoice is issued, on the service line's net amount (after discount);
package sessions count at their fixed session value. Returns reverse in proportion. Payout from the bank."""
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from apps.accounting.services.posting import Line, post_entry
from apps.core.dates import business_date
from apps.core.errors import DomainError
from apps.core.money import money
from apps.staff.models import CommissionEntry, StaffMember


def _base(line):
    return money(line.unit_price * line.qty) if line.redeemed_package_id else line.line_total


def accrue(inv, lines, user):
    total = Decimal("0")
    for ln in lines:
        if ln.kind != "service" or not ln.staff_id:
            continue
        staff = StaffMember.objects.get(id=ln.staff_id)
        if staff.commission_percent <= 0:
            continue
        base = _base(ln)
        amount = money(base * staff.commission_percent / 100)
        if amount > 0:
            CommissionEntry.objects.create(staff=staff, kind="accrual", invoice_line=ln, base=base, rate=staff.commission_percent,
                                           amount=amount, reference=inv.number)
            total += amount
    if total > 0:
        post_entry(legal_entity_id=inv.legal_entity_id, entry_date=inv.business_date, user=user, kind="auto", branch_id=inv.branch_id,
                   source_type="pos.invoice", source_id=str(inv.id), event_type="commission.accrued", memo=f"Commissions {inv.number}",
                   lines=[Line("COMMISSION_EXPENSE", debit=money(total), branch_id=inv.branch_id),
                          Line("COMMISSIONS_PAYABLE", credit=money(total), branch_id=inv.branch_id)])


def reverse(cn, cn_lines, user):
    total = Decimal("0")
    inv = cn.invoice
    for c in cn_lines:
        ln = c.invoice_line
        acc = CommissionEntry.objects.filter(invoice_line=ln, kind="accrual").first()
        if acc is None or ln.line_total == 0:
            continue
        amount = money(acc.amount * c.amount / ln.line_total)
        if amount > 0:
            CommissionEntry.objects.create(staff=acc.staff, kind="reversal", invoice_line=ln, base=c.amount, rate=acc.rate,
                                           amount=-amount, reference=cn.number)
            total += amount
    if total > 0:
        post_entry(legal_entity_id=inv.legal_entity_id, entry_date=cn.business_date, user=user, kind="auto", branch_id=inv.branch_id,
                   source_type="pos.credit_note", source_id=str(cn.id), event_type="commission.reversed", memo=f"Commissions {cn.number}",
                   lines=[Line("COMMISSIONS_PAYABLE", debit=money(total), branch_id=inv.branch_id),
                          Line("COMMISSION_EXPENSE", credit=money(total), branch_id=inv.branch_id)])


def balance(staff) -> Decimal:
    return money(CommissionEntry.objects.filter(staff=staff).aggregate(s=Sum("amount"))["s"] or 0)


def pay_out(*, staff, amount, reference, legal_entity_id, branch_id, user) -> CommissionEntry:
    amount = money(amount)
    if not reference.strip():
        raise DomainError(code="payment_reference_required")
    with transaction.atomic():
        StaffMember.objects.select_for_update().get(id=staff.id)
        if amount <= 0 or amount > balance(staff):
            raise DomainError(code="overpayment", details={"balance": str(balance(staff))})
        entry = CommissionEntry.objects.create(staff=staff, kind="payout", amount=-amount, reference=reference.strip())
        post_entry(legal_entity_id=legal_entity_id, entry_date=business_date(), user=user, kind="auto", branch_id=branch_id,
                   source_type="staff.commission_payout", source_id=str(entry.id), event_type="commission.paid",
                   memo=f"Commission payout {staff.full_name_ar} {reference}",
                   lines=[Line("COMMISSIONS_PAYABLE", debit=amount, branch_id=branch_id), Line("BANK", credit=amount, branch_id=branch_id)])
    return entry
