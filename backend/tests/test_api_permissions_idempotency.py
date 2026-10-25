"""Server-side permissions, idempotent posting, and branch scope on the accounting API."""
from apps.accounting.models import AccountRoleMapping, JournalEntry
from apps.tenancy.context import tenant_context

from .conftest import TODAY, add_member, client_for


def entry_body(entity, rent, bank, amount="300.000"):
    return {"legal_entity_id": entity.id, "entry_date": TODAY.isoformat(), "memo": "October rent",
            "lines": [{"account_id": rent.id, "debit": amount}, {"account_id": bank.id, "credit": amount}]}


def accounts(t, e):
    with tenant_context(t.id):
        m = {x.role: x.account for x in AccountRoleMapping.objects.filter(legal_entity=e).select_related("account")}
    return m["RENT"], m["BANK"]


def count_entries(t):
    with tenant_context(t.id):
        return JournalEntry.objects.count()


def test_cashier_cannot_post_or_view_ledger(company_a):
    t, e, b = company_a
    cashier = add_member(t, "c@mykids.test", "cashier", branch=b["HAW"])
    c = client_for(cashier, t)
    rent, bank = accounts(t, e)
    r = c.post("/api/v1/accounting/journal-entries", entry_body(e, rent, bank), format="json", HTTP_IDEMPOTENCY_KEY="a1")
    assert r.status_code == 403
    assert c.get(f"/api/v1/accounting/accounts?legal_entity_id={e.id}").status_code == 403
    assert count_entries(t) == 0


def test_accountant_posts_idempotently(company_a):
    t, e, _ = company_a
    accountant = add_member(t, "a@mykids.test", "accountant")
    c = client_for(accountant, t)
    rent, bank = accounts(t, e)
    body = entry_body(e, rent, bank)
    r1 = c.post("/api/v1/accounting/journal-entries", body, format="json", HTTP_IDEMPOTENCY_KEY="rent-oct")
    r2 = c.post("/api/v1/accounting/journal-entries", body, format="json", HTTP_IDEMPOTENCY_KEY="rent-oct")
    assert r1.status_code == r2.status_code == 201
    assert r1.json()["number"] == r2.json()["number"]
    assert r2["Idempotent-Replay"] == "true"
    assert count_entries(t) == 1
    r3 = c.post("/api/v1/accounting/journal-entries", entry_body(e, rent, bank, "301"), format="json",
                HTTP_IDEMPOTENCY_KEY="rent-oct")
    assert r3.status_code == 422 and r3.json()["error"]["code"] == "idempotency_key_mismatch"


def test_idempotency_key_required(company_a):
    t, e, _ = company_a
    c = client_for(add_member(t, "a2@mykids.test", "accountant"), t)
    rent, bank = accounts(t, e)
    r = c.post("/api/v1/accounting/journal-entries", entry_body(e, rent, bank), format="json")
    assert r.status_code == 422 and r.json()["error"]["code"] == "idempotency_key_required"


def test_failed_request_does_not_burn_the_key(company_a):
    t, e, _ = company_a
    c = client_for(add_member(t, "a3@mykids.test", "accountant"), t)
    rent, bank = accounts(t, e)
    bad = entry_body(e, rent, bank)
    bad["lines"][1]["credit"] = "299"
    r = c.post("/api/v1/accounting/journal-entries", bad, format="json", HTTP_IDEMPOTENCY_KEY="k9")
    assert r.status_code == 422 and r.json()["error"]["code"] == "je_unbalanced"
    r = c.post("/api/v1/accounting/journal-entries", bad | {"lines": entry_body(e, rent, bank)["lines"]}, format="json",
               HTTP_IDEMPOTENCY_KEY="k9-retry")
    assert r.status_code == 201


def test_unknown_or_foreign_account_rejected(company_a, company_b):
    t, e, _ = company_a
    tb, eb, _ = company_b
    c = client_for(add_member(t, "a4@mykids.test", "accountant"), t)
    foreign_rent, foreign_bank = accounts(tb, eb)
    r = c.post("/api/v1/accounting/journal-entries", entry_body(e, foreign_rent, foreign_bank), format="json",
               HTTP_IDEMPOTENCY_KEY="x1")
    assert r.status_code == 422 and r.json()["error"]["code"] == "je_unknown_account"


def test_reverse_requires_permission_and_reason(company_a):
    t, e, _ = company_a
    accountant = add_member(t, "a5@mykids.test", "accountant")
    fm = add_member(t, "fm@mykids.test", "finance_manager")
    rent, bank = accounts(t, e)
    je = client_for(accountant, t).post("/api/v1/accounting/journal-entries", entry_body(e, rent, bank), format="json",
                                        HTTP_IDEMPOTENCY_KEY="r1").json()
    url = f"/api/v1/accounting/journal-entries/{je['id']}/reverse"
    assert client_for(accountant, t).post(url, {"reason": "oops"}, format="json", HTTP_IDEMPOTENCY_KEY="rv1").status_code == 403
    assert client_for(fm, t).post(url, {}, format="json", HTTP_IDEMPOTENCY_KEY="rv2").status_code == 400
    r = client_for(fm, t).post(url, {"reason": "duplicate bill"}, format="json", HTTP_IDEMPOTENCY_KEY="rv3")
    assert r.status_code == 201 and r.json()["reversal_of"] == je["id"]


def test_trial_balance_api_and_branch_restriction(company_a):
    t, e, b = company_a
    fm = add_member(t, "fm2@mykids.test", "finance_manager")
    rent, bank = accounts(t, e)
    client_for(fm, t).post("/api/v1/accounting/journal-entries", entry_body(e, rent, bank), format="json",
                           HTTP_IDEMPOTENCY_KEY="tb1")
    r = client_for(fm, t).get(f"/api/v1/accounting/trial-balance?legal_entity_id={e.id}&from={TODAY.replace(day=1)}&to={TODAY}")
    assert r.status_code == 200 and r.json()["balanced"] is True and r.json()["total_debit"] == "300.000"
    scoped = add_member(t, "auditor@mykids.test", "auditor", branch=b["SAL"])
    c = client_for(scoped, t)
    base = f"/api/v1/accounting/trial-balance?legal_entity_id={e.id}&from={TODAY.replace(day=1)}&to={TODAY}"
    assert c.get(base).status_code == 422
    assert c.get(base + f"&branch_id={b['HAW'].id}").status_code == 422
    assert c.get(base + f"&branch_id={b['SAL'].id}").status_code == 200
