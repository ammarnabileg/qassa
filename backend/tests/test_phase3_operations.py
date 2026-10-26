"""Phase 3 acceptance: booking without double-booking; POS with server-side prices; examples 1, 3, 4, 7 posted
correctly; cash drawer with segregated variance approval; immutability; permissions."""
import threading
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.accounting.models import JournalEntry, JournalLine
from apps.accounting.services.posting import resolve_role
from apps.catalog.models import Service, ServiceCategory
from apps.catalog.services.pricing import set_price
from apps.identity.models import User
from apps.staff.models import StaffBranch, StaffMember, StaffSkill
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Membership
from tests.conftest import add_member, client_for

pytestmark = pytest.mark.django_db
D = Decimal


@pytest.fixture
def salon(company_a):
    """Kids company, branch HAW: two services with prices, two staff with skills, a cashier, a manager."""
    t, entity, b = company_a
    with tenant_context(t.id):
        cat = ServiceCategory.objects.create(name_ar="قصات", business_type="kids")
        cut = Service.objects.create(category=cat, name_ar="قص", duration_minutes=30)
        wash = Service.objects.create(category=cat, name_ar="غسيل", duration_minutes=15)
        set_price(cut, price="5.000")
        set_price(wash, price="15.000")
        staff = []
        for name in ["منى", "سارة"]:
            s = StaffMember.objects.create(full_name_ar=name)
            StaffBranch.objects.create(staff=s, branch=b["HAW"])
            StaffSkill.objects.create(staff=s, service=cut)
            StaffSkill.objects.create(staff=s, service=wash)
            staff.append(s)
    cashier = add_member(t, "cashier@k.test", "cashier", branch=b["HAW"])
    manager = add_member(t, "bm@k.test", "branch_manager", branch=b["HAW"])
    owner = User.objects.get(memberships__tenant=t, memberships__role__key="owner")
    return dict(t=t, entity=entity, b=b, cut=cut, wash=wash, staff=staff, cashier=cashier, manager=manager, owner=owner)


def balance(s, role):
    """Debit-positive balance of an account role across all posted entries."""
    with tenant_context(s["t"].id):
        acc = resolve_role(s["entity"].id, role)
        agg = JournalLine.objects.filter(account=acc).aggregate(d=Sum("debit"), c=Sum("credit"))
    return (agg["d"] or D(0)) - (agg["c"] or D(0))


def open_drawer(s, user=None, amount="20.000"):
    r = client_for(user or s["cashier"], s["t"]).post("/api/v1/pos/sessions", {"branch_id": s["b"]["HAW"].id,
                                                                              "opening_float": amount}, format="json")
    assert r.status_code == 201, r.content
    return r.json()


def checkout(s, user, lines, payments=(), key="k1", **extra):
    body = {"branch_id": s["b"]["HAW"].id, "lines": lines, "payments": list(payments), **extra}
    return client_for(user, s["t"]).post("/api/v1/pos/checkout", body, format="json", HTTP_IDEMPOTENCY_KEY=key)


def soon(minutes=60):
    return (timezone.now() + timedelta(minutes=minutes)).replace(second=0, microsecond=0)


# ---------- booking ----------
def book(s, start, staff=0, key=None, user=None, items=None):
    body = {"branch_id": s["b"]["HAW"].id, "starts_at": start.isoformat(), "walk_in_name": "يوسف",
            "items": items or [{"service_id": s["cut"].id, "staff_id": s["staff"][staff].id}]}
    return client_for(user or s["cashier"], s["t"]).post("/api/v1/booking/appointments", body, format="json",
                                                         HTTP_IDEMPOTENCY_KEY=key or f"b-{start.isoformat()}-{staff}")


def test_no_double_booking_and_cancel_frees_the_slot(salon):
    s = salon
    t0 = soon()
    r = book(s, t0)
    assert r.status_code == 201, r.content
    a1 = r.json()
    from datetime import datetime
    assert datetime.fromisoformat(a1["ends_at"]) == t0 + timedelta(minutes=30)
    clash = book(s, t0 + timedelta(minutes=15), key="clash")
    assert clash.status_code == 409 and clash.json()["error"]["code"] == "slot_taken"
    assert book(s, t0 + timedelta(minutes=15), staff=1, key="other").status_code == 201  # another person is free
    assert book(s, t0 + timedelta(minutes=30), key="after").status_code == 201          # back-to-back is fine
    c = client_for(s["cashier"], s["t"])
    assert c.post(f"/api/v1/booking/appointments/{a1['id']}/status", {"status": "cancelled"}, format="json").status_code == 422
    assert c.post(f"/api/v1/booking/appointments/{a1['id']}/status", {"status": "cancelled", "reason": "اتصل"},
                  format="json").status_code == 200
    assert book(s, t0, key="freed").status_code == 201


def test_multi_service_visit_is_sequential(salon):
    s = salon
    t0 = soon()
    r = book(s, t0, items=[{"service_id": s["cut"].id, "staff_id": s["staff"][0].id},
                           {"service_id": s["wash"].id, "staff_id": s["staff"][1].id}])
    items = r.json()["items"]
    assert items[1]["starts_at"] == items[0]["ends_at"]
    assert r.json()["ends_at"] == items[1]["ends_at"]


def test_booking_validates_skill_branch_and_business_type(salon):
    s = salon
    with tenant_context(s["t"].id):
        newbie = StaffMember.objects.create(full_name_ar="جديد")
        StaffBranch.objects.create(staff=newbie, branch=s["b"]["HAW"])
        other = StaffMember.objects.create(full_name_ar="فرع آخر")
        StaffSkill.objects.create(staff=other, service=s["cut"])
        womens = Service.objects.create(category=ServiceCategory.objects.create(name_ar="نسائي", business_type="women"),
                                        name_ar="صبغة", duration_minutes=60)
    t0 = soon()
    for items, code in [([{"service_id": s["cut"].id, "staff_id": newbie.id}], "staff_lacks_skill"),
                        ([{"service_id": s["cut"].id, "staff_id": other.id}], "staff_not_in_branch"),
                        ([{"service_id": womens.id, "staff_id": s["staff"][0].id}], "service_not_for_branch")]:
        r = book(s, t0, items=items, key=code)
        assert r.status_code == 422 and r.json()["error"]["code"] == code


def test_status_flow_and_bad_transition(salon):
    s = salon
    a = book(s, soon()).json()
    c = client_for(s["cashier"], s["t"])
    url = f"/api/v1/booking/appointments/{a['id']}/status"
    for st in ["arrived", "in_service", "completed"]:
        assert c.post(url, {"status": st}, format="json").json()["status"] == st
    r = c.post(url, {"status": "booked"}, format="json")
    assert r.status_code == 422 and r.json()["error"]["code"] == "appointment_bad_transition"


@pytest.mark.django_db(transaction=True)
def test_concurrent_bookings_for_the_same_slot_only_one_wins():
    from tests.conftest import make_company
    t, entity, b = make_company("Race", "o@race.test")
    with tenant_context(t.id):
        cat = ServiceCategory.objects.create(name_ar="قصات", business_type="kids")
        cut = Service.objects.create(category=cat, name_ar="قص", duration_minutes=30)
        st = StaffMember.objects.create(full_name_ar="منى")
        StaffBranch.objects.create(staff=st, branch=b["HAW"])
        StaffSkill.objects.create(staff=st, service=cut)
    owner = User.objects.get(email="o@race.test")
    start = soon(120).isoformat()
    results = []

    def go(i):
        r = client_for(owner, t).post("/api/v1/booking/appointments", {
            "branch_id": b["HAW"].id, "starts_at": start, "walk_in_name": f"c{i}",
            "items": [{"service_id": cut.id, "staff_id": st.id}]}, format="json", HTTP_IDEMPOTENCY_KEY=f"race-{i}")
        results.append(r.status_code)
        connection.close()

    threads = [threading.Thread(target=go, args=(i,)) for i in range(6)]
    [th.start() for th in threads]
    [th.join() for th in threads]
    assert sorted(results) == [201, 409, 409, 409, 409, 409]


# ---------- POS + accounting ----------
def test_example_1_cash_service_posts_two_balanced_entries(salon):
    s = salon
    open_drawer(s)
    r = checkout(s, s["cashier"], [{"service_id": s["cut"].id, "staff_id": s["staff"][0].id}],
                 [{"method": "cash", "amount": "5.000"}], expected_total="5.000")
    assert r.status_code == 201, r.content
    inv = r.json()
    assert inv["number"].startswith("INV-") and inv["total"] == "5.000" and inv["state"]["balance"] == "0.000"
    assert balance(s, "CASH_DRAWER") == D("5.000")
    assert balance(s, "SERVICE_REVENUE") == D("-5.000")
    assert balance(s, "AR_CUSTOMERS") == D("0.000")
    with tenant_context(s["t"].id):
        events = set(JournalEntry.objects.filter(source_type__startswith="pos.").values_list("event_type", flat=True))
    assert events == {"invoice.issued", "payment.received"}


def test_example_3_mixed_cash_and_knet(salon):
    s = salon
    open_drawer(s)
    r = checkout(s, s["cashier"], [{"service_id": s["wash"].id}, {"service_id": s["cut"].id}],
                 [{"method": "cash", "amount": "5.000"}, {"method": "knet", "amount": "15.000", "reference": "AUTH77"}])
    assert r.status_code == 201, r.content
    assert balance(s, "CASH_DRAWER") == D("5.000") and balance(s, "KNET_CLEARING") == D("15.000")
    assert balance(s, "SERVICE_REVENUE") == D("-20.000") and balance(s, "AR_CUSTOMERS") == 0
    # card without an approval code is refused
    r = checkout(s, s["cashier"], [{"service_id": s["cut"].id}], [{"method": "knet", "amount": "5.000"}], key="k2")
    assert r.status_code == 422 and r.json()["error"]["code"] == "payment_reference_required"


def test_example_4_credit_sale_then_collection(salon):
    s = salon
    c = client_for(s["manager"], s["t"])
    cust = c.post("/api/v1/customers", {"full_name": "أم يوسف", "phone": "55551111"}, format="json").json()
    # cashier may not sell on credit
    r = checkout(s, s["cashier"], [{"service_id": s["wash"].id}], customer_id=cust["id"], key="c0")
    assert r.status_code == 422 and r.json()["error"]["code"] == "credit_sale_forbidden"
    # manager may, but only for a known customer
    assert checkout(s, s["manager"], [{"service_id": s["wash"].id}], key="c1").json()["error"]["code"] == "credit_sale_needs_customer"
    r = checkout(s, s["manager"], [{"service_id": s["wash"].id}], customer_id=cust["id"], key="c2")
    inv = r.json()
    assert r.status_code == 201 and inv["is_credit"] and inv["state"]["balance"] == "15.000"
    assert balance(s, "AR_CUSTOMERS") == D("15.000")
    unpaid = c.get("/api/v1/pos/invoices", {"unpaid": "true"}).json()
    assert [x["id"] for x in unpaid] == [inv["id"]]
    r = c.post(f"/api/v1/pos/invoices/{inv['id']}/payments", {"payments": [{"method": "transfer", "amount": "16.000", "reference": "T1"}]},
               format="json", HTTP_IDEMPOTENCY_KEY="p0")
    assert r.status_code == 422 and r.json()["error"]["code"] == "overpayment"
    r = c.post(f"/api/v1/pos/invoices/{inv['id']}/payments", {"payments": [{"method": "transfer", "amount": "15.000", "reference": "T1"}]},
               format="json", HTTP_IDEMPOTENCY_KEY="p1")
    assert r.status_code == 201 and r.json()["state"]["balance"] == "0.000"
    assert balance(s, "AR_CUSTOMERS") == 0 and balance(s, "BANK") == D("15.000")


def test_example_7_partial_return_with_cash_refund(salon):
    s = salon
    open_drawer(s)
    inv = checkout(s, s["cashier"], [{"service_id": s["wash"].id}], [{"method": "cash", "amount": "15.000"}]).json()
    line = inv["lines"][0]["id"]
    # the cashier role has no pos.return
    r = client_for(s["cashier"], s["t"]).post(f"/api/v1/pos/invoices/{inv['id']}/credit-notes",
                                             {"lines": [{"invoice_line_id": line, "amount": "2.000"}], "reason": "x"},
                                             format="json", HTTP_IDEMPOTENCY_KEY="r0")
    assert r.status_code == 403
    m = client_for(s["manager"], s["t"])
    body = {"lines": [{"invoice_line_id": line, "amount": "2.000"}], "reason": "الخدمة ناقصة",
            "refund": {"method": "cash", "amount": "2.000"}}
    r = m.post(f"/api/v1/pos/invoices/{inv['id']}/credit-notes", body, format="json", HTTP_IDEMPOTENCY_KEY="r1")
    assert r.status_code == 201, r.content
    got = r.json()
    assert got["credit_notes"][0]["number"].startswith("CN-") and got["lines"][0]["returned"] == "2.000"
    assert balance(s, "SALES_RETURNS") == D("2.000") and balance(s, "CASH_DRAWER") == D("13.000")
    assert balance(s, "AR_CUSTOMERS") == 0
    # cannot return more than what is left on the line, nor refund more than was paid
    r = m.post(f"/api/v1/pos/invoices/{inv['id']}/credit-notes", {"lines": [{"invoice_line_id": line, "amount": "13.500"}],
                                                                  "reason": "x"}, format="json", HTTP_IDEMPOTENCY_KEY="r2")
    assert r.json()["error"]["code"] == "return_exceeds_line"


def test_prices_come_from_the_server_and_old_invoices_keep_their_price(salon):
    s = salon
    open_drawer(s)
    r = checkout(s, s["cashier"], [{"service_id": s["cut"].id}], [{"method": "cash", "amount": "5.000"}], expected_total="4.000")
    assert r.status_code == 409 and r.json()["error"]["code"] == "price_changed" and r.json()["error"]["details"]["total"] == "5.000"
    inv = checkout(s, s["cashier"], [{"service_id": s["cut"].id}], [{"method": "cash", "amount": "5.000"}], key="k2").json()
    with tenant_context(s["t"].id):
        from apps.catalog.models import ServicePrice
        ServicePrice.objects.filter(service=s["cut"]).update(valid_from=timezone.localdate() - timedelta(days=5))
        set_price(s["cut"], price="7.000", valid_from=timezone.localdate() + timedelta(days=1))
    again = client_for(s["cashier"], s["t"]).get(f"/api/v1/pos/invoices/{inv['id']}").json()
    assert again["lines"][0]["unit_price"] == "5.000"


def test_cash_requires_open_drawer_and_one_drawer_per_branch(salon):
    s = salon
    r = checkout(s, s["cashier"], [{"service_id": s["cut"].id}], [{"method": "cash", "amount": "5.000"}])
    assert r.status_code == 422 and r.json()["error"]["code"] == "no_open_session"
    open_drawer(s)
    r = client_for(s["manager"], s["t"]).post("/api/v1/pos/sessions", {"branch_id": s["b"]["HAW"].id, "opening_float": "0"}, format="json")
    assert r.status_code == 409 and r.json()["error"]["code"] == "session_already_open"


def test_drawer_close_variance_needs_another_person_and_posts_over_short(salon):
    s = salon
    sess = open_drawer(s, amount="20.000")
    checkout(s, s["cashier"], [{"service_id": s["cut"].id}], [{"method": "cash", "amount": "5.000"}])
    c = client_for(s["cashier"], s["t"])
    assert c.get("/api/v1/pos/sessions", {"branch_id": s["b"]["HAW"].id}).json()[0]["expected_now"] == "25.000"
    closed = c.post(f"/api/v1/pos/sessions/{sess['id']}/close", {"counted_cash": "24.500"}, format="json").json()
    assert closed["expected_cash"] == "25.000" and closed["variance"] == "-0.500" and closed["variance_status"] == "pending"
    # the cashier has no approval permission; a manager who did not run the drawer approves
    assert c.post(f"/api/v1/pos/sessions/{sess['id']}/approve").status_code == 403
    m = client_for(s["manager"], s["t"])
    r = m.post(f"/api/v1/pos/sessions/{sess['id']}/approve")
    assert r.status_code == 200 and r.json()["variance_status"] == "approved"
    assert balance(s, "CASH_OVER_SHORT") == D("0.500") and balance(s, "CASH_DRAWER") == D("4.500")


def test_manager_cannot_approve_own_drawer(salon):
    s = salon
    sess = open_drawer(s, user=s["manager"], amount="10.000")
    m = client_for(s["manager"], s["t"])
    m.post(f"/api/v1/pos/sessions/{sess['id']}/close", {"counted_cash": "11.000"}, format="json")
    r = m.post(f"/api/v1/pos/sessions/{sess['id']}/approve")
    assert r.status_code == 422 and r.json()["error"]["code"] == "variance_self_approval"


def test_discount_limit_and_override(salon):
    s = salon
    open_drawer(s)
    line = [{"service_id": s["wash"].id, "discount": "3.000"}]  # 20%
    r = checkout(s, s["cashier"], line, [{"method": "cash", "amount": "12.000"}])
    assert r.status_code == 422 and r.json()["error"]["code"] == "discount_over_limit"
    Membership.objects.filter(user=s["cashier"]).update(discount_limit_percent=20)
    r = checkout(s, s["cashier"], line, [{"method": "cash", "amount": "12.000"}], key="k2")
    assert r.status_code == 201 and r.json()["discount_total"] == "3.000"
    assert balance(s, "SERVICE_REVENUE") == D("-12.000")  # revenue is net of the discount
    r = checkout(s, s["manager"], [{"service_id": s["wash"].id, "discount": "10.000"}], [{"method": "cash", "amount": "5.000"}], key="k3")
    assert r.status_code == 201  # branch manager has pos.discount.override


def test_appointment_to_invoice_once(salon):
    s = salon
    open_drawer(s)
    a = book(s, soon()).json()
    r = checkout(s, s["cashier"], [{"service_id": s["cut"].id, "staff_id": s["staff"][0].id}],
                 [{"method": "cash", "amount": "5.000"}], appointment_id=a["id"])
    assert r.status_code == 201
    got = client_for(s["cashier"], s["t"]).get(f"/api/v1/booking/appointments/{a['id']}").json()
    assert got["status"] == "invoiced" and got["invoice_id"] == r.json()["id"]
    r = checkout(s, s["cashier"], [{"service_id": s["cut"].id}], [{"method": "cash", "amount": "5.000"}],
                 appointment_id=a["id"], key="k2")
    assert r.status_code == 409 and r.json()["error"]["code"] == "appointment_already_invoiced"


def test_checkout_is_idempotent_and_overpayment_refused(salon):
    s = salon
    open_drawer(s)
    args = (s, s["cashier"], [{"service_id": s["cut"].id}], [{"method": "cash", "amount": "5.000"}])
    r1, r2 = checkout(*args, key="same"), checkout(*args, key="same")
    assert r1.json()["id"] == r2.json()["id"] and r2.headers.get("Idempotent-Replay") == "true"
    assert balance(s, "CASH_DRAWER") == D("5.000")
    r = checkout(s, s["cashier"], [{"service_id": s["cut"].id}], [{"method": "cash", "amount": "6.000"}], key="over")
    assert r.status_code == 422 and r.json()["error"]["code"] == "overpayment"


def test_issued_documents_are_immutable_in_the_database(salon):
    s = salon
    open_drawer(s)
    inv = checkout(s, s["cashier"], [{"service_id": s["cut"].id}], [{"method": "cash", "amount": "5.000"}]).json()
    for sql in ["UPDATE pos_invoice SET total = 1 WHERE id = %s", "DELETE FROM pos_payment WHERE invoice_id = %s",
                "UPDATE pos_invoiceline SET unit_price = 0 WHERE invoice_id = %s"]:
        with pytest.raises(Exception, match="immutable"), transaction.atomic(), connection.cursor() as cur:
            cur.execute(sql, [inv["id"]])


def test_branch_scope_on_pos_and_booking(salon):
    s = salon
    other = s["b"]["SAL"].id
    c = client_for(s["cashier"], s["t"])
    r = c.post("/api/v1/pos/checkout", {"branch_id": other, "lines": [{"service_id": s["cut"].id}]}, format="json",
               HTTP_IDEMPOTENCY_KEY="x")
    assert r.status_code == 403
    assert c.get("/api/v1/booking/appointments", {"branch_id": other}).status_code == 403
