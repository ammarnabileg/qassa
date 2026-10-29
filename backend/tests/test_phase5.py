"""Phase 5: expenses and accruals, fixed assets and depreciation (example 12), clearing settlement (example 11),
statements, period close checks, year-end closing, frozen report versions."""
from datetime import date
from decimal import Decimal

import pytest
from django.db import connection, transaction

from apps.accounting.models import AccountRoleMapping, FiscalYear, JournalEntry, JournalLine, ReportVersion
from apps.accounting.services.posting import Line, post_entry
from apps.identity.models import User
from apps.tenancy.context import tenant_context

from .conftest import TODAY, add_member, client_for

Y = TODAY.year


@pytest.fixture
def s(company_a):
    t, e, b = company_a
    owner = User.objects.get(memberships__tenant=t, memberships__role__key="owner")
    return {"t": t, "e": e, "b": b, "c": client_for(owner, t), "q": f"?legal_entity_id={e.id}"}


def acc(s, role):
    with tenant_context(s["t"].id):
        return AccountRoleMapping.objects.get(legal_entity=s["e"], role=role).account


def lines_of(s, source_type, source_id, event):
    with tenant_context(s["t"].id):
        je = JournalEntry.objects.get(source_type=source_type, source_id=str(source_id), event_type=event)
        return {(l.account.code, str(l.debit), str(l.credit)) for l in JournalLine.objects.filter(entry=je).select_related("account")}


def test_expense_paid_and_accrued(s):
    c, q = s["c"], s["q"]
    rent = acc(s, "RENT")
    r = c.post(f"/api/v1/accounting/expenses{q}", {"expense_date": f"{Y}-03-01", "account_id": rent.id, "description": "إيجار مارس",
                                                    "amount": "450", "paid_from": "accrued"}, format="json", HTTP_IDEMPOTENCY_KEY="e1")
    assert r.status_code == 201, r.content
    e = r.json()
    assert lines_of(s, "expense", e["id"], "recorded") == {(rent.code, "450.000", "0.000"), (acc(s, "ACCRUED_EXPENSES").code, "0.000", "450.000")}
    p = c.post(f"/api/v1/accounting/expenses/{e['id']}/pay", {"paid_on": f"{Y}-03-05", "reference": "TRX-55"}, format="json", HTTP_IDEMPOTENCY_KEY="e2")
    assert p.json()["paid_reference"] == "TRX-55"
    assert lines_of(s, "expense", e["id"], "paid") == {(acc(s, "ACCRUED_EXPENSES").code, "450.000", "0.000"), (acc(s, "BANK").code, "0.000", "450.000")}
    again = c.post(f"/api/v1/accounting/expenses/{e['id']}/pay", {"paid_on": f"{Y}-03-06", "reference": "X"}, format="json", HTTP_IDEMPOTENCY_KEY="e3")
    assert again.json()["error"]["code"] == "expense_not_accrued"
    bad = c.post(f"/api/v1/accounting/expenses{q}", {"expense_date": f"{Y}-03-01", "account_id": acc(s, "BANK").id, "description": "x",
                                                      "amount": "1", "paid_from": "bank"}, format="json", HTTP_IDEMPOTENCY_KEY="e4")
    assert bad.json()["error"]["code"] == "expense_account_invalid"


def test_fixed_asset_and_depreciation_example_12(s):
    c, q = s["c"], s["q"]
    r = c.post(f"/api/v1/accounting/assets{q}", {"name": "كرسي حلاقة", "acquired_on": f"{Y}-01-15", "cost": "600", "life_months": 60,
                                                  "paid_from": "bank"}, format="json", HTTP_IDEMPOTENCY_KEY="a1")
    assert r.status_code == 201 and r.json()["monthly"] == "10.000"
    a = r.json()
    assert lines_of(s, "asset", a["id"], "acquired") == {(acc(s, "FIXED_ASSETS").code, "600.000", "0.000"), (acc(s, "BANK").code, "0.000", "600.000")}
    assert c.post(f"/api/v1/accounting/depreciation{q}", {"month": f"{Y}-01"}, format="json").json()["posted"] == 0   # month of purchase
    d = c.post(f"/api/v1/accounting/depreciation{q}", {"month": f"{Y}-02"}, format="json").json()
    assert d == {"month": f"{Y}-02", "posted": 1, "already_posted": 0, "total": "10.000"}
    assert c.post(f"/api/v1/accounting/depreciation{q}", {"month": f"{Y}-02"}, format="json").json()["already_posted"] == 1
    assert lines_of(s, "asset", a["id"], f"dep:{Y}-02") == {(acc(s, "DEPRECIATION_EXPENSE").code, "10.000", "0.000"),
                                                            (acc(s, "ACCUMULATED_DEPRECIATION").code, "0.000", "10.000")}


def test_last_depreciation_month_absorbs_rounding(db):
    from apps.accounting.models import FixedAsset
    from apps.accounting.services.finance import depreciation_for
    a = FixedAsset(acquired_on=date(2026, 1, 10), cost=Decimal("100.000"), residual_value=Decimal("0"), life_months=3)
    months = [depreciation_for(a, date(2026, m, 1)) for m in (1, 2, 3, 4, 5)]
    assert months == [Decimal("0"), Decimal("33.333"), Decimal("33.333"), Decimal("33.334"), Decimal("0")]


def test_clearing_settlement_example_11(s):
    c, q = s["c"], s["q"]
    with tenant_context(s["t"].id):
        post_entry(legal_entity_id=s["e"].id, entry_date=date(Y, 4, 1), kind="auto", source_type="t", source_id="1", event_type="knet",
                   lines=[Line("KNET_CLEARING", debit="30"), Line("SERVICE_REVENUE", credit="30")])
    too_much = c.post(f"/api/v1/accounting/settlements{q}", {"channel": "knet", "settled_on": f"{Y}-04-02", "gross": "31", "fees": "0.750",
                                                              "reference": "S1"}, format="json", HTTP_IDEMPOTENCY_KEY="s0")
    assert too_much.json()["error"]["code"] == "settlement_exceeds_clearing"
    r = c.post(f"/api/v1/accounting/settlements{q}", {"channel": "knet", "settled_on": f"{Y}-04-02", "gross": "30", "fees": "0.750",
                                                       "reference": "S1"}, format="json", HTTP_IDEMPOTENCY_KEY="s1")
    assert r.status_code == 201
    assert lines_of(s, "settlement", r.json()["id"], "settled") == {(acc(s, "BANK").code, "29.250", "0.000"),
                                                                    (acc(s, "PAYMENT_FEES").code, "0.750", "0.000"),
                                                                    (acc(s, "KNET_CLEARING").code, "0.000", "30.000")}
    st = c.get(f"/api/v1/accounting/settlements{q}").json()["status"]
    assert {x["channel"]: x["open_balance"] for x in st} == {"knet": "0.000", "gateway": "0.000"}


def test_statements_year_close_and_frozen_version(s):
    c, q, e = s["c"], s["q"], s["e"]
    with tenant_context(s["t"].id):
        post_entry(legal_entity_id=e.id, entry_date=date(Y, 2, 1), lines=[Line(acc(s, "BANK"), debit="1000"), Line(acc(s, "CAPITAL"), credit="1000")], memo="c")
        post_entry(legal_entity_id=e.id, entry_date=date(Y, 2, 2), kind="auto", source_type="t", source_id="2", event_type="sale",
                   lines=[Line("CASH_DRAWER", debit="80"), Line("SERVICE_REVENUE", credit="80")])
        post_entry(legal_entity_id=e.id, entry_date=date(Y, 2, 3), lines=[Line(acc(s, "RENT"), debit="30"), Line(acc(s, "BANK"), credit="30")], memo="r")
        fy = FiscalYear.objects.get(legal_entity=e, start_date__lte=date(Y, 2, 1), end_date__gte=date(Y, 2, 1))
    inc = c.get(f"/api/v1/accounting/income-statement{q}&from={fy.start_date}&to={fy.end_date}").json()
    assert (inc["total_revenue"], inc["total_expenses"], inc["net_profit"]) == ("80.000", "30.000", "50.000")
    bs = c.get(f"/api/v1/accounting/balance-sheet{q}&as_of={fy.end_date}").json()
    assert bs["total_assets"] == "1050.000" and bs["unclosed_profit"] == "50.000" and bs["balanced"]

    frozen = c.post(f"/api/v1/accounting/report-versions{q}", {"kind": "income_statement", "params": {"from": str(fy.start_date), "to": str(fy.end_date)},
                                                                "note": "للمحاسب"}, format="json").json()
    closed = c.post(f"/api/v1/accounting/years/{fy.id}/close").json()
    assert closed["entry"].startswith("JE-")
    assert c.post(f"/api/v1/accounting/years/{fy.id}/close").json()["error"]["code"] == "year_already_closed"
    # after closing: profit moved to retained earnings, the year's income statement is unchanged
    bs2 = c.get(f"/api/v1/accounting/balance-sheet{q}&as_of={fy.end_date}").json()
    assert bs2["unclosed_profit"] == "0.000" and bs2["balanced"]
    assert {r["code"]: r["amount"] for r in bs2["equity"]}[acc(s, "RETAINED_EARNINGS").code] == "50.000"
    assert c.get(f"/api/v1/accounting/income-statement{q}&from={fy.start_date}&to={fy.end_date}").json()["net_profit"] == "50.000"
    v = c.get(f"/api/v1/accounting/report-versions/{frozen['id']}").json()
    assert v["intact"] and v["data"]["net_profit"] == "50.000" and v["sha256"] == frozen["sha256"]
    with pytest.raises(Exception), transaction.atomic(), connection.cursor() as cur:   # frozen versions are immutable in the DB
        cur.execute("UPDATE accounting_reportversion SET note='x' WHERE id=%s", [frozen["id"]])
    assert ReportVersion.unscoped.get(id=frozen["id"]).note == "للمحاسب"


def test_period_close_blocked_by_open_drawer_and_permissions(s):
    from apps.pos.models import CashSession
    from apps.accounting.models import FiscalPeriod
    c, t, b = s["c"], s["t"], s["b"]
    with tenant_context(t.id):
        owner = User.objects.get(memberships__tenant=t, memberships__role__key="owner")
        CashSession.objects.create(branch=b["HAW"], opened_by=owner, opening_float=Decimal("10"))
        p = FiscalPeriod.objects.filter(legal_entity=s["e"], start_date__lte=TODAY, end_date__gte=TODAY).first()
    r = c.post(f"/api/v1/accounting/periods/{p.id}/close", {}, format="json")
    assert r.json()["error"]["code"] == "period_close_blocked"
    cashier = add_member(t, "c@k.test", "cashier", branch=b["HAW"])
    assert client_for(cashier, t).get(f"/api/v1/accounting/income-statement{s['q']}&from={Y}-01-01&to={Y}-12-31").status_code == 403
    periods = c.get(f"/api/v1/accounting/periods{s['q']}").json()
    assert len(periods[0]["periods"]) == 12
