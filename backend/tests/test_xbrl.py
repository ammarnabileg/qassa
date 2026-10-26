"""MOCI XBRL draft statements: role defaults, override, balance-sheet equation, unmapped accounts, permissions."""
from apps.accounting.models import AccountRoleMapping, FiscalYear
from apps.accounting.services.posting import Line, post_entry
from apps.identity.models import User
from apps.tenancy.context import tenant_context

from .conftest import TODAY, add_member, client_for


def _acc(e, role):
    return AccountRoleMapping.objects.get(legal_entity=e, role=role).account


def test_statements_follow_template_and_balance(company_a):
    t, e, b = company_a
    with tenant_context(t.id):
        post_entry(legal_entity_id=e.id, entry_date=TODAY, branch_id=b["HAW"].id,
                   lines=[Line(_acc(e, "BANK"), debit="1000"), Line(_acc(e, "CAPITAL"), credit="1000")], memo="capital", user=None)
        post_entry(legal_entity_id=e.id, entry_date=TODAY, branch_id=b["HAW"].id, kind="auto",
                   source_type="t", source_id="1", event_type="sale",
                   lines=[Line("CASH_DRAWER", debit="30"), Line("SERVICE_REVENUE", credit="30")])
        post_entry(legal_entity_id=e.id, entry_date=TODAY, branch_id=b["HAW"].id,
                   lines=[Line(_acc(e, "RENT"), debit="10"), Line(_acc(e, "BANK"), credit="10")], memo="rent", user=None)
        fy = FiscalYear.objects.get(legal_entity=e, start_date__lte=TODAY, end_date__gte=TODAY)
    owner = User.objects.get(memberships__tenant=t, memberships__role__key="owner")
    c = client_for(owner, t)
    r = c.get(f"/api/v1/accounting/xbrl?legal_entity_id={e.id}&year_end={fy.end_date}").json()
    fp = {x["tag"]: x["cy"] for x in r["financial_position"]}
    assert fp["ifrs-full:CashAndCashEquivalents"] == "1020.000"
    assert fp["ifrs-full:IssuedCapital"] == "1000.000"
    assert fp["ifrs-full:RetainedEarnings"] == "20.000"          # unclosed profit of the year
    pl = {x["tag"]: x["cy"] for x in r["profit_or_loss"]}
    assert pl == {"ifrs-full:RevenueFromContractsWithCustomers": "30.000", "ifrs-full:GeneralAndAdministrativeExpense": "-10.000"}
    tot = {x["tag"]: x["cy"] for x in r["totals"]}
    assert tot["ifrs-full:Assets"] == tot["ifrs-full:EquityAndLiabilities"] == "1020.000" and tot["ifrs-full:ProfitLoss"] == "20.000"
    assert all(ch["ok"] for ch in r["checks"]) and r["draft"] and r["cash_flows"] is None

    with tenant_context(t.id):
        rent = _acc(e, "RENT")
    bad = c.put(f"/api/v1/accounting/xbrl/mapping?legal_entity_id={e.id}", {"account_id": rent.id, "tag": "ifrs-full:Inventories"}, format="json")
    assert bad.json()["error"]["code"] == "xbrl_tag_invalid"
    ok = c.put(f"/api/v1/accounting/xbrl/mapping?legal_entity_id={e.id}", {"account_id": rent.id, "tag": "ifrs-full:MiscellaneousOtherOperatingExpense"}, format="json")
    assert ok.status_code == 200
    pl = {x["tag"]: x["cy"] for x in c.get(f"/api/v1/accounting/xbrl?legal_entity_id={e.id}&year_end={fy.end_date}").json()["profit_or_loss"]}
    assert pl["ifrs-full:MiscellaneousOtherOperatingExpense"] == "-10.000"

    cashier = add_member(t, "c@k.test", "cashier", branch=b["HAW"])
    assert client_for(cashier, t).get(f"/api/v1/accounting/xbrl?legal_entity_id={e.id}&year_end={fy.end_date}").status_code == 403
