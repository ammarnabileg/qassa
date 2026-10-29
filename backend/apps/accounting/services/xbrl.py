"""MOCI (Kuwait Ministry of Commerce) XBRL annual statements: a table in the template's order for the accountant
to transfer into the official workbook. Figures are drafts from the posted ledger, never audited figures (D-009)."""
import json
from datetime import date, timedelta
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


# Working-capital line for a current asset / liability, by its balance-sheet line (indirect method).
WC_TAG = {
    "ifrs-full:Inventories": "ifrs-full:AdjustmentsForDecreaseIncreaseInInventories",
    "ifrs-full:TradeAndOtherReceivables": "moci:ChangesInOtherOperatingReceivables",
    "ifrs-full:Prepayments": "moci:AdjustmentsForDecreaseIncreaseInOtherOperatingAssets",
    "ifrs-full:TradeAndOtherPayables": "moci:ChangesInOtherOperatingPayables",
    "ifrs-full:CurrentContractLiabilities": "moci:AdjustmentsForIncreaseDecreaseInAdvancesFromCustomers",
}
CF_OTHER = {"current_assets": "moci:AdjustmentsForDecreaseIncreaseInOtherOperatingAssets",
            "current_liabilities": "ifrs-full:AdjustmentsForIncreaseDecreaseInOtherOperatingPayables",
            "noncurrent_assets": "ifrs-full:PurchaseOfOtherLongtermAssetsClassifiedAsInvestingActivities",
            "noncurrent_liabilities": "ifrs-full:OtherInflowsOutflowsOfCashClassifiedAsFinancingActivities",
            "Equity": "ifrs-full:OtherInflowsOutflowsOfCashClassifiedAsFinancingActivities"}
FP_SECTION = {c["tag"]: c["section"] for c in CATALOG if c["statement"] == "fp"}
CASH = "ifrs-full:CashAndCashEquivalents"
DEP = "moci:AdjustmentsForDepreciationOnPropertyPlantAndEquipment"
PPE_BUY = "ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"


def _bal_no_closing(entity_id, upto):
    q = (JournalLine.objects.filter(entry__legal_entity_id=entity_id, entry__status=JournalEntry.Status.POSTED,
                                    entry__entry_date__lte=upto).exclude(entry__source_type="fiscal_year")
         .values("account_id").annotate(d=Sum("debit"), c=Sum("credit")))
    return {r["account_id"]: (r["d"] or ZERO) - (r["c"] or ZERO) for r in q}


def _cash_flow(entity_id, start, end, tags, accounts, profit):
    """Indirect method from balance-sheet movements (closing entries left out). A draft: the accountant
    checks the classification (e.g. an asset bought on credit is not an investing cash outflow)."""
    from apps.accounting.models import AccountRoleMapping
    dep_ids = set(AccountRoleMapping.objects.filter(legal_entity_id=entity_id, role="ACCUMULATED_DEPRECIATION")
                  .values_list("account_id", flat=True))
    before = _bal_no_closing(entity_id, start - timedelta(days=1))
    after = _bal_no_closing(entity_id, end)
    lines, cash_open, cash_close, unknown = {}, ZERO, ZERO, []
    for a in accounts:
        if a.type not in FP_TYPES:
            continue
        tag = tags.get(a.id)
        delta = after.get(a.id, ZERO) - before.get(a.id, ZERO)       # debit-positive movement
        if tag == CASH:
            cash_open += before.get(a.id, ZERO)
            cash_close += after.get(a.id, ZERO)
            continue
        if not delta:
            continue
        if a.id in dep_ids:
            cf = DEP                                                   # non-cash: added back
        elif tag == "ifrs-full:PropertyPlantAndEquipment":
            cf = PPE_BUY
        elif tag in WC_TAG:
            cf = WC_TAG[tag]
        elif tag in FP_SECTION:
            cf = CF_OTHER[FP_SECTION[tag]]
        else:
            unknown.append(a)
            continue
        lines[cf] = lines.get(cf, ZERO) - delta                       # more assets = cash out; more liabilities = cash in
    sections = {"operating": profit + sum((v for k, v in lines.items() if _cf_section(k) in ("adjustments", "working_capital", "operating_other")), ZERO),
                "investing": sum((v for k, v in lines.items() if _cf_section(k) == "investing"), ZERO),
                "financing": sum((v for k, v in lines.items() if _cf_section(k) == "financing"), ZERO)}
    net = sections["operating"] + sections["investing"] + sections["financing"]
    return lines, sections, net, cash_open, cash_close, unknown


def _cf_section(tag):
    return next((c["section"] for c in CATALOG if c["statement"] == "cf" and c["tag"] == tag), "")


def _equity_changes(entity_id, start, end, tags, accounts, profit):
    """Opening, profit for the year, other movements and closing per equity line (closing entries left out)."""
    before = _bal_no_closing(entity_id, start - timedelta(days=1))
    after = _bal_no_closing(entity_id, end)
    rows = {}
    pl_before = -sum((before.get(a.id, ZERO) for a in accounts if a.type in ("revenue", "expense")), ZERO)
    for a in accounts:
        if a.type != "equity":
            continue
        tag = tags.get(a.id) or "ifrs-full:OtherEquityInterest"
        r = rows.setdefault(tag, {"opening": ZERO, "profit": ZERO, "other": ZERO, "closing": ZERO})
        r["opening"] += -before.get(a.id, ZERO)
        r["closing"] += -after.get(a.id, ZERO)
    re = rows.setdefault("ifrs-full:RetainedEarnings", {"opening": ZERO, "profit": ZERO, "other": ZERO, "closing": ZERO})
    re["opening"] += pl_before                                          # earlier years' unclosed results
    re["profit"] = profit
    re["closing"] += pl_before + profit
    for r in rows.values():
        r["other"] = r["closing"] - r["opening"] - r["profit"]
    return rows


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

    cf, soce = {}, {}
    for k, (st, en) in periods.items():
        cf[k] = _cash_flow(entity.id, st, en, tags, accounts, totals[k]["ifrs-full:ProfitLoss"])
        soce[k] = _equity_changes(entity.id, st, en, tags, accounts, totals[k]["ifrs-full:ProfitLoss"])
    cf_lines = [{"tag": "ifrs-full:ProfitLoss", "label_ar": "ربح (خسارة) السنة", "section": "profit",
                 "cy": str(totals["cy"]["ifrs-full:ProfitLoss"]), "py": str(totals["py"]["ifrs-full:ProfitLoss"])}]
    cf_lines += [{"tag": c["tag"], "label_ar": c["label_ar"], "section": c["section"],
                  "cy": str(cf["cy"][0].get(c["tag"], ZERO)), "py": str(cf["py"][0].get(c["tag"], ZERO))}
                 for c in CATALOG if c["statement"] == "cf" and (cf["cy"][0].get(c["tag"]) or cf["py"][0].get(c["tag"]))]
    cf_totals = [{"tag": t, "cy": str(v_cy), "py": str(v_py)} for t, v_cy, v_py in (
        ("ifrs-full:CashFlowsFromUsedInOperatingActivities", cf["cy"][1]["operating"], cf["py"][1]["operating"]),
        ("ifrs-full:CashFlowsFromUsedInInvestingActivities", cf["cy"][1]["investing"], cf["py"][1]["investing"]),
        ("ifrs-full:CashFlowsFromUsedInFinancingActivities", cf["cy"][1]["financing"], cf["py"][1]["financing"]),
        ("ifrs-full:IncreaseDecreaseInCashAndCashEquivalents", cf["cy"][2], cf["py"][2]),
        ("cash_start", cf["cy"][3], cf["py"][3]), ("cash_end", cf["cy"][4], cf["py"][4]))]
    soce_out = {k: [{"tag": tg, "label_ar": next((c["label_ar"] for c in CATALOG if c["tag"] == tg), tg),
                     **{f: str(v) for f, v in r.items()}} for tg, r in soce[k].items() if any(r.values())] for k in soce}

    checks = []
    for k in data:
        t = totals[k]
        checks.append({"id": f"VAL_BS_EQUATION_{k.upper()}", "ok": t["ifrs-full:Assets"] == t["ifrs-full:EquityAndLiabilities"],
                       "values": [str(t["ifrs-full:Assets"]), str(t["ifrs-full:EquityAndLiabilities"])]})
    for k in data:
        diff = cf[k][4] - cf[k][3] - cf[k][2]
        checks.append({"id": f"VAL_CF_RECONCILES_{k.upper()}", "ok": diff == 0,
                       "values": [str(cf[k][2]), str(cf[k][4] - cf[k][3])]})
    unmapped = {a.id: a for k in data for a in data[k][2]}
    checks.append({"id": "ALL_ACCOUNTS_MAPPED", "ok": not unmapped, "values": [f"{a.code} {a.name_ar}" for a in unmapped.values()]})
    return {
        "year_end": year_end.isoformat(), "prior_year_end": cy.isoformat(),
        "periods": {k: [s.isoformat(), e.isoformat()] for k, (s, e) in periods.items()},
        "financial_position": [x for x in fp_lines if x["cy"] != "0.000" or x["py"] != "0.000"],
        "profit_or_loss": [x for x in pl_lines if x["cy"] != "0.000" or x["py"] != "0.000"],
        "totals": [{"tag": tg, "cy": str(totals["cy"][tg]), "py": str(totals["py"][tg])} for tg in totals["cy"]],
        "checks": checks,
        "cash_flows": [x for x in cf_lines if x["cy"] != "0.000" or x["py"] != "0.000"], "cash_flow_totals": cf_totals,
        "equity_changes": soce_out,
        "draft": True,
    }
