"""Reports from issued documents, branch scope, cost visibility; salon and platform settings; CSV export."""
import pytest

from apps.identity.models import User
from tests.conftest import client_for
from tests.test_phase3_operations import checkout, open_drawer, salon  # noqa: F401

pytestmark = pytest.mark.django_db


def sell(s, key, amount_lines, staff=None):
    lines = [{"service_id": sid, "staff_id": (staff or s["staff"][0]).id} for sid in amount_lines]
    r = checkout(s, s["cashier"], lines, key=key)
    total = r.json().get("total") if r.status_code == 201 else None
    if total is None:
        q = client_for(s["cashier"], s["t"]).post("/api/v1/pos/quote", {"branch_id": s["b"]["HAW"].id, "lines": lines}, format="json").json()
        r = checkout(s, s["cashier"], lines, [{"method": "cash", "amount": q["total"]}], key=key + "p")
    assert r.status_code == 201, r.content
    return r.json()


def test_sales_report_numbers_scope_and_cost(salon):
    s = salon
    open_drawer(s)
    sell(s, "a", [s["cut"].id])                    # 5.000
    sell(s, "b", [s["cut"].id, s["wash"].id])      # 20.000
    m = client_for(s["manager"], s["t"]).get(f"/api/v1/reports/sales?branch_id={s['b']['HAW'].id}").json()
    assert m["stats"]["sales"] == "25.000" and m["stats"]["invoices"] == 2 and m["stats"]["average"] == "12.500"
    assert m["items"][0]["name_ar"] == "غسيل" and m["items"][0]["total"] == "15.000"
    assert {x["method"]: x["total"] for x in m["methods"]} == {"cash": "25.000"}
    assert sum(h["invoices"] for h in m["hours"]) == 2 and m["staff"][0]["total"] == "25.000"
    owner = client_for(s["owner"], s["t"]).get("/api/v1/reports/sales").json()
    assert owner["profit"]["sales"] == "25.000"                       # cost/profit only with report.view.cost_profit
    assert "profit" not in m                                           # a branch manager does not see cost and profit
    other = s["b"]["JAH"].id
    assert client_for(s["manager"], s["t"]).get(f"/api/v1/reports/sales?branch_id={other}").status_code == 403
    br = client_for(s["owner"], s["t"]).get("/api/v1/reports/branches").json()
    haw = next(x for x in br if x["branch_id"] == s["b"]["HAW"].id)
    assert haw["today"] == "25.000" and haw["invoices_today"] == 2 and haw["drawer_open"]


def test_salon_and_platform_settings_and_export(salon):
    s = salon
    o = client_for(s["owner"], s["t"])
    assert o.patch("/api/v1/salon-settings", {"receipt_footer_ar": "نورتونا", "commercial_registration": "12345"}, format="json").json()["receipt_footer_ar"] == "نورتونا"
    assert client_for(s["cashier"], s["t"]).get("/api/v1/salon-settings").json()["commercial_registration"] == "12345"
    assert client_for(s["cashier"], s["t"]).patch("/api/v1/salon-settings", {"receipt_footer_ar": "x"}, format="json").status_code == 403
    csv = o.get("/api/v1/export/customers")
    assert csv.status_code == 200 and csv.content.startswith("﻿".encode()) and b"phone" in csv.content
    assert client_for(s["cashier"], s["t"]).get("/api/v1/export/customers").status_code == 403
    ops = User.objects.create_user("ops@qassa.test", "Ops-Pass-2026!!", is_platform_staff=True)
    c = client_for(ops)
    assert c.patch("/api/v1/platform/settings", {"sales_whatsapp": "55512345", "trial_days": 14}, format="json").json()["sales_whatsapp"] == "96555512345"
    from rest_framework.test import APIClient
    site = APIClient().get("/api/v1/public/site").json()
    assert site["whatsapp"] == "96555512345" and site["trial_days"] == 14
    assert client_for(s["owner"]).patch("/api/v1/platform/settings", {"trial_days": 1}, format="json").status_code == 403


def test_kids_list_visits_and_spend(salon):
    s = salon
    c = client_for(s["owner"], s["t"])
    cust = c.post("/api/v1/customers", {"full_name": "أم يوسف", "phone": "55123456", "add_self": False}, format="json").json()
    kid = c.post(f"/api/v1/customers/{cust['id']}/beneficiaries", {"full_name": "يوسف", "relation": "child"}, format="json").json()
    open_drawer(s)
    lines = [{"service_id": s["cut"].id, "staff_id": s["staff"][0].id}]
    q = client_for(s["cashier"], s["t"]).post("/api/v1/pos/quote", {"branch_id": s["b"]["HAW"].id, "lines": lines}, format="json").json()
    r = checkout(s, s["cashier"], lines, [{"method": "cash", "amount": q["total"]}], key="kid1", customer_id=cust["id"], beneficiary_id=kid["id"])
    assert r.status_code == 201, r.content
    rows = c.get("/api/v1/customers/kids?q=يوسف").json()
    assert len(rows) == 1 and rows[0]["guardian"] == "أم يوسف" and rows[0]["phone"] == "96555123456"
    assert rows[0]["visits"] == 1 and rows[0]["total"] == q["total"] and rows[0]["last_visit"]
    assert c.get("/api/v1/customers/kids?q=nobody").json() == []


def test_points_overview_and_manual_adjust(salon):
    s = salon
    c = client_for(s["owner"], s["t"])
    cust = c.post("/api/v1/customers", {"full_name": "أم ليلى", "phone": "55111222", "add_self": False}, format="json").json()
    assert c.post("/api/v1/loyalty/points/adjust", {"customer_id": cust["id"], "points": -5, "note": "x"}, format="json").json()["error"]["code"] == "points_insufficient"
    assert c.post("/api/v1/loyalty/points/adjust", {"customer_id": cust["id"], "points": 0, "note": "x"}, format="json").json()["error"]["code"] == "points_zero"
    r = c.post("/api/v1/loyalty/points/adjust", {"customer_id": cust["id"], "points": 40, "note": "هدية عيد ميلاد"}, format="json")
    assert r.status_code == 200 and r.json()["balance"] == 40
    assert c.post("/api/v1/loyalty/points/adjust", {"customer_id": cust["id"], "points": -15, "note": "تصحيح"}, format="json").json()["balance"] == 25
    o = c.get("/api/v1/loyalty/points").json()
    assert o["outstanding"] == 25 and o["balances"][0]["balance"] == 25 and o["recent"][0]["points"] == -15
    assert client_for(s["cashier"], s["t"]).post("/api/v1/loyalty/points/adjust", {"customer_id": cust["id"], "points": 5, "note": "x"}, format="json").status_code == 403


def test_throttle_keys_on_the_address_traefik_saw(settings):
    """Behind Traefik -> nginx, a client-made X-Forwarded-For prefix must not create a fresh throttle bucket."""
    from rest_framework.settings import api_settings
    from rest_framework.test import APIRequestFactory
    from rest_framework.throttling import SimpleRateThrottle
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "NUM_PROXIES": 2}
    api_settings.reload()
    try:
        f = APIRequestFactory()
        ident = lambda xff: SimpleRateThrottle.get_ident(None, f.get("/", HTTP_X_FORWARDED_FOR=xff, REMOTE_ADDR="10.0.0.9"))
        assert ident("1.1.1.1, 203.0.113.7, 10.0.0.5") == ident("9.9.9.9, 203.0.113.7, 10.0.0.5") == "203.0.113.7"
        assert ident("203.0.113.8, 10.0.0.5") == "203.0.113.8"
    finally:
        api_settings.reload()


def test_login_limit_holds_under_a_parallel_burst(db, settings):
    """15 logins at once against a 10/min limit: exactly 10 get through, the rest are refused with 429."""
    from concurrent.futures import ThreadPoolExecutor
    from django.core.cache import cache
    from rest_framework.test import APIClient
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": "redis://localhost:6379/9"}}
    cache.clear()

    def hit(_):
        return APIClient().post("/api/v1/auth/login", {}, format="json", REMOTE_ADDR="198.51.100.20").status_code
    with ThreadPoolExecutor(max_workers=15) as ex:
        codes = list(ex.map(hit, range(15)))
    assert codes.count(429) == 5 and codes.count(400) == 10, codes
