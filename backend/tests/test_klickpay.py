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
    assert a["status"] == "not_started" and len(a["checklist"]) == KycDocumentType.objects.filter(stage="kyc").count() >= 4
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


# ---------- refunds ----------
class RefundingKlickPay(FakeKlickPay):
    def __init__(self):
        super().__init__()
        self.refund_code = "REFUND_SUCCESS"

    def __call__(self, method, url, headers, body=None):
        if "/refunds/" in url:
            self.calls.append((url.rsplit("/v3", 1)[-1], headers, body))
            if self.refund_code == "REFUND_SUCCESS":
                return 200, {"success": True, "code": "REFUND_SUCCESS", "data": {"refund_reference": "RF1", "refund_status": "success"}}
            if self.refund_code == "INSUFFICIENT_BALANCE":
                return 422, {"success": False, "code": "INSUFFICIENT_BALANCE", "details": {"refund_reference": "RF2", "shortfall_amount": "3.153"}}
            return 422, {"success": False, "code": "REFUND_FAILED", "details": {"refund_reference": "RF3", "gateway": {"message": "Gateway error"}}}
        return super().__call__(method, url, headers, body)


@pytest.fixture
def kpr(monkeypatch):
    fake = RefundingKlickPay()
    monkeypatch.setattr(klickpay, "_http", fake)
    return fake


def _paid_online_invoice(s, kp):
    p, token, secret = _activate(s)
    inv = _credit_invoice(s)
    m = client_for(s["manager"], s["t"])
    ref = m.post(f"/api/v1/pos/invoices/{inv['id']}/pay-link", {}, format="json").json()["reference"]
    kp.status = {"status": "paid", "result": "CAPTURED", "amount": "15.000", "payment_method": "KNET"}
    APIClient().get(f"/api/v1/public/pay/{ref}")
    process_outbox()
    return p, token, secret, inv, m


def test_online_refund_after_a_return(salon, kpr):
    s = salon
    p, token, secret, inv, m = _paid_online_invoice(s, kpr)
    # nothing owed yet: no refund without a return first
    assert m.post(f"/api/v1/pos/invoices/{inv['id']}/online-refund", {"amount": "5.000", "reason": "x"}, format="json").json()["error"]["code"] == "refund_more_than_owed"
    m.post(f"/api/v1/pos/invoices/{inv['id']}/credit-notes", {"lines": [{"invoice_line_id": inv["lines"][0]["id"], "amount": "5.000"}],
                                                               "reason": "خدمة ناقصة"}, format="json", HTTP_IDEMPOTENCY_KEY="cn1")
    r = m.post(f"/api/v1/pos/invoices/{inv['id']}/online-refund", {"amount": "5.000", "reason": "خدمة ناقصة"}, format="json").json()
    assert r["refunds"][0]["status"] == "success" and kpr.calls[-1][0] == "/refunds/partial" and kpr.calls[-1][2]["refund_amount"] == "5.000"
    assert balance(s, "GATEWAY_CLEARING") == D("10.000")
    assert m.get(f"/api/v1/pos/invoices/{inv['id']}").json()["state"]["balance"] == "0.000"
    assert client_for(s["cashier"], s["t"]).post(f"/api/v1/pos/invoices/{inv['id']}/online-refund", {"amount": "1", "reason": "x"},
                                                 format="json").status_code == 403
    row = next(x for x in p.get("/api/v1/platform/payments/report").json()["rows"] if x["tenant_id"] == s["t"].id)
    assert row["refunded_amount"] == "5.000"


def test_refund_waits_for_wallet_then_webhook_completes_it(salon, kpr):
    s = salon
    p, token, secret, inv, m = _paid_online_invoice(s, kpr)
    m.post(f"/api/v1/pos/invoices/{inv['id']}/credit-notes", {"lines": [{"invoice_line_id": inv["lines"][0]["id"], "amount": "15.000"}],
                                                               "reason": "إلغاء"}, format="json", HTTP_IDEMPOTENCY_KEY="cn2")
    kpr.refund_code = "INSUFFICIENT_BALANCE"
    r = m.post(f"/api/v1/pos/invoices/{inv['id']}/online-refund", {"amount": "15.000", "reason": "إلغاء"}, format="json").json()
    assert r["refunds"][0]["status"] == "pending" and kpr.calls[-1][0] == "/refunds/full"
    assert balance(s, "GATEWAY_CLEARING") == D("15.000")                      # nothing posted while it waits
    assert m.post(f"/api/v1/pos/invoices/{inv['id']}/online-refund", {"amount": "1.000", "reason": "x"},
                  format="json").json()["error"]["code"] == "refund_more_than_owed"   # no double refund while pending
    body = {"invoice_id": "QI123ABC", "payment_id": "QI123ABC", "refund_reference": "RF2", "event_type": "refund.success", "refund_status": "success"}
    raw, h = _signed(secret, body)
    APIClient().post(f"/api/v1/payments/klickpay/webhook/{token}", raw, content_type="application/json", **h)
    assert balance(s, "GATEWAY_CLEARING") == 0
    assert m.get(f"/api/v1/pos/invoices/{inv['id']}").json()["state"]["balance"] == "0.000"


# ---------- booking deposits ----------
def _app_booking(s, kp, hours=48, set_policy=True):
    from datetime import timedelta
    from django.utils import timezone
    from apps.catalog.services.pricing import set_price
    from apps.customers.models import Beneficiary, Customer
    from apps.customers.services import otp
    from apps.platform.models import TenantDomain
    from apps.staff.models import StaffBranch, StaffSkill, WorkingHours
    p, token, secret = _activate(s)
    owner = client_for(s["owner"], s["t"])
    if set_policy:
        assert owner.patch("/api/v1/payments/account", {"deposit_mode": "percent", "deposit_value": "50", "deposit_refund_hours": 24},
                           format="json").json()["deposit"]["mode"] == "percent"
    host = TenantDomain.objects.filter(tenant=s["t"]).first().host
    with tenant_context(s["t"].id):
        c = Customer.objects.create(full_name="سارة", phone="96555552222")
        kid = Beneficiary.objects.create(customer=c, full_name="ليلى", relation="child")
        tok = otp.issue_token(s["t"], c)
        from apps.tenancy.models import Branch
        Branch.objects.filter(id=s["b"]["HAW"].id).update(opens_at="00:00", closes_at="23:59")
        for st in s["staff"]:
            for d in range(7):
                WorkingHours.objects.get_or_create(staff=st, branch=s["b"]["HAW"], weekday=d, defaults={"starts_at": "00:00", "ends_at": "23:59"})
    app = APIClient(HTTP_HOST=host, HTTP_AUTHORIZATION=f"Customer {tok}")
    day = (timezone.localtime() + timedelta(hours=hours)).date()
    slots = app.get("/api/v1/app/slots", {"branch_id": s["b"]["HAW"].id, "service_id": s["wash"].id, "date": str(day)}).json()["slots"]
    assert slots, "no free slots"
    r = app.post("/api/v1/app/bookings", {"branch_id": s["b"]["HAW"].id, "service_id": s["wash"].id, "beneficiary_id": kid.id,
                                          "starts_at": slots[-1]["starts_at"]}, format="json", HTTP_IDEMPOTENCY_KEY=f"b{hours}")
    assert r.status_code == 201, r.content
    return p, app, r.json(), c


def test_deposit_paid_then_applied_at_checkout(salon, kpr):
    s = salon
    p, app, b, c = _app_booking(s, kpr)
    assert b["deposit"]["amount"] == "7.500" and b["deposit"]["status"] == "pending" and b["pay_url"].startswith("https://")
    with tenant_context(s["t"].id):
        op = OnlinePayment.objects.get(purpose="deposit")
    kpr.status = {"status": "paid", "result": "CAPTURED", "amount": "7.500", "payment_method": "KNET"}
    APIClient().get(f"/api/v1/public/pay/{op.reference}")
    process_outbox()
    assert app.get("/api/v1/app/bookings").json()[0]["deposit"]["status"] == "paid"
    assert balance(s, "CUSTOMER_DEPOSITS") == D("-7.500") and balance(s, "GATEWAY_CLEARING") == D("7.500")
    from apps.booking.models import Appointment
    with tenant_context(s["t"].id):
        Appointment.objects.filter(id=b["id"]).update(status="completed")
    from tests.test_phase3_operations import open_drawer
    open_drawer(s)
    r = checkout(s, s["cashier"], [{"service_id": s["wash"].id}], [{"method": "cash", "amount": "7.500"}], customer_id=c.id,
                 appointment_id=b["id"], key="dep1")
    assert r.status_code == 201, r.content
    assert r.json()["state"]["balance"] == "0.000" and {x["method"] for x in r.json()["payments"]} == {"cash", "deposit"}
    assert balance(s, "CUSTOMER_DEPOSITS") == 0


def test_deposit_cancel_in_time_refunds_late_keeps(salon, kpr):
    s = salon
    p, app, b, c = _app_booking(s, kpr, hours=48)
    with tenant_context(s["t"].id):
        op = OnlinePayment.objects.get(purpose="deposit")
    kpr.status = {"status": "paid", "result": "CAPTURED", "amount": "7.500"}
    APIClient().get(f"/api/v1/public/pay/{op.reference}")
    process_outbox()
    assert app.post(f"/api/v1/app/bookings/{b['id']}/cancel").status_code == 200
    process_outbox()
    assert app.get("/api/v1/app/bookings").json()[0]["deposit"]["status"] == "refunded"
    assert balance(s, "CUSTOMER_DEPOSITS") == 0 and balance(s, "GATEWAY_CLEARING") == 0
    # a later booking, then a no-show: the salon keeps the deposit
    from apps.booking.models import Appointment
    from apps.booking.services.appointments import set_status
    with tenant_context(s["t"].id):
        a = Appointment.objects.get(id=b["id"])
        a2 = Appointment.objects.create(branch=a.branch, customer=a.customer, beneficiary=a.beneficiary, starts_at=a.starts_at,
                                        ends_at=a.ends_at, business_date=a.business_date, source="online", deposit_amount="7.500", deposit_status="paid")
        OnlinePayment.objects.create(reference="DX-1", purpose="deposit", appointment=a2, amount="7.500", status="paid", gateway_id="QIX")
        from apps.accounting.services.posting import Line, post_entry
        post_entry(legal_entity_id=a.branch.legal_entity_id, entry_date=a.starts_at.date(), kind="auto", branch_id=a.branch_id,
                   lines=[Line("GATEWAY_CLEARING", debit=D("7.500")), Line("CUSTOMER_DEPOSITS", credit=D("7.500"))])
        set_status(a2, "no_show", reason="ما جاش")
        assert Appointment.objects.get(id=a2.id).deposit_status == "forfeited"
    assert balance(s, "CUSTOMER_DEPOSITS") == 0 and balance(s, "OTHER_INCOME") == D("-7.500")


def test_unpaid_deposit_releases_the_slot(salon, kpr):
    from apps.booking.models import Appointment
    from apps.core.models import OutboxEvent
    from django.utils import timezone
    s = salon
    p, app, b, c = _app_booking(s, kpr)
    OutboxEvent.objects.filter(topic="deposit.expire").update(available_at=timezone.now())
    process_outbox()
    with tenant_context(s["t"].id):
        a = Appointment.objects.get(id=b["id"])
        assert a.status == "cancelled" and a.deposit_status == "expired"
        assert OnlinePayment.objects.get(purpose="deposit").status == "voided"


def test_no_deposit_when_policy_off(salon, kpr):
    s = salon
    p, app, b, c = _app_booking(s, kpr, set_policy=False)
    assert b["deposit"] is None


def test_contract_cycle_and_officer_links(salon, kp):
    from apps.platform.models import PlatformSettings
    s = salon
    owner = client_for(s["owner"], s["t"])
    a = owner.get("/api/v1/payments/account").json()
    assert all(i["type"]["stage"] == "kyc" for i in a["checklist"]) and a["contract"] is None   # no contract item yet
    for i in a["checklist"]:
        if i["type"]["required"]:
            owner.post("/api/v1/payments/kyc", {"doc_type": i["type"]["id"], "file": pdf()}, format="multipart")
    owner.post("/api/v1/payments/kyc/submit")
    p = ops()
    # the officer's number is set once in platform settings; documents go to them as 7-day links
    assert p.post(f"/api/v1/platform/payments/accounts/{s['t'].id}/send-officer").json()["error"]["code"] == "officer_phone_missing"
    p.patch("/api/v1/platform/settings", {"klickpay_officer_whatsapp": "55500099"}, format="json")
    assert PlatformSettings.get().klickpay_officer_whatsapp == "96555500099"
    r = p.post(f"/api/v1/platform/payments/accounts/{s['t'].id}/send-officer").json()
    assert r["documents"] == 4 and "/api/v1/public/kyc/" in r["text"]
    link = r["text"].split("/api/v1/public/kyc/")[1].split()[0]
    assert APIClient().get(f"/api/v1/public/kyc/{link}").status_code == 200
    assert APIClient().get(f"/api/v1/public/kyc/{link}x").status_code == 404
    # KlickPay's contract: platform uploads it, the salon downloads, signs and uploads it back
    r = p.post(f"/api/v1/platform/payments/accounts/{s['t'].id}/contract", {"file": pdf("contract.pdf")}, format="multipart").json()
    assert r["status"] == "contract"
    a = owner.get("/api/v1/payments/account").json()
    signed = next(i for i in a["checklist"] if i["type"]["code"] == "signed_contract")
    assert a["contract"]["name"] == "contract.pdf" and signed["doc"] is None
    assert owner.get("/api/v1/payments/contract").status_code == 200
    up = owner.post("/api/v1/payments/kyc", {"doc_type": signed["type"]["id"], "file": pdf("signed.pdf")}, format="multipart").json()
    assert owner.get("/api/v1/payments/account").json()["status"] == "under_review"
    # a rejected signature sends the salon back to signing; activation waits for an accepted signed contract
    p.patch(f"/api/v1/platform/payments/accounts/{s['t'].id}", {"client_id": "c", "client_secret": "s", "new_webhook_secret": True}, format="json")
    assert p.patch(f"/api/v1/platform/payments/accounts/{s['t'].id}", {"status": "active"}, format="json").json()["error"]["code"] == "contract_not_signed"
    assert p.post(f"/api/v1/platform/payments/kyc/{up['id']}/review", {"accept": False, "note": "ناقص الختم"}, format="json").json()["account_status"] == "contract"
    up = owner.post("/api/v1/payments/kyc", {"doc_type": signed["type"]["id"], "file": pdf("signed2.pdf")}, format="multipart").json()
    p.post(f"/api/v1/platform/payments/kyc/{up['id']}/review", {"accept": True}, format="json")
    assert p.patch(f"/api/v1/platform/payments/accounts/{s['t'].id}", {"status": "active"}, format="json").json()["status"] == "active"


def test_booking_confirmation_waits_for_the_deposit(salon, kpr, monkeypatch):
    from apps.notifications import auto, whatsapp
    from apps.notifications.models import MessagingSettings
    sent = []
    monkeypatch.setattr(whatsapp, "send_text", lambda phone, text, **k: sent.append((k.get("kind"), text)) or "fake")
    s = salon
    with tenant_context(s["t"].id):
        MessagingSettings.objects.get_or_create(tenant_id=s["t"].id)
    p, app, b, c = _app_booking(s, kpr)
    process_outbox()
    assert not [k for k, _ in sent if k == "booking.confirmed"]                  # nothing while the deposit is unpaid
    with tenant_context(s["t"].id):
        op = OnlinePayment.objects.get(purpose="deposit")
    kpr.status = {"status": "paid", "result": "CAPTURED", "amount": "7.500"}
    APIClient().get(f"/api/v1/public/pay/{op.reference}")
    process_outbox()
    process_outbox()
    assert [k for k, _ in sent].count("booking.confirmed") == 1


def test_no_deposit_booking_is_confirmed_at_once(salon, kpr, monkeypatch):
    from apps.notifications import whatsapp
    sent = []
    monkeypatch.setattr(whatsapp, "send_text", lambda phone, text, **k: sent.append(k.get("kind")) or "fake")
    p, app, b, c = _app_booking(salon, kpr, set_policy=False)
    process_outbox()
    assert sent.count("booking.confirmed") == 1
