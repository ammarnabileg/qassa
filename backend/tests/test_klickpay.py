"""KlickPay (D-017): salon documents and platform review, credentials and webhook secret, invoice payment link,
signed webhook -> server-side status check -> receipt and ledger, and the platform's commission report."""
import hashlib
import hmac
import json
import time
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.core.services.infra import process_outbox
from apps.identity.models import User
from apps.payments.models import GatewayAccount, KycDocumentType, OnlinePayment
from apps.payments.services import klickpay
from apps.pos.models import Payment
from apps.tenancy.context import tenant_context
from tests.conftest import client_for
from tests.test_phase3_operations import balance, checkout, salon  # noqa: F401

pytestmark = pytest.mark.django_db
D = Decimal


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


class FakeKlickPay:
    def __init__(self):
        self.calls, self.status = [], {"status": "created"}

    def __call__(self, method, url, headers, body=None):
        self.calls.append((url.rsplit("/v3", 1)[-1], headers, body))
        if url.endswith("/auth/token"):
            return 200, {"data": {"access_token": "tok"}}
        if url.endswith("/payments/general-link"):
            return 200, {"success": True, "data": {"payment_id": "QI123ABC", "payment_url": "https://pstaging.maakpay.com/checkout.php?invoice_id=QI123ABC"}}
        if url.endswith("/payments/status"):
            return 200, {"success": True, "data": {"payment_id": "QI123ABC", **self.status}}
        return 404, {}


@pytest.fixture
def kp(monkeypatch):
    fake = FakeKlickPay()
    monkeypatch.setattr(klickpay, "_http", fake)
    return fake


def ops():
    return client_for(User.objects.create_user("ops@k.test", "Ops-Pass-2026!!", is_platform_staff=True))


def pdf(name="doc.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4 test", content_type="application/pdf")


def test_documents_review_and_activation(salon, kp):
    s = salon
    owner = client_for(s["owner"], s["t"])
    a = owner.get("/api/v1/payments/account").json()
    assert a["status"] == "not_started" and len(a["checklist"]) == KycDocumentType.objects.count()
    required = [i["type"]["id"] for i in a["checklist"] if i["type"]["required"]]
    owner.post("/api/v1/payments/kyc", {"doc_type": required[0], "file": pdf()}, format="multipart")
    assert owner.post("/api/v1/payments/kyc/submit").json()["error"]["code"] == "kyc_missing_documents"
    assert owner.post("/api/v1/payments/kyc", {"doc_type": required[1], "file": SimpleUploadedFile("x.exe", b"MZ")},
                      format="multipart").json()["error"]["code"] == "kyc_file_type"
    for t in required[1:]:
        assert owner.post("/api/v1/payments/kyc", {"doc_type": t, "file": pdf()}, format="multipart").status_code == 201
    assert owner.post("/api/v1/payments/kyc/submit").json()["status"] == "under_review"
    assert owner.post("/api/v1/payments/kyc", {"doc_type": required[0], "file": pdf()}, format="multipart").json()["error"]["code"] == "kyc_locked"
    # platform rejects one document with a note -> the salon sees which one and why
    p = ops()
    detail = p.get(f"/api/v1/platform/payments/accounts/{s['t'].id}").json()
    first = detail["checklist"][0]["doc"]["id"]
    assert p.get(f"/api/v1/platform/payments/kyc/{first}/file").status_code == 200
    assert p.post(f"/api/v1/platform/payments/kyc/{first}/review", {"accept": False}, format="json").json()["error"]["code"] == "kyc_note_required"
    r = p.post(f"/api/v1/platform/payments/kyc/{first}/review", {"accept": False, "note": "الرخصة منتهية"}, format="json").json()
    assert r["account_status"] == "needs_changes"
    mine = owner.get("/api/v1/payments/account").json()
    assert mine["status"] == "needs_changes" and mine["checklist"][0]["doc"]["note"] == "الرخصة منتهية"
    owner.post("/api/v1/payments/kyc", {"doc_type": required[0], "file": pdf("new.pdf")}, format="multipart")
    assert owner.post("/api/v1/payments/kyc/submit").json()["status"] == "under_review"
    # activation needs credentials and a webhook secret; the secret is shown once
    assert p.patch(f"/api/v1/platform/payments/accounts/{s['t'].id}", {"status": "active"}, format="json").json()["error"]["code"] == "gateway_incomplete"
    r = p.patch(f"/api/v1/platform/payments/accounts/{s['t'].id}", {"client_id": "cid", "client_secret": "csecret", "new_webhook_secret": True,
                                                                 "commission_percent": "1.50", "commission_fixed": "0.050"}, format="json").json()
    assert r["webhook_secret"] and "/api/v1/payments/klickpay/webhook/" in r["webhook_url"] and "client_secret" not in r
    again = p.get(f"/api/v1/platform/payments/accounts/{s['t'].id}").json()
    assert "webhook_secret" not in again and again["has_secret"]
    assert p.patch(f"/api/v1/platform/payments/accounts/{s['t'].id}", {"status": "active"}, format="json").json()["status"] == "active"
    assert client_for(s["owner"], s["t"]).get("/api/v1/platform/payments/accounts").status_code == 403


def _activate(s):
    p = ops()
    r = p.patch(f"/api/v1/platform/payments/accounts/{s['t'].id}", {"client_id": "cid", "client_secret": "csecret", "new_webhook_secret": True,
                                                                 "commission_percent": "2.00", "commission_fixed": "0.100", "status": "active"},
                format="json").json()
    return p, r["webhook_url"].rsplit("/", 1)[1], r["webhook_secret"]


def _signed(secret, body, ts=None):
    raw = json.dumps(body).encode()
    ts = str(ts or int(time.time()))
    return raw, {"HTTP_X_KLICKPAY_SIGNATURE": hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest(),
                 "HTTP_X_KLICKPAY_TIMESTAMP": ts, "HTTP_X_KLICKPAY_EVENT": body["event_type"]}


def _credit_invoice(s):
    c = client_for(s["manager"], s["t"])
    cust = c.post("/api/v1/customers", {"full_name": "أم يوسف", "phone": "55551111"}, format="json").json()
    return checkout(s, s["manager"], [{"service_id": s["wash"].id}], customer_id=cust["id"], key="c2").json()


def test_pay_link_then_signed_webhook_records_the_receipt(salon, kp):
    s = salon
    p, token, secret = _activate(s)
    inv = _credit_invoice(s)
    m = client_for(s["manager"], s["t"])
    r = m.post(f"/api/v1/pos/invoices/{inv['id']}/pay-link", {"send": False}, format="json")
    assert r.status_code == 200 and r.json()["payment_url"].startswith("https://") and r.json()["amount"] == "15.000"
    sent = kp.calls[-1][2]
    assert sent["transction_amount"] == 15.0 and sent["success_page"].endswith("/pay/" + r.json()["reference"]) and sent["source"] == "web_app"
    assert m.post(f"/api/v1/pos/invoices/{inv['id']}/pay-link", {}, format="json").json()["reference"] == r.json()["reference"]  # reused
    hook = f"/api/v1/payments/klickpay/webhook/{token}"
    body = {"invoice_id": "QI123ABC", "payment_id": "617010000149659", "event_type": "payment.success", "amount": "15.000", "result": "CAPTURED"}
    raw, h = _signed("wrong", body)
    assert APIClient().post(hook, raw, content_type="application/json", **h).status_code == 401
    raw, h = _signed(secret, body, ts=int(time.time()) - 3600)
    assert APIClient().post(hook, raw, content_type="application/json", **h).status_code == 401        # stale
    # the webhook alone records nothing: KlickPay still says "created"
    raw, h = _signed(secret, body)
    assert APIClient().post(hook, raw, content_type="application/json", **h).json()["result"] == "ok"
    process_outbox()
    with tenant_context(s["t"].id):
        assert OnlinePayment.objects.get().status == "created" and not Payment.objects.filter(method="online").exists()
    # paid at KlickPay -> the check writes the receipt once; a re-delivery is ignored
    kp.status = {"status": "paid", "result": "CAPTURED", "amount": "15.000", "payment_method": "KNET"}
    raw, h = _signed(secret, body)
    assert APIClient().post(hook, raw, content_type="application/json", **h).json()["result"] == "duplicate"   # same event again
    process_outbox()
    raw, h = _signed(secret, body)
    APIClient().post(hook, raw, content_type="application/json", **h)
    process_outbox()
    with tenant_context(s["t"].id):
        op = OnlinePayment.objects.get()
        assert op.status == "paid" and op.method == "KNET" and Payment.objects.filter(method="online").count() == 1
    assert balance(s, "GATEWAY_CLEARING") == D("15.000") and balance(s, "AR_CUSTOMERS") == 0
    assert m.get(f"/api/v1/pos/invoices/{inv['id']}").json()["state"]["balance"] == "0.000"
    assert APIClient().get(f"/api/v1/public/pay/{op.reference}").json()["status"] == "paid"
    rep = p.get("/api/v1/platform/payments/report").json()
    row = next(x for x in rep["rows"] if x["tenant_id"] == s["t"].id)
    assert row["paid_count"] == 1 and row["paid_amount"] == "15.000" and row["commission"] == "0.400"   # 2% + 0.100


def test_amount_mismatch_goes_to_review_and_till_cannot_fake_online(salon, kp):
    s = salon
    _activate(s)
    inv = _credit_invoice(s)
    m = client_for(s["manager"], s["t"])
    ref = m.post(f"/api/v1/pos/invoices/{inv['id']}/pay-link", {}, format="json").json()["reference"]
    kp.status = {"status": "paid", "result": "CAPTURED", "amount": "1.000"}
    APIClient().get(f"/api/v1/public/pay/{ref}")
    process_outbox()
    with tenant_context(s["t"].id):
        assert OnlinePayment.objects.get().status == "review" and not Payment.objects.filter(method="online").exists()
    r = m.post(f"/api/v1/pos/invoices/{inv['id']}/payments", {"payments": [{"method": "online", "amount": "15.000", "reference": "x"}]},
               format="json", HTTP_IDEMPOTENCY_KEY="p1")
    assert r.status_code in (400, 422) and r.json()["error"]["code"] in ("invalid", "payment_method_unknown")


def test_declined_payment_counts_as_failed(salon, kp):
    s = salon
    p, _, _ = _activate(s)
    inv = _credit_invoice(s)
    ref = client_for(s["manager"], s["t"]).post(f"/api/v1/pos/invoices/{inv['id']}/pay-link", {}, format="json").json()["reference"]
    kp.status = {"status": "declined", "result": "NOT CAPTURED"}
    APIClient().get(f"/api/v1/public/pay/{ref}")
    process_outbox()
    row = next(x for x in p.get("/api/v1/platform/payments/report").json()["rows"] if x["tenant_id"] == s["t"].id)
    assert row["failed_count"] == 1 and row["paid_count"] == 0 and row["commission"] == "0.000"


def test_link_needs_an_active_account(salon, kp):
    s = salon
    inv = _credit_invoice(s)
    r = client_for(s["manager"], s["t"]).post(f"/api/v1/pos/invoices/{inv['id']}/pay-link", {}, format="json")
    assert r.json()["error"]["code"] == "gateway_not_active"
