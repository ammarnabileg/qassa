"""Tips: collected with invoices (TIPS_PAYABLE), owed per employee, paid out in cash, by bank or with the salary."""
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from apps.accounting.services.posting import Line, post_entry
from apps.audit.services.log import record as audit
from apps.core.dates import accounting_date
from apps.core.errors import DomainError
from apps.core.money import money
from apps.staff.models import StaffMember, TipPayout

CREDIT = {"cash": "CASH_DRAWER", "bank": "BANK", "payroll": "SALARIES_PAYABLE"}


def owed(staff) -> Decimal:
    from apps.pos.models import Invoice
    got = Invoice.objects.filter(tip_staff=staff).aggregate(s=Sum("tip"))["s"] or 0
    paid = TipPayout.objects.filter(staff=staff).aggregate(s=Sum("amount"))["s"] or 0
    return money(got - paid)


def pay_out(*, staff, branch, amount, method, reference, user) -> TipPayout:
    from apps.pos.services.sales import open_session_for
    amount = money(amount)
    if method not in CREDIT:
        raise DomainError(code="tip_method_unknown")
    if method == "bank" and not reference.strip():
        raise DomainError(code="payment_reference_required")
    with transaction.atomic():
        StaffMember.objects.select_for_update().get(id=staff.id)
        if amount <= 0 or amount > owed(staff):
            raise DomainError(code="overpayment", details={"balance": str(owed(staff))})
        session = None
        if method == "cash":
            session = open_session_for(branch.id)
            if session is None:
                raise DomainError(code="no_open_session")
        t = TipPayout.objects.create(staff=staff, branch=branch, amount=amount, method=method, cash_session=session,
                                     reference=reference.strip(), created_by=user)
        post_entry(legal_entity_id=branch.legal_entity_id, entry_date=accounting_date(), user=user, kind="auto", branch_id=branch.id,
                   source_type="staff.tip_payout", source_id=str(t.id), event_type="tip.paid", memo=f"Tips {staff.full_name_ar} {method}",
                   lines=[Line("TIPS_PAYABLE", debit=amount, branch_id=branch.id), Line(CREDIT[method], credit=amount, branch_id=branch.id)])
        audit("staff.tips_paid", tenant_id=staff.tenant_id, actor=user, obj=t, data={"amount": str(amount), "method": method})
    return t
