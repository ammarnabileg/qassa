"""Offline selling (D-013): signed receipts, idempotent sync, promotions no longer valid become reviewed discounts,
conflicts stay visible and can be retried, missing sequence numbers are reported."""
import uuid
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.pos.models import Invoice, OfflineSale
from apps.pos.services.offline import sign
from apps.tenancy.context import tenant_context
from tests.conftest import client_for
from tests.test_phase3_operations import open_drawer, salon  # noqa: F401
from tests.test_phase4 import make_product, owner, receive

pytestmark = pytest.mark.django_db


def drawer(s):
    """A drawer opened an hour ago (the offline receipts below happened while it was open)."""
    from apps.pos.models import CashSession
    open_drawer(s)
    with tenant_context(s["t"].id):
        CashSession.objects.update(opened_at=timezone.now() - timedelta(hours=1))


def device(s, user=None):
    r = client_for(user or s["cashier"], s["t"]).post("/api/v1/pos/devices", {"branch_id": s["b"]["HAW"].id, "name": "تابلت 1"}, format="json")
    assert r.status_code == 201
    return r.json()


def receipt(dev, seq, lines, total, payments=None, minutes_ago=10, **extra):
    payload = {"uuid": str(uuid.uuid4()), "seq": seq, "created_at": (timezone.now() - timedelta(minutes=minutes_ago)).isoformat(),
               "lines": lines, "payments": payments if payments is not None else [{"method": "cash", "amount": total}], "total": total, **extra}
    return {"payload": payload, "signature": sign(dev["secret"], payload)}


def sync(s, dev, *items, user=None):
    r = client_for(user or s["cashier"], s["t"]).post("/api/v1/pos/offline/sync", {"device_id": dev["id"], "sales": list(items)}, format="json")
    assert r.status_code == 200, r.content
    return r.json()["results"]


def test_bundle_has_prices_for_the_till(salon):
    b = client_for(salon["cashier"], salon["t"]).get(f"/api/v1/pos/offline/bundle?branch_id={salon['b']['HAW'].id}").json()
    assert {x["name_ar"]: x["price"] for x in b["services"]} == {"قص": "5.000", "غسيل": "15.000"}
    assert "secret" not in str(b)


def test_offline_sale_posts_once_with_its_offline_time_and_reference(salon):
    s = salon
    drawer(s)
    dev = device(s)
    item = receipt(dev, 1, [{"service_id": s["cut"].id, "unit_price": "5.000", "staff_id": s["staff"][0].id}], "5.000")
    first = sync(s, dev, item)[0]
    assert first["status"] == "synced" and first["invoice_number"].startswith("INV-") and first["ref"] == f"OFF-{dev['id']}-1"
    assert sync(s, dev, item)[0]["invoice_id"] == first["invoice_id"]          # resend: same invoice, nothing new
    with tenant_context(s["t"].id):
        inv = Invoice.objects.get(id=first["invoice_id"])
        assert inv.offline_ref == first["ref"] and inv.offline_at is not None and Invoice.objects.count() == 1
        assert inv.payments.get().cash_session_id is not None


def test_forged_or_altered_receipt_is_refused(salon):
    s = salon
    drawer(s)
    dev = device(s)
    item = receipt(dev, 1, [{"service_id": s["cut"].id, "unit_price": "5.000"}], "5.000")
    item["payload"]["total"] = "1.000"
    assert sync(s, dev, item)[0]["rejected"] == "offline_signature_invalid"
    old = receipt(dev, 2, [{"service_id": s["cut"].id, "unit_price": "5.000"}], "5.000", minutes_ago=60 * 24 * 9)
    assert sync(s, dev, old)[0]["rejected"] == "offline_time_invalid"
    with tenant_context(s["t"].id):
        assert Invoice.objects.count() == 0


def test_coupon_used_up_on_another_device_keeps_the_paid_amount_for_review(salon):
    s = salon
    drawer(s)
    today = timezone.localdate()
    owner(s).post("/api/v1/loyalty/coupons", {"code": "ONE", "kind": "percent", "value": "20", "valid_from": str(today - timedelta(days=1)),
                                              "valid_to": str(today + timedelta(days=1)), "max_uses": 1}, format="json")
    d1, d2 = device(s), device(s, s["manager"])
    line = [{"service_id": s["wash"].id, "unit_price": "15.000"}]
    a = sync(s, d1, receipt(d1, 1, line, "12.000", coupon_code="ONE"))[0]
    b = sync(s, d2, receipt(d2, 1, line, "12.000", coupon_code="ONE"), user=s["manager"])[0]
    assert a["status"] == "synced"
    assert b["status"] == "review" and b["flags"] == ["promotion_not_honoured:coupon_used_up"]
    with tenant_context(s["t"].id):
        inv = Invoice.objects.get(id=b["invoice_id"])
        assert str(inv.total) == "12.000" and inv.coupon_id is None and str(inv.discount_total) == "3.000"
    m = client_for(s["manager"], s["t"])
    assert m.get("/api/v1/pos/offline/sales?status=review").json()[0]["id"] == b["id"]
    assert client_for(s["cashier"], s["t"]).post(f"/api/v1/pos/offline/sales/{b['id']}/acknowledge").status_code == 403
    assert m.post(f"/api/v1/pos/offline/sales/{b['id']}/acknowledge").json()["status"] == "synced"


def test_price_changed_meanwhile_is_kept_and_flagged(salon):
    from apps.catalog.services.pricing import set_price
    s = salon
    drawer(s)
    dev = device(s)
    with tenant_context(s["t"].id):
        set_price(s["cut"], price="6.000")       # raised today while the tablet was offline with the old price
    r = sync(s, dev, receipt(dev, 1, [{"service_id": s["cut"].id, "unit_price": "5.000"}], "5.000"))[0]
    assert r["status"] == "review" and r["flags"] == ["price_changed:0"]


def test_stock_conflict_then_retry_and_missing_sequence(salon):
    s = salon
    drawer(s)
    p = make_product(s, "SH9", "3.000")
    dev = device(s)
    r = sync(s, dev, receipt(dev, 1, [{"product_id": p["id"], "unit_price": "3.000"}], "3.000"),
             receipt(dev, 3, [{"service_id": s["cut"].id, "unit_price": "5.000"}], "5.000"))
    assert r[0]["status"] == "conflict" and r[0]["error"] == "stock_insufficient" and r[1]["status"] == "synced"
    devices = client_for(s["manager"], s["t"]).get("/api/v1/pos/devices").json()
    assert devices[0]["missing_seq"] == [2]                                  # receipt 2 never arrived
    receive(s, p["id"], "5", "1.000", "g1")
    again = client_for(s["manager"], s["t"]).post(f"/api/v1/pos/offline/sales/{r[0]['id']}/retry").json()
    assert again["status"] == "synced" and again["invoice_id"]
    with tenant_context(s["t"].id):
        assert OfflineSale.objects.filter(status="conflict").count() == 0


def test_reused_number_or_malformed_receipt_creates_no_invoice(salon):
    s = salon
    drawer(s)
    dev = device(s)
    sync(s, dev, receipt(dev, 1, [{"service_id": s["cut"].id, "unit_price": "5.000"}], "5.000"))
    again = receipt(dev, 1, [{"service_id": s["wash"].id, "unit_price": "15.000"}], "15.000")      # new uuid, same number
    bad_qty = receipt(dev, 2, [{"service_id": s["cut"].id, "unit_price": "abc"}], "5.000")
    r = sync(s, dev, again, bad_qty, {"payload": "not-a-dict", "signature": "x"})
    assert sorted(x.get("rejected") or x["status"] for x in r) == ["offline_payload_invalid", "offline_seq_reused", "offline_signature_invalid"]
    with tenant_context(s["t"].id):
        assert Invoice.objects.count() == 1 and OfflineSale.objects.filter(invoice__isnull=False).count() == 1
