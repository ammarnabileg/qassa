"""MOCI (Kuwait Ministry of Commerce) XBRL annual statements: a table in the template's order for the accountant
to transfer into the official workbook. Figures are drafts from the posted ledger, never audited figures (D-009)."""
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.db.models import Sum

from apps.accounting.models import Account, AccountRoleMapping, JournalEntry, JournalLine, XbrlMapping

ZERO = Decimal("0.000")
CATALOG = json.loads((Path(__file__).resolve().parent.parent / "moci_catalog.json").read_text(encoding="utf-8"))
TAGS = {(c["statement"], c["tag"]) for c in CATALOG}

# Default line per chart-of-accounts role; the accountant can override any account.
ROLE_DEFAULTS = {
    "CASH_DRAWER": "ifrs-full:CashAndCashEquivalents", "BANK": "ifrs-full:CashAndCashEquivalents",
    "KNET_CLEARING": "ifrs-full:TradeAndOtherReceivables", "GATEWAY_CLEARING": "ifrs-full:TradeAndOtherReceivables",
    "AR_CUSTOMERS": "ifrs-full:TradeAndOtherReceivables",
    "INVENTORY_RETAIL": "ifrs-full:Inventories", "INVENTORY_SUPPLIES": "ifrs-full:Inventories",
    "PREPAID_EXPENSES": "ifrs-full:Prepayments",
    "FIXED_ASSETS": "ifrs-full:PropertyPlantAndEquipment", "ACCUMULATED_DEPRECIATION": "ifrs-full:PropertyPlantAndEquipment",
    "AP_SUPPLIERS": "ifrs-full:TradeAndOtherPayables", "GRNI": "ifrs-full:TradeAndOtherPayables",
    "COMMISSIONS_PAYABLE": "ifrs-full:TradeAndOtherPayables", "TIPS_PAYABLE": "ifrs-full:TradeAndOtherPayables",
    "ACCRUED_EXPENSES": "ifrs-full:TradeAndOtherPayables",
    "CONTRACT_LIABILITY_PACKAGES": "ifrs-full:CurrentContractLiabilities", "CUSTOMER_DEPOSITS": "ifrs-full:CurrentContractLiabilities",
    "CUSTOMER_WALLET": "ifrs-full:CurrentContractLiabilities", "GIFT_CARDS": "ifrs-full:CurrentContractLiabilities",
    "CAPITAL": "ifrs-full:IssuedCapital", "RETAINED_EARNINGS": "ifrs-full:RetainedEarnings", "OPENING_BALANCE": "ifrs-full:RetainedEarnings",
    "SERVICE_REVENUE": "ifrs-full:RevenueFromContractsWithCustomers", "HOME_VISIT_REVENUE": "ifrs-full:RevenueFromContractsWithCustomers",
    "PRODUCT_REVENUE": "ifrs-full:RevenueFromContractsWithCustomers", "SALES_RETURNS": "ifrs-full:RevenueFromContractsWithCustomers",
    "SALES_DISCOUNTS": "ifrs-full:RevenueFromContractsWithCustomers", "OTHER_INCOME": "ifrs-full:OtherIncome",
    "COGS_PRODUCTS": "ifrs-full:CostOfSales", "COST_OF_SERVICES_SUPPLIES": "ifrs-full:CostOfSales",
    "COMMISSION_EXPENSE": "ifrs-full:EmployeeBenefitsExpense", "SALARIES": "ifrs-full:EmployeeBenefitsExpense",
    "RENT": "ifrs-full:GeneralAndAdministrativeExpense", "UTILITIES": "ifrs-full:GeneralAndAdministrativeExpense",
    "PAYMENT_FEES": "ifrs-full:GeneralAndAdministrativeExpense", "CASH_OVER_SHORT": "ifrs-full:GeneralAndAdministrativeExpense",
    "OTHER_EXPENSES": "ifrs-full:GeneralAndAdministrativeExpense",
    "DEPRECIATION_EXPENSE": "ifrs-full:DepreciationPropertyPlantAndEquipment",
    "MARKETING": "moci:SellingDistributionAndMarketingExpense",
}
FP_TYPES = {"asset", "liability", "equity"}
FP_SECTIONS = [("noncurrent_assets", "ifrs-full:NoncurrentAssets"), ("current_assets", "ifrs-full:CurrentAssets"),
               ("Equity", "ifrs-full:Equity"), ("noncurrent_liabilities", "ifrs-full:NoncurrentLiabilities"),
               ("current_liabilities", "ifrs-full:CurrentLiabilities")]


def mapping(entity_id) -> dict[int, str | None]:
    """account_id → tag (explicit mapping, else role default, else None = unmapped)."""
    by_role = {m.account_id: ROLE_DEFAULTS.get(m.role) for m in AccountRoleMapping.objects.filter(legal_entity_id=entity_id)}
    out = {a: by_role.get(a) for a in Account.objects.filter(legal_entity_id=entity_id, is_postable=True).values_list("id", flat=True)}
    out.update({m.account_id: m.tag for m in XbrlMapping.objects.filter(legal_entity_id=entity_id)})
    return out


def _sums(entity_id, **flt):
    q = JournalLine.objects.filter(entry__legal_entity_id=entity_id, entry__status=JournalEntry.Status.POSTED, **flt)
    if "entry__entry_date__gte" in flt:   # activity of a year: leave out its year-end closing entry
        q = q.exclude(entry__source_type="fiscal_year")
    q = q.values("account_id").annotate(d=Sum("debit"), c=Sum("credit"))
    return {r["account_id"]: (r["d"] or ZERO) - (r["c"] or ZERO) for r in q}


def _year(entity_id, start: date, end: date, tags, accounts):
    bal = _sums(entity_id, entry__entry_date__lte=end)                       # balances at year end
    act = _sums(entity_id, entry__entry_date__gte=start, entry__entry_date__lte=end)  # activity in the year
    fp, pl, unmapped, unclosed_pl = {}, {}, [], ZERO
    for acc in accounts:
        tag = tags.get(acc.id)
        if acc.type in FP_TYPES:
            v = bal.get(acc.id, ZERO)
            v = v if acc.type == "asset" else -v
            if v and tag:
                fp[tag] = fp.get(tag, ZERO) + v
            elif v:
                unmapped.append(acc)
        else:
            unclosed_pl += -bal.get(acc.id, ZERO)                            # P&L not yet closed to retained earnings
            v = -act.get(acc.id, ZERO)                                       # income positive, expense negative
            if v and tag:
                pl[tag] = pl.get(tag, ZERO) + v
            elif v:
                unmapped.append(acc)
    if unclosed_pl:
        fp["ifrs-full:RetainedEarnings"] = fp.get("ifrs-full:RetainedEarnings", ZERO) + unclosed_pl
    return fp, pl, unmapped


def report(entity, year_end: date) -> dict:
    cy = (date(year_end.year - 1, year_end.month, year_end.day) if not (year_end.month == 2 and year_end.day == 29)
          else date(year_end.year - 1, 2, 28))
    py = date(cy.year - 1, cy.month, cy.day) if not (cy.month == 2 and cy.day == 29) else date(cy.year - 1, 2, 28)
    from datetime import timedelta
    periods = {"cy": (cy + timedelta(days=1), year_end), "py": (py + timedelta(days=1), cy)}
    tags = mapping(entity.id)
    accounts = list(Account.objects.filter(legal_entity_id=entity.id, is_postable=True).order_by("code"))
    data = {k: _year(entity.id, s, e, tags, accounts) for k, (s, e) in periods.items()}

    def line(c, src):
        return {"tag": c["tag"], "label_ar": c["label_ar"], "section": c["section"],
                "cy": str(src["cy"].get(c["tag"], ZERO)), "py": str(src["py"].get(c["tag"], ZERO))}

    fp_vals = {k: data[k][0] for k in data}
    pl_vals = {k: data[k][1] for k in data}
    fp_lines, totals = [], {k: {} for k in data}
    for section, total_tag in FP_SECTIONS:
        items = [c for c in CATALOG if c["statement"] == "fp" and c["section"] == section]
        fp_lines += [line(c, fp_vals) for c in items]
        for k in data:
            totals[k][total_tag] = sum((fp_vals[k].get(c["tag"], ZERO) for c in items), ZERO)
    for k in data:
        t = totals[k]
        t["ifrs-full:Assets"] = t["ifrs-full:NoncurrentAssets"] + t["ifrs-full:CurrentAssets"]
        t["ifrs-full:Liabilities"] = t["ifrs-full:NoncurrentLiabilities"] + t["ifrs-full:CurrentLiabilities"]
        t["ifrs-full:EquityAndLiabilities"] = t["ifrs-full:Liabilities"] + t["ifrs-full:Equity"]
        rev = sum((v for tg, v in pl_vals[k].items() if ("pl", tg) in TAGS and
                   next(c["section"] for c in CATALOG if c["statement"] == "pl" and c["tag"] == tg) == "revenue"), ZERO)
        t["ifrs-full:Revenue"] = rev
        t["ifrs-full:ProfitLoss"] = sum(pl_vals[k].values(), ZERO)
    pl_lines = [line(c, pl_vals) for c in CATALOG if c["statement"] == "pl"]

    checks = []
    for k in data:
        t = totals[k]
        checks.append({"id": f"VAL_BS_EQUATION_{k.upper()}", "ok": t["ifrs-full:Assets"] == t["ifrs-full:EquityAndLiabilities"],
                       "values": [str(t["ifrs-full:Assets"]), str(t["ifrs-full:EquityAndLiabilities"])]})
    unmapped = {a.id: a for k in data for a in data[k][2]}
    checks.append({"id": "ALL_ACCOUNTS_MAPPED", "ok": not unmapped, "values": [f"{a.code} {a.name_ar}" for a in unmapped.values()]})
    return {
        "year_end": year_end.isoformat(), "prior_year_end": cy.isoformat(),
        "periods": {k: [s.isoformat(), e.isoformat()] for k, (s, e) in periods.items()},
        "financial_position": [x for x in fp_lines if x["cy"] != "0.000" or x["py"] != "0.000"],
        "profit_or_loss": [x for x in pl_lines if x["cy"] != "0.000" or x["py"] != "0.000"],
        "totals": [{"tag": tg, "cy": str(totals["cy"][tg]), "py": str(totals["py"][tg])} for tg in totals["cy"]],
        "checks": checks,
        "cash_flows": None,  # needs the accountant's classification of cash movements (D-009); not generated
        "draft": True,
    }
