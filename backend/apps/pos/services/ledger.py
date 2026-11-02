"""Accounting events of the POS (architecture §6.2, examples 1, 3, 4, 7 and §6.3 cash over/short).
These are the proposed postings pending the accountant's approval of the matrix; the accounts come from
AccountRoleMapping, never hard-coded numbers. Each event posts at most once (source_type/source_id/event_type)."""
from decimal import Decimal

from apps.accounting.services.posting import Line, post_entry
from apps.core.money import money
from apps.core.dates import accounting_date, business_date

METHOD_ROLE = {"cash": "CASH_DRAWER", "knet": "KNET_CLEARING", "transfer": "BANK", "online": "GATEWAY_CLEARING", "deposit": "CUSTOMER_DEPOSITS"}


REVENUE_ROLE = {"service": "SERVICE_REVENUE", "product": "PRODUCT_REVENUE", "package": "CONTRACT_LIABILITY_PACKAGES"}


def inv_date(inv):
    """Entry date of an invoice: when it was really issued (offline: when the sale happened on the till)."""
    return accounting_date(inv.offline_at or inv.issued_at)


def _by_role(pairs):
    out = {}
    for role, amount in pairs:
        if amount:
            out[role] = out.get(role, Decimal("0")) + amount
    return out


def post_invoice(inv, lines, user):
    """Dr AR_CUSTOMERS / Cr revenue by line kind (services, products) — or the package liability for packages sold
    (§6.2 ex. 5: collection is not revenue). Net of discounts (§6.3)."""
    if inv.total == 0:
        return None
    credits = _by_role((REVENUE_ROLE[ln.kind], ln.line_total) for ln in lines)
    return post_entry(legal_entity_id=inv.legal_entity_id, entry_date=inv_date(inv), user=user, kind="auto",
                      branch_id=inv.branch_id, source_type="pos.invoice", source_id=str(inv.id), event_type="invoice.issued",
                      memo=f"Invoice {inv.number}",
                      lines=[Line("AR_CUSTOMERS", debit=inv.total, branch_id=inv.branch_id, description=inv.number),
                             *[Line(role, credit=v, branch_id=inv.branch_id, description=inv.number) for role, v in credits.items()]])


def post_cogs(inv, lines, user):
    """Products sold: Dr COGS_PRODUCTS / Cr INVENTORY_RETAIL at the average cost taken from the stock move (§6.2 ex. 2)."""
    cost = money(sum((ln.unit_cost * ln.qty for ln in lines if ln.kind == "product"), Decimal("0")))
    if cost <= 0:
        return None
    return post_entry(legal_entity_id=inv.legal_entity_id, entry_date=inv_date(inv), user=user, kind="auto",
                      branch_id=inv.branch_id, source_type="pos.invoice", source_id=str(inv.id), event_type="invoice.cogs",
                      memo=f"COGS {inv.number}",
                      lines=[Line("COGS_PRODUCTS", debit=cost, branch_id=inv.branch_id), Line("INVENTORY_RETAIL", credit=cost, branch_id=inv.branch_id)])


def post_package_redemptions(inv, lines, user):
    """Sessions used from a package: Dr CONTRACT_LIABILITY_PACKAGES / Cr SERVICE_REVENUE at the value fixed at sale."""
    value = money(sum((ln.unit_price * ln.qty for ln in lines if ln.redeemed_package_id), Decimal("0")))
    if value <= 0:
        return None
    return post_entry(legal_entity_id=inv.legal_entity_id, entry_date=inv_date(inv), user=user, kind="auto",
                      branch_id=inv.branch_id, source_type="pos.invoice", source_id=str(inv.id), event_type="package.redeemed",
                      memo=f"Package sessions {inv.number}",
                      lines=[Line("CONTRACT_LIABILITY_PACKAGES", debit=value, branch_id=inv.branch_id),
                             Line("SERVICE_REVENUE", credit=value, branch_id=inv.branch_id)])


def post_tip(inv, user):
    """The tip is collected with the payment but is not revenue: Dr AR / Cr TIPS_PAYABLE (§6.3)."""
    return post_entry(legal_entity_id=inv.legal_entity_id, entry_date=inv_date(inv), user=user, kind="auto",
                      branch_id=inv.branch_id, source_type="pos.invoice", source_id=str(inv.id), event_type="invoice.tip",
                      memo=f"Tip {inv.number}",
                      lines=[Line("AR_CUSTOMERS", debit=inv.tip, branch_id=inv.branch_id), Line("TIPS_PAYABLE", credit=inv.tip, branch_id=inv.branch_id)])


CLEARING = {"KNET_CLEARING", "GATEWAY_CLEARING"}


def refund_lines(legal_entity_id, role, amount, on, branch_id, desc):
    """Credit side of money going back. For KNET / the gateway only what is still unsettled in the clearing account is
    taken from it; the rest was already paid to the bank, so the provider will deduct it from a later settlement:
    a liability (PSP_PAYABLE) until then (accountant's review, refunds after settlement)."""
    if role not in CLEARING:
        return [Line(role, credit=amount, branch_id=branch_id, description=desc)]
    from apps.accounting.services.finance import balance_of
    from apps.accounting.services.posting import resolve_role
    open_ = max(balance_of(legal_entity_id, resolve_role(legal_entity_id, role), on), Decimal("0"))
    from_clearing = min(amount, money(open_))
    out = [Line(role, credit=from_clearing, branch_id=branch_id, description=desc)] if from_clearing > 0 else []
    if amount - from_clearing > 0:
        out.append(Line("PSP_PAYABLE", credit=money(amount - from_clearing), branch_id=branch_id, description=f"{desc} (after settlement)"))
    return out


def post_payment(p, inv, user, on=None):
    """Receipt: Dr cash/clearing / Cr AR.  Refund: Dr AR / Cr cash/clearing (or due-to-provider after settlement)."""
    desc = f"{inv.number} {p.method}{(' ' + p.reference) if p.reference else ''}"
    day = on or accounting_date()
    if p.direction == "in":
        lines = [Line(METHOD_ROLE[p.method], debit=p.amount, branch_id=p.branch_id, description=desc),
                 Line("AR_CUSTOMERS", credit=p.amount, branch_id=p.branch_id, description=desc)]
    else:
        lines = [Line("AR_CUSTOMERS", debit=p.amount, branch_id=p.branch_id, description=desc),
                 *refund_lines(inv.legal_entity_id, METHOD_ROLE[p.method], p.amount, day, p.branch_id, desc)]
    return post_entry(legal_entity_id=inv.legal_entity_id, entry_date=day, user=user, kind="auto",
                      branch_id=p.branch_id, source_type="pos.payment", source_id=str(p.id),
                      event_type="payment.received" if p.direction == "in" else "refund.paid", memo=desc, lines=lines)


def post_credit_note(cn, inv, cn_lines, user):
    """Dr SALES_RETURNS (or the package liability for an unused package) / Cr AR_CUSTOMERS; products put back on the
    shelf: Dr INVENTORY_RETAIL / Cr COGS_PRODUCTS at their original cost (§6.2 ex. 7)."""
    debits = _by_role(("CONTRACT_LIABILITY_PACKAGES" if c.invoice_line.kind == "package" else "SALES_RETURNS", c.amount) for c in cn_lines)
    entry = post_entry(legal_entity_id=inv.legal_entity_id, entry_date=accounting_date(cn.issued_at), user=user, kind="auto",
                       branch_id=inv.branch_id, source_type="pos.credit_note", source_id=str(cn.id),
                       event_type="credit_note.issued", memo=f"Credit note {cn.number} for {inv.number}",
                       lines=[*[Line(role, debit=v, branch_id=inv.branch_id, description=cn.number) for role, v in debits.items()],
                              Line("AR_CUSTOMERS", credit=cn.total, branch_id=inv.branch_id, description=cn.number)])
    restock = money(sum((c.invoice_line.unit_cost * c.restock_qty for c in cn_lines if c.restock_qty), Decimal("0")))
    if restock > 0:
        post_entry(legal_entity_id=inv.legal_entity_id, entry_date=accounting_date(cn.issued_at), user=user, kind="auto",
                   branch_id=inv.branch_id, source_type="pos.credit_note", source_id=str(cn.id), event_type="credit_note.restock",
                   memo=f"Restock {cn.number}",
                   lines=[Line("INVENTORY_RETAIL", debit=restock, branch_id=inv.branch_id), Line("COGS_PRODUCTS", credit=restock, branch_id=inv.branch_id)])
    return entry


def post_cash_variance(session, legal_entity_id, user):
    """Shortage: Dr CASH_OVER_SHORT / Cr CASH_DRAWER. Overage: the reverse."""
    v = session.variance
    amount = abs(v)
    short = v < 0
    return post_entry(legal_entity_id=legal_entity_id, entry_date=accounting_date(session.closed_at), user=user, kind="auto",
                      branch_id=session.branch_id, source_type="pos.cash_session", source_id=str(session.id),
                      event_type="cash.variance", memo=f"Cash {'shortage' if short else 'overage'} session {session.id}",
                      lines=[Line("CASH_OVER_SHORT", branch_id=session.branch_id, **({"debit": amount} if short else {"credit": amount})),
                             Line("CASH_DRAWER", branch_id=session.branch_id, **({"credit": amount} if short else {"debit": amount}))])
