"""Phase 4: inventory at weighted average, purchasing (ex. 8), product sale with COGS (ex. 2), packages (ex. 5),
coupons, points, commissions (ex. 10), tips, staff hours and time off."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.dates import business_date

from apps.loyalty.models import LoyaltySettings
from apps.staff.models import StaffMember, TimeOff, WorkingHours
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Membership
from tests.conftest import add_member, client_for
from tests.test_phase3_operations import balance, book, checkout, open_drawer, salon, soon  # noqa: F401

pytestmark = pytest.mark.django_db
D = Decimal


def manager(s):
    return client_for(s["manager"], s["t"])


def owner(s):
    return client_for(s["owner"], s["t"])


def make_product(s, sku="SH1", price="3.000"):
    r = owner(s).post("/api/v1/inventory/products", {"sku": sku, "name_ar": "شامبو", "kind": "retail", "sale_price": price}, format="json")
    assert r.status_code == 201, r.content
    return r.json()


def receive(s, product_id, qty, cost, key):
    sup = owner(s).post("/api/v1/inventory/suppliers", {"name": "مورد"}, format="json").json()
    r = owner(s).post("/api/v1/inventory/receipts", {"branch_id": s["b"]["HAW"].id, "supplier_id": sup["id"],
                                                     "lines": [{"product_id": product_id, "qty": qty, "unit_cost": cost}]},
                      format="json", HTTP_IDEMPOTENCY_KEY=key)
    assert r.status_code == 201, r.content
    return r.json()


def test_purchasing_cycle_example_8(salon):
    s = salon
    p = make_product(s)
    grn = receive(s, p["id"], "10", "1.800", "g1")
    assert grn["number"].startswith("GRN-") and grn["total"] == "18.000"
    assert balance(s, "INVENTORY_RETAIL") == D("18.000") and balance(s, "GRNI") == D("-18.000")
    r = owner(s).post(f"/api/v1/inventory/receipts/{grn['id']}/bill", {"supplier_ref": "S-77", "amount": "17.500"}, format="json",
                      HTTP_IDEMPOTENCY_KEY="b0")
    assert r.status_code == 422 and r.json()["error"]["code"] == "bill_amount_mismatch"
    bill = owner(s).post(f"/api/v1/inventory/receipts/{grn['id']}/bill", {"supplier_ref": "S-77", "amount": "18.000"}, format="json",
                         HTTP_IDEMPOTENCY_KEY="b1").json()["bill"]
    assert balance(s, "GRNI") == 0 and balance(s, "AP_SUPPLIERS") == D("-18.000")
    owner(s).post(f"/api/v1/inventory/bills/{bill['id']}/payments", {"amount": "18.000", "reference": "TRX1"}, format="json",
                  HTTP_IDEMPOTENCY_KEY="p1")
    assert balance(s, "AP_SUPPLIERS") == 0 and balance(s, "BANK") == D("-18.000")
    # no expense booked by paying a supplier (the demo's bug)
    assert balance(s, "COGS_PRODUCTS") == 0


def test_weighted_average_and_product_sale_example_2(salon):
    s = salon
    p = make_product(s)
    receive(s, p["id"], "10", "1.800", "g1")
    receive(s, p["id"], "10", "2.200", "g2")          # average becomes 2.000
    open_drawer(s)
    r = checkout(s, s["cashier"], [{"product_id": p["id"], "qty": 2}], [{"method": "cash", "amount": "6.000"}])
    assert r.status_code == 201, r.content
    assert balance(s, "PRODUCT_REVENUE") == D("-6.000") and balance(s, "COGS_PRODUCTS") == D("4.000")
    assert balance(s, "INVENTORY_RETAIL") == D("36.000")  # 40 - 4
    prods = owner(s).get("/api/v1/inventory/products", {"branch_id": s["b"]["HAW"].id}).json()
    assert prods[0]["stock"]["qty"] == "18.000" and prods[0]["stock"]["avg_cost"] == "2.000000"
    # the cashier does not see costs
    assert "avg_cost" not in client_for(s["cashier"], s["t"]).get("/api/v1/inventory/products", {"branch_id": s["b"]["HAW"].id}).json()[0]["stock"]
    # selling more than in stock is refused
    r = checkout(s, s["cashier"], [{"product_id": p["id"], "qty": 50}], [{"method": "cash", "amount": "150.000"}], key="k2")
    assert r.status_code == 422 and r.json()["error"]["code"] == "stock_insufficient"


def test_product_return_restocks_at_original_cost(salon):
    s = salon
    p = make_product(s)
    receive(s, p["id"], "5", "2.000", "g1")
    open_drawer(s)
    inv = checkout(s, s["cashier"], [{"product_id": p["id"], "qty": 1}], [{"method": "cash", "amount": "3.000"}]).json()
    r = manager(s).post(f"/api/v1/pos/invoices/{inv['id']}/credit-notes", {"lines": [{"invoice_line_id": inv["lines"][0]["id"], "amount": "3.000",
                         "restock_qty": 1}], "reason": "مغلّف", "refund": {"method": "cash", "amount": "3.000"}}, format="json", HTTP_IDEMPOTENCY_KEY="r1")
    assert r.status_code == 201, r.content
    assert balance(s, "COGS_PRODUCTS") == 0 and balance(s, "INVENTORY_RETAIL") == D("10.000")
    assert owner(s).get("/api/v1/inventory/products", {"branch_id": s["b"]["HAW"].id}).json()[0]["stock"]["qty"] == "5.000"


def test_stock_adjustment_needs_reason_and_permission(salon):
    s = salon
    p = make_product(s)
    receive(s, p["id"], "5", "2.000", "g1")
    body = {"branch_id": s["b"]["HAW"].id, "product_id": p["id"], "qty_delta": "-1", "reason": "تالف"}
    assert client_for(s["cashier"], s["t"]).post("/api/v1/inventory/adjust", body, format="json").status_code == 403
    r = owner(s).post("/api/v1/inventory/adjust", body, format="json")
    assert r.status_code == 201 and r.json()["qty"] == "4.000"
    assert balance(s, "COGS_PRODUCTS") == D("2.000") and balance(s, "INVENTORY_RETAIL") == D("8.000")


def test_package_sale_and_use_example_5(salon):
    s = salon
    cust = manager(s).post("/api/v1/customers", {"full_name": "أم يوسف", "phone": "55552222"}, format="json").json()
    plan = owner(s).post("/api/v1/loyalty/plans", {"name_ar": "3 قصات", "service": s["cut"].id, "sessions": 3, "price": "12.000"},
                         format="json").json()
    open_drawer(s)
    r = checkout(s, s["cashier"], [{"package_plan_id": plan["id"]}], [{"method": "cash", "amount": "12.000"}], customer_id=cust["id"])
    assert r.status_code == 201, r.content
    # collection is not revenue: the money is a liability
    assert balance(s, "CONTRACT_LIABILITY_PACKAGES") == D("-12.000") and balance(s, "SERVICE_REVENUE") == 0
    wallet = client_for(s["cashier"], s["t"]).get(f"/api/v1/customers/{cust['id']}/wallet").json()
    pkg = wallet["packages"][0]
    assert pkg["sessions_left"] == 3 and pkg["session_value"] == "4.000"
    r = checkout(s, s["cashier"], [{"service_id": s["cut"].id, "redeem_package_id": pkg["id"], "staff_id": s["staff"][0].id}],
                 [], customer_id=cust["id"], key="k2")
    assert r.status_code == 201 and r.json()["total"] == "0.000"
    assert balance(s, "CONTRACT_LIABILITY_PACKAGES") == D("-8.000") and balance(s, "SERVICE_REVENUE") == D("-4.000")
    assert client_for(s["cashier"], s["t"]).get(f"/api/v1/customers/{cust['id']}/wallet").json()["packages"][0]["sessions_left"] == 2
    # a used package cannot be returned
    sale = r.json()
    first = manager(s).get("/api/v1/pos/invoices", {"q": cust["full_name"]}).json()
    pkg_inv = [x for x in first if x["lines"][0]["kind"] == "package"][0]
    rr = manager(s).post(f"/api/v1/pos/invoices/{pkg_inv['id']}/credit-notes", {"lines": [{"invoice_line_id": pkg_inv["lines"][0]["id"],
                          "amount": "12.000"}], "reason": "x"}, format="json", HTTP_IDEMPOTENCY_KEY="r9")
    assert rr.json()["error"]["code"] == "package_already_used"
    assert sale["lines"][0]["redeemed_package_id"] == pkg["id"]


def test_coupon_discount_and_max_uses(salon):
    s = salon
    today = business_date()
    owner(s).post("/api/v1/loyalty/coupons", {"code": "eid20", "kind": "percent", "value": "20", "valid_from": str(today),
                                              "valid_to": str(today + timedelta(days=5)), "max_uses": 1}, format="json")
    open_drawer(s)
    r = checkout(s, s["cashier"], [{"service_id": s["wash"].id}], [{"method": "cash", "amount": "12.000"}], coupon_code="EID20")
    assert r.status_code == 201, r.content
    assert r.json()["discount_total"] == "3.000" and r.json()["total"] == "12.000"   # coupons do not hit the cashier's own limit
    r = checkout(s, s["cashier"], [{"service_id": s["wash"].id}], [{"method": "cash", "amount": "12.000"}], coupon_code="EID20", key="k2")
    assert r.json()["error"]["code"] == "coupon_used_up"


def test_points_earn_redeem_and_reverse(salon):
    s = salon
    with tenant_context(s["t"].id):
        LoyaltySettings.objects.create(enabled=True, points_per_kd=10, point_value="0.010", min_redeem=50)
    cust = manager(s).post("/api/v1/customers", {"full_name": "خالد", "phone": "55553333"}, format="json").json()
    open_drawer(s)
    checkout(s, s["cashier"], [{"service_id": s["wash"].id}], [{"method": "cash", "amount": "15.000"}], customer_id=cust["id"])
    w = client_for(s["cashier"], s["t"]).get(f"/api/v1/customers/{cust['id']}/wallet").json()
    assert w["points"] == 150
    r = checkout(s, s["cashier"], [{"service_id": s["cut"].id}], [{"method": "cash", "amount": "4.000"}], customer_id=cust["id"],
                 redeem_points=100, key="k2")
    assert r.status_code == 201, r.content
    assert r.json()["total"] == "4.000" and r.json()["points_redeemed"] == 100
    assert client_for(s["cashier"], s["t"]).get(f"/api/v1/customers/{cust['id']}/wallet").json()["points"] == 150 - 100 + 40
    r = checkout(s, s["cashier"], [{"service_id": s["cut"].id}], [{"method": "cash", "amount": "5.000"}], customer_id=cust["id"],
                 redeem_points=500, key="k3")
    assert r.json()["error"]["code"] == "points_insufficient"


def test_commission_accrual_reversal_payout_example_10(salon):
    s = salon
    with tenant_context(s["t"].id):
        StaffMember.objects.filter(id=s["staff"][0].id).update(commission_percent=10)
    open_drawer(s)
    inv = checkout(s, s["cashier"], [{"service_id": s["wash"].id, "staff_id": s["staff"][0].id}],
                   [{"method": "cash", "amount": "15.000"}]).json()
    assert balance(s, "COMMISSION_EXPENSE") == D("1.500") and balance(s, "COMMISSIONS_PAYABLE") == D("-1.500")
    manager(s).post(f"/api/v1/pos/invoices/{inv['id']}/credit-notes", {"lines": [{"invoice_line_id": inv["lines"][0]["id"], "amount": "5.000"}],
                    "reason": "جزئي"}, format="json", HTTP_IDEMPOTENCY_KEY="r1")
    assert balance(s, "COMMISSIONS_PAYABLE") == D("-1.000")
    rows = owner(s).get("/api/v1/commissions").json()
    assert [r["balance"] for r in rows if r["staff_id"] == s["staff"][0].id] == ["1.000"]
    r = owner(s).post(f"/api/v1/staff/{s['staff'][0].id}/payout", {"amount": "1.000", "reference": "SAL-10", "branch_id": s["b"]["HAW"].id},
                      format="json")
    assert r.status_code == 201 and r.json()["balance"] == "0.000"
    assert balance(s, "COMMISSIONS_PAYABLE") == 0
    assert client_for(s["cashier"], s["t"]).get("/api/v1/commissions").status_code == 403


def test_tip_is_not_revenue(salon):
    s = salon
    open_drawer(s)
    r = checkout(s, s["cashier"], [{"service_id": s["cut"].id}], [{"method": "cash", "amount": "6.000"}], tip="1.000",
                 tip_staff_id=s["staff"][0].id)
    assert r.status_code == 201, r.content
    assert r.json()["state"]["balance"] == "0.000"
    assert balance(s, "SERVICE_REVENUE") == D("-5.000") and balance(s, "TIPS_PAYABLE") == D("-1.000")
    assert balance(s, "CASH_DRAWER") == D("6.000") and balance(s, "AR_CUSTOMERS") == 0


def test_working_hours_and_time_off_limit_bookings(salon):
    s = salon
    mona = s["staff"][0]
    day = (timezone.localtime() + timedelta(days=2)).date()
    r = owner(s).put(f"/api/v1/staff/{mona.id}/schedule", {"hours": [{"branch_id": s["b"]["HAW"].id, "weekday": day.weekday(),
                                                                       "starts_at": "10:00", "ends_at": "14:00"}]}, format="json")
    assert r.status_code == 200, r.content
    tz = timezone.get_current_timezone()
    from datetime import datetime
    inside = datetime.combine(day, datetime.strptime("11:00", "%H:%M").time(), tzinfo=tz)
    outside = datetime.combine(day, datetime.strptime("15:00", "%H:%M").time(), tzinfo=tz)
    assert book(s, inside, key="in").status_code == 201
    r = book(s, outside, key="out")
    assert r.status_code == 422 and r.json()["error"]["code"] == "staff_unavailable"
    owner(s).post(f"/api/v1/staff/{mona.id}/time-off", {"starts_at": (inside + timedelta(hours=1)).isoformat(),
                                                        "ends_at": (inside + timedelta(hours=2)).isoformat(), "reason": "دكتور"}, format="json")
    r = book(s, inside + timedelta(hours=1), key="off")
    assert r.json()["error"]["code"] == "staff_unavailable"


def test_quote_matches_checkout_and_writes_nothing(salon):
    s = salon
    today = business_date()
    owner(s).post("/api/v1/loyalty/coupons", {"code": "Q15", "kind": "percent", "value": "15", "valid_from": str(today),
                                              "valid_to": str(today), "max_uses": 1}, format="json")
    body = {"branch_id": s["b"]["HAW"].id, "lines": [{"service_id": s["wash"].id}, {"service_id": s["cut"].id}], "coupon_code": "Q15"}
    q = client_for(s["cashier"], s["t"]).post("/api/v1/pos/quote", body, format="json").json()
    assert q["total"] == "17.000" and q["coupon_discount"] == "3.000"
    q2 = client_for(s["cashier"], s["t"]).post("/api/v1/pos/quote", body, format="json").json()
    assert q2 == q  # the coupon was not consumed by quoting
    open_drawer(s)
    r = checkout(s, s["cashier"], body["lines"], [{"method": "cash", "amount": q["total"]}], coupon_code="Q15", expected_total=q["total"])
    assert r.status_code == 201 and r.json()["total"] == q["total"]


def test_points_tiers_welcome_birthday_and_expiry(salon):
    from datetime import date
    from apps.customers.models import Customer
    from apps.loyalty.models import PointsEntry
    from apps.loyalty.services import points as pts
    s = salon
    with tenant_context(s["t"].id):
        LoyaltySettings.objects.create(enabled=True, points_per_kd=10, point_value="0.010", min_redeem=50, welcome_points=5,
                                       birthday_points=20, expiry_months=12)
    r = owner(s).patch("/api/v1/loyalty/settings", {"tiers": [{"name_ar": "فضي", "min": 100, "mul": 2}, {"name_ar": "برونزي", "min": 0, "mul": 1}]},
                       format="json")
    assert r.status_code == 200 and [t["min"] for t in r.json()["tiers"]] == [0, 100]
    bad = owner(s).patch("/api/v1/loyalty/settings", {"tiers": [{"name_ar": "x", "min": 5, "mul": 1}]}, format="json")
    assert bad.status_code == 400
    cust = manager(s).post("/api/v1/customers", {"full_name": "خالد", "phone": "55553334"}, format="json").json()
    manager(s).post(f"/api/v1/customers/{cust['id']}/beneficiaries", {"full_name": "ليلى", "relation": "child", "birth_date": "2018-06-10"},
                    format="json")
    open_drawer(s)
    checkout(s, s["cashier"], [{"service_id": s["wash"].id}], [{"method": "cash", "amount": "15.000"}], customer_id=cust["id"])
    wallet = lambda: client_for(s["cashier"], s["t"]).get(f"/api/v1/customers/{cust['id']}/wallet").json()["points"]  # noqa: E731
    assert wallet() == 150 + 5                          # bronze ×1 + welcome gift once
    checkout(s, s["cashier"], [{"service_id": s["cut"].id}], [{"method": "cash", "amount": "5.000"}], customer_id=cust["id"], key="k2")
    assert wallet() == 155 + 100                        # now silver: ×2, no second welcome
    ov = owner(s).get("/api/v1/loyalty/points").json()
    assert ov["balances"][0]["tier"] == "فضي" and [t["customers"] for t in ov["tiers"]] == [0, 1]
    with tenant_context(s["t"].id):
        assert pts.birthday_gifts(date(2026, 6, 10)) == 1 and pts.birthday_gifts(date(2026, 6, 10)) == 0
        assert pts.birthday_gifts(date(2026, 6, 11)) == 0
        c = Customer.objects.get(id=cust["id"])
        assert pts.expire_inactive(business_date()) == 0                     # active customer keeps points
        assert pts.expire_inactive(business_date().replace(year=business_date().year + 2)) == 1
        assert pts.balance(c) == 0 and PointsEntry.objects.filter(customer=c, kind="expire").count() == 1
