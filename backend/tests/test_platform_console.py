"""Platform console: subscription billing, support tickets, leads, read-only support access, dashboard."""
import datetime

from django.utils import timezone

from apps.identity.models import User
from apps.platform.models import Lead, PlatformInvoice, Subscription, SupportAccess
from apps.platform.services import billing
from apps.tenancy.models import Tenant

from .conftest import add_member, client_for


def _staff():
    return User.objects.create_user("ops@qassa.test", "Ops-Pass-2026!!", is_platform_staff=True)


def _owner(t):
    return User.objects.get(memberships__tenant=t, memberships__role__key="owner")


def test_billing_issues_once_marks_overdue_and_payment_reactivates(company_a):
    t, _, _ = company_a
    sub = Subscription.objects.get(tenant=t)
    sub.current_period_end = datetime.date(2026, 1, 31)
    sub.save()
    Tenant.objects.filter(id=t.id).update(status="active")
    today = datetime.date(2026, 3, 5)
    issued = billing.issue_due(today)
    assert [i.period_start for i in issued] == [datetime.date(2026, 2, 1), datetime.date(2026, 3, 1)]
    assert billing.issue_due(today) == []                                   # idempotent
    assert issued[0].amount == sub.plan.monthly_price and issued[0].due_on == datetime.date(2026, 2, 8)
    assert billing.mark_overdue(today) == 1
    t.refresh_from_db()
    assert t.status == "past_due"

    c = client_for(_staff())
    r = c.post(f"/api/v1/platform/invoices/{issued[0].id}/action", {"action": "pay", "reference": ""}, format="json")
    assert r.json()["error"]["code"] == "payment_reference_required"
    for inv in issued:
        assert c.post(f"/api/v1/platform/invoices/{inv.id}/action", {"action": "pay", "method": "bank", "reference": "TRX-9"},
                      format="json").json()["status"] == "paid"
    t.refresh_from_db()
    assert t.status == "active"
    again = c.post(f"/api/v1/platform/invoices/{issued[0].id}/action", {"action": "pay", "reference": "x"}, format="json")
    assert again.json()["error"]["code"] == "invoice_not_open"
    # the salon sees its own invoices only, not other companies'
    mine = client_for(_owner(t), t).get("/api/v1/subscription/invoices").json()
    assert {i["number"] for i in mine} == {i.number for i in issued}


def test_tickets_flow_and_isolation(company_a, company_b):
    ta, tb = company_a[0], company_b[0]
    a = client_for(_owner(ta), ta)
    tk = a.post("/api/v1/support/tickets", {"subject": "الطابعة مش بتطبع", "body": "من امبارح", "priority": "high"}, format="json").json()
    assert tk["status"] == "open" and len(tk["messages"]) == 1
    staff = client_for(_staff())
    r = staff.post(f"/api/v1/platform/tickets/{tk['id']}/reply", {"body": "جرب تعيد تعريفها"}, format="json").json()
    assert r["status"] == "pending" and r["messages"][-1]["from_platform"]
    assert a.post(f"/api/v1/support/tickets/{tk['id']}/reply", {"body": "لسه", "status": "pending"}, format="json").json()["status"] == "open"
    b = client_for(_owner(tb), tb)
    assert b.get("/api/v1/support/tickets").json() == []
    assert b.post(f"/api/v1/support/tickets/{tk['id']}/reply", {"body": "x"}, format="json").status_code == 404
    cashier = add_member(ta, "c@k.test", "cashier", branch=company_a[2]["HAW"])
    assert client_for(cashier, ta).get("/api/v1/support/tickets").status_code == 403
    assert client_for(_owner(ta)).get("/api/v1/platform/tickets").status_code == 403


def test_public_lead_honeypot_and_platform_follow_up(db):
    from rest_framework.test import APIClient
    c = APIClient()
    body = {"salon_name": "صالون نجوم", "contact_name": "أم سالم", "phone": "55512345", "business_type": "kids", "branches": 2}
    assert c.post("/api/v1/public/leads", body, format="json").status_code == 201
    assert c.post("/api/v1/public/leads", {**body, "website": "spam.example"}, format="json").status_code == 201
    assert Lead.objects.count() == 1 and Lead.objects.get().phone == "96555512345"
    staff = client_for(_staff())
    lead = staff.get("/api/v1/platform/leads").json()[0]
    assert staff.patch(f"/api/v1/platform/leads/{lead['id']}", {"status": "contacted", "notes": "اتصلت", "phone": "1"},
                       format="json").json()["phone"] == "96555512345"   # contact data is read-only


def test_support_access_is_read_only_audited_and_expires(company_a):
    from apps.audit.models import AuditLog
    t, e, _ = company_a
    staff = _staff()
    c = client_for(staff, t)
    assert c.get("/api/v1/org").status_code == 403                       # no access without a reason
    assert c.post(f"/api/v1/platform/tenants/{t.id}/support", {"reason": "قصير"}, format="json").status_code == 400
    assert c.post(f"/api/v1/platform/tenants/{t.id}/support", {"reason": "العميل بيشتكي من ميزان المراجعة"}, format="json").status_code == 201
    assert c.get("/api/v1/org").status_code == 200
    assert c.get(f"/api/v1/accounting/accounts?legal_entity_id={e.id}").status_code == 200
    assert c.post("/api/v1/customers", {"full_name": "x", "phone": "55554444"}, format="json").status_code == 403
    me = c.get("/api/v1/auth/me").json()
    assert [m["support"] for m in me["memberships"]] == [True]
    assert AuditLog.objects.filter(action="platform.support_access_started", acting_as_support=True).exists()
    SupportAccess.objects.update(expires_at=timezone.now() - datetime.timedelta(minutes=1))
    assert c.get("/api/v1/org").status_code == 403
    assert client_for(_owner(t), t).post(f"/api/v1/platform/tenants/{t.id}/support", {"reason": "x" * 20}, format="json").status_code == 403


def test_dashboard_uses_real_figures(company_a, company_b):
    Tenant.objects.filter(id=company_a[0].id).update(status="active")
    d = client_for(_staff()).get("/api/v1/platform/dashboard").json()
    assert d["tenants"]["active"] == 1 and d["tenants"]["trial"] == 1
    assert d["mrr"] == str(Subscription.objects.get(tenant=company_a[0]).plan.monthly_price)
    assert len(d["history"]) == 6 and PlatformInvoice.objects.count() == 0


def test_month_end_billing_keeps_its_day_and_unique_numbers(company_a):
    t, _, _ = company_a
    sub = Subscription.objects.get(tenant=t)
    sub.started_on, sub.current_period_end = datetime.date(2025, 12, 1), datetime.date(2025, 12, 31)
    sub.save()
    issued = billing.issue_due(datetime.date(2026, 5, 2))
    assert [(i.period_start.isoformat(), i.period_end.isoformat()) for i in issued] == [
        ("2026-01-01", "2026-01-31"), ("2026-02-01", "2026-02-28"), ("2026-03-01", "2026-03-31"), ("2026-04-01", "2026-04-30"),
        ("2026-05-01", "2026-05-31")]
    assert len({i.number for i in issued}) == 5
