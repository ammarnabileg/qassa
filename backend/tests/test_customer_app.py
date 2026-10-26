"""Customer app: phone + code login, registration with children, nearest branch, free slots, booking, cancel."""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.booking.models import Appointment
from apps.catalog.models import Service, ServiceCategory
from apps.catalog.services.pricing import set_price
from apps.customers.models import OtpChallenge
from apps.platform.models import TenantDomain
from apps.staff.models import StaffBranch, StaffMember, StaffSkill
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Branch

pytestmark = pytest.mark.django_db


@pytest.fixture
def app(company_a, settings):
    t, _, b = company_a
    settings.PLATFORM_HOSTS = ["qassa.test", "testserver"]
    TenantDomain.objects.filter(tenant=t).update(host="kids.qassa.test", is_active=True)
    with tenant_context(t.id):
        # Hawally and Jahra coordinates
        Branch.objects.filter(id=b["HAW"].id).update(latitude="29.3375", longitude="48.0281", opens_at="00:00", closes_at="23:59")
        Branch.objects.filter(id=b["JAH"].id).update(latitude="29.3375", longitude="47.6581", business_type="kids")
        cat = ServiceCategory.objects.create(name_ar="قصات", business_type="kids")
        cut = Service.objects.create(category=cat, name_ar="قص", duration_minutes=30)
        set_price(cut, price="4.500")
        mona = StaffMember.objects.create(full_name_ar="منى")
        StaffBranch.objects.create(staff=mona, branch=b["HAW"])
        StaffSkill.objects.create(staff=mona, service=cut)
    c = APIClient(HTTP_HOST="kids.qassa.test")
    return dict(t=t, b=b, cut=cut, mona=mona, c=c)


def login(app, phone="55550001", name="أم سارة"):
    c = app["c"]
    r = c.post("/api/v1/app/otp/request", {"phone": phone}, format="json")
    assert r.status_code == 200, r.content
    code = r.json()["debug_code"]  # test environment only
    r = c.post("/api/v1/app/otp/verify", {"phone": phone, "code": code}, format="json")
    if r.json().get("new"):
        r = c.post("/api/v1/app/register", {"registration_token": r.json()["registration_token"], "full_name": name,
                                            "self_service": False, "children": [{"full_name": "سارة"}, {"full_name": "يوسف"}]},
                   format="json")
        assert r.status_code == 201, r.content
    return r.json()["token"]


def authed(app, token):
    return APIClient(HTTP_HOST="kids.qassa.test", HTTP_AUTHORIZATION=f"Customer {token}")


def test_register_with_two_children_then_login_again(app):
    token = login(app)
    me = authed(app, token).get("/api/v1/app/me").json()
    assert me["phone"] == "96555550001" and sorted(b["full_name"] for b in me["beneficiaries"]) == ["سارة", "يوسف"]
    # second login: existing customer gets a token straight away
    OtpChallenge.unscoped.all().update(created_at=timezone.now() - timedelta(minutes=11))
    r = app["c"].post("/api/v1/app/otp/request", {"phone": "55550001"}, format="json")
    r = app["c"].post("/api/v1/app/otp/verify", {"phone": "55550001", "code": r.json()["debug_code"]}, format="json")
    assert r.json()["new"] is False and r.json()["token"]


def test_code_is_hashed_single_use_limited_and_throttled(app):
    c = app["c"]
    code = c.post("/api/v1/app/otp/request", {"phone": "55550002"}, format="json").json()["debug_code"]
    with tenant_context(app["t"].id):
        assert OtpChallenge.objects.get().code_hash != code
    for _ in range(5):
        r = c.post("/api/v1/app/otp/verify", {"phone": "55550002", "code": "000000" if code != "000000" else "111111"}, format="json")
    assert r.json()["error"]["code"] == "otp_invalid"
    r = c.post("/api/v1/app/otp/verify", {"phone": "55550002", "code": code}, format="json")
    assert r.status_code == 429  # attempts used up, even with the right code
    r = c.post("/api/v1/app/otp/request", {"phone": "55550002"}, format="json")
    assert r.status_code == 429 and r.json()["error"]["code"] == "otp_throttled"  # 60 s cooldown


def test_no_whatsapp_channel_is_a_clear_error_not_a_fake_success(app, settings):
    settings.QASSA = {**settings.QASSA, "WHATSAPP_ADAPTER": "disabled"}
    r = app["c"].post("/api/v1/app/otp/request", {"phone": "55550003"}, format="json")
    assert r.status_code == 503 and r.json()["error"]["code"] == "whatsapp_unavailable"


def test_nearest_branch_is_recommended(app):
    near_jahra = app["c"].get("/api/v1/app/catalog", {"lat": "29.34", "lng": "47.67"}).json()
    assert near_jahra["branches"][0]["id"] == app["b"]["JAH"].id and near_jahra["branches"][0]["recommended"]
    near_hawally = app["c"].get("/api/v1/app/catalog", {"lat": "29.33", "lng": "48.03"}).json()
    assert near_hawally["branches"][0]["id"] == app["b"]["HAW"].id
    assert near_hawally["services"][0]["price"] == "4.500"


def test_book_a_free_slot_then_it_disappears_and_cancel(app):
    token = login(app)
    c = authed(app, token)
    me = c.get("/api/v1/app/me").json()
    day = (timezone.localtime() + timedelta(days=1)).date().isoformat()
    q = {"branch_id": app["b"]["HAW"].id, "service_id": app["cut"].id, "date": day}
    slots = c.get("/api/v1/app/slots", q).json()["slots"]
    first = slots[0]
    r = c.post("/api/v1/app/bookings", {"branch_id": q["branch_id"], "service_id": q["service_id"], "starts_at": first["starts_at"],
                                        "beneficiary_id": me["beneficiaries"][0]["id"]}, format="json", HTTP_IDEMPOTENCY_KEY="b1")
    assert r.status_code == 201, r.content
    bk = r.json()
    assert bk["status"] == "booked" and bk["can_cancel"] and bk["services"][0]["staff_ar"] == "منى"
    assert bk["starts_at"] == first["starts_at"] and bk["starts_at"].endswith("+03:00")  # salon time, not UTC
    with tenant_context(app["t"].id):
        assert Appointment.objects.get(id=bk["id"]).source == "online"
    assert first["starts_at"] not in [s["starts_at"] for s in c.get("/api/v1/app/slots", q).json()["slots"]]
    again = c.post("/api/v1/app/bookings", {"branch_id": q["branch_id"], "service_id": q["service_id"], "starts_at": first["starts_at"],
                                            "beneficiary_id": me["beneficiaries"][0]["id"]}, format="json", HTTP_IDEMPOTENCY_KEY="b2")
    assert again.status_code == 422 and again.json()["error"]["code"] == "slot_unavailable"
    assert c.post(f"/api/v1/app/bookings/{bk['id']}/cancel").json()["status"] == "cancelled"
    assert first["starts_at"] in [s["starts_at"] for s in c.get("/api/v1/app/slots", q).json()["slots"]]


def test_customer_cannot_book_for_someone_else_or_without_login(app):
    token = login(app)
    other = login(app, phone="55550009", name="خالد")
    other_child = authed(app, other).get("/api/v1/app/me").json()["beneficiaries"][0]["id"]
    c = authed(app, token)
    day = (timezone.localtime() + timedelta(days=1)).date().isoformat()
    slot = c.get("/api/v1/app/slots", {"branch_id": app["b"]["HAW"].id, "service_id": app["cut"].id, "date": day}).json()["slots"][0]
    r = c.post("/api/v1/app/bookings", {"branch_id": app["b"]["HAW"].id, "service_id": app["cut"].id, "starts_at": slot["starts_at"],
                                        "beneficiary_id": other_child}, format="json", HTTP_IDEMPOTENCY_KEY="x")
    assert r.json()["error"]["code"] == "beneficiary_unknown"
    assert app["c"].get("/api/v1/app/me").status_code in (401, 403)


def test_token_from_one_salon_is_useless_on_another(app, company_b):
    tb, _, _ = company_b
    TenantDomain.objects.filter(tenant=tb).update(host="men.qassa.test", is_active=True)
    token = login(app)
    r = APIClient(HTTP_HOST="men.qassa.test", HTTP_AUTHORIZATION=f"Customer {token}").get("/api/v1/app/me")
    assert r.status_code in (401, 403)
