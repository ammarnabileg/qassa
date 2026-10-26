"""Accounting events of the POS (architecture §6.2, examples 1, 3, 4, 7 and §6.3 cash over/short).
These are the proposed postings pending the accountant's approval of the matrix; the accounts come from
AccountRoleMapping, never hard-coded numbers. Each event posts at most once (source_type/source_id/event_type)."""
from apps.accounting.services.posting import Line, post_entry
from apps.core.dates import business_date

METHOD_ROLE = {"cash": "CASH_DRAWER", "knet": "KNET_CLEARING", "transfer": "BANK"}


def post_invoice(inv, user):
    """Dr AR_CUSTOMERS / Cr SERVICE_REVENUE, net of discounts (discount reduces revenue, §6.3)."""
    return post_entry(legal_entity_id=inv.legal_entity_id, entry_date=inv.business_date, user=user, kind="auto",
                      branch_id=inv.branch_id, source_type="pos.invoice", source_id=str(inv.id), event_type="invoice.issued",
                      memo=f"Invoice {inv.number}",
                      lines=[Line("AR_CUSTOMERS", debit=inv.total, branch_id=inv.branch_id, description=inv.number),
                             Line("SERVICE_REVENUE", credit=inv.total, branch_id=inv.branch_id, description=inv.number)])


def post_payment(p, inv, user):
    """Receipt: Dr cash/clearing / Cr AR.  Refund: Dr AR / Cr cash/clearing."""
    money_side, ar_side = ("debit", "credit") if p.direction == "in" else ("credit", "debit")
    desc = f"{inv.number} {p.method}{(' ' + p.reference) if p.reference else ''}"
    return post_entry(legal_entity_id=inv.legal_entity_id, entry_date=p.business_date, user=user, kind="auto",
                      branch_id=p.branch_id, source_type="pos.payment", source_id=str(p.id),
                      event_type="payment.received" if p.direction == "in" else "refund.paid", memo=desc,
                      lines=[Line(METHOD_ROLE[p.method], branch_id=p.branch_id, description=desc, **{money_side: p.amount}),
                             Line("AR_CUSTOMERS", branch_id=p.branch_id, description=desc, **{ar_side: p.amount})])


def post_credit_note(cn, inv, user):
    """Dr SALES_RETURNS / Cr AR_CUSTOMERS."""
    return post_entry(legal_entity_id=inv.legal_entity_id, entry_date=cn.business_date, user=user, kind="auto",
                      branch_id=inv.branch_id, source_type="pos.credit_note", source_id=str(cn.id),
                      event_type="credit_note.issued", memo=f"Credit note {cn.number} for {inv.number}",
                      lines=[Line("SALES_RETURNS", debit=cn.total, branch_id=inv.branch_id, description=cn.number),
                             Line("AR_CUSTOMERS", credit=cn.total, branch_id=inv.branch_id, description=cn.number)])


def post_cash_variance(session, legal_entity_id, user):
    """Shortage: Dr CASH_OVER_SHORT / Cr CASH_DRAWER. Overage: the reverse."""
    v = session.variance
    amount = abs(v)
    short = v < 0
    return post_entry(legal_entity_id=legal_entity_id, entry_date=business_date(session.closed_at), user=user, kind="auto",
                      branch_id=session.branch_id, source_type="pos.cash_session", source_id=str(session.id),
                      event_type="cash.variance", memo=f"Cash {'shortage' if short else 'overage'} session {session.id}",
                      lines=[Line("CASH_OVER_SHORT", branch_id=session.branch_id, **({"debit": amount} if short else {"credit": amount})),
                             Line("CASH_DRAWER", branch_id=session.branch_id, **({"credit": amount} if short else {"debit": amount}))])
