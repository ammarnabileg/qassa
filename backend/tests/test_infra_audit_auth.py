"""Outbox, audit chain, authentication and MFA, platform onboarding."""
import pytest
from django.db import transaction
from django_otp.oath import totp
from django_otp.plugins.otp_totp.models import TOTPDevice
from rest_framework.test import APIClient

from apps.audit.models import AuditLog
from apps.audit.services.log import record, verify_chain
from apps.core.models import OutboxEvent
from apps.core.services.infra import enqueue, outbox_handler, process_outbox
from apps.identity.models import User
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Branch

from .conftest import add_member

CALLS = []


@outbox_handler("test.ok")
def _ok(ev):
    CALLS.append(ev.payload["n"])


@outbox_handler("test.fail")
def _fail(ev):
    raise RuntimeError("provider down")


def test_outbox_is_transactional_and_deduplicated(db):
    try:
        with transaction.atomic():
            enqueue("test.ok", {"n": 1})
            raise RuntimeError("business change failed")
    except RuntimeError:
        pass
    assert OutboxEvent.objects.count() == 0
    enqueue("test.ok", {"n": 2}, dedupe_key="sms:42")
    enqueue("test.ok", {"n": 2}, dedupe_key="sms:42")
    assert OutboxEvent.objects.count() == 1
    CALLS.clear()
    assert process_outbox() == 1 and CALLS == [2]
    assert process_outbox() == 0  # already done


def test_outbox_failure_backs_off_then_gives_up(db):
    ev = enqueue("test.fail", {})
    process_outbox()
    ev.refresh_from_db()
    assert ev.status == "pending" and ev.attempts == 1 and "provider down" in ev.last_error
    OutboxEvent.objects.filter(pk=ev.pk).update(attempts=7, available_at=ev.created_at)
    process_outbox()
    ev.refresh_from_db()
    assert ev.status == "failed"


def test_audit_chain_detects_tampering_and_rows_are_append_only(company_a):
    t, _, _ = company_a
    record("test.one", tenant_id=t.id, data={"a": 1})
    record("test.two", tenant_id=t.id, data={"b": 2})
    assert verify_chain(t.id) == (True, None)
    with pytest.raises(Exception):
        with transaction.atomic():
            AuditLog.objects.filter(tenant_id=t.id).update(data={"a": 999})
    with pytest.raises(Exception):
        with transaction.atomic():
            AuditLog.objects.filter(tenant_id=t.id).delete()


def test_onboarding_creates_full_structure(company_a):
    t, e, branches = company_a
    with tenant_context(t.id):
        assert set(branches) == {"HAW", "SAL", "JAH"}
        assert {b.business_type for b in Branch.objects.all()} == {"kids", "women", "men"}
        assert e.accounts.filter(code="4101").exists()
    owner = t.memberships.get().user
    assert owner.mfa_required and t.memberships.get().role.key == "owner"


def test_login_rejects_bad_password_and_requires_mfa_for_owner(company_a):
    c = APIClient()
    assert c.post("/api/v1/auth/login", {"email": "owner@mykids.test", "password": "nope"}, format="json").status_code == 401
    r = c.post("/api/v1/auth/login", {"email": "owner@mykids.test", "password": "Owner-Pass-2026!"}, format="json")
    assert r.status_code == 200 and r.json()["mfa"] == "setup" and r.json()["methods"] == ["totp"]  # no phone on account
    assert c.get("/api/v1/auth/me").status_code == 403  # not logged in until MFA verified
    url = c.post("/api/v1/auth/mfa/setup").json()["otpauth_url"]
    assert url.startswith("otpauth://totp/")
    device = TOTPDevice.objects.get(user__email="owner@mykids.test")
    assert c.post("/api/v1/auth/mfa/verify", {"token": "000000"}, format="json").status_code == 401
    token = f"{totp(device.bin_key, step=device.step, t0=device.t0, digits=device.digits):06d}"
    r = c.post("/api/v1/auth/mfa/verify", {"token": token}, format="json")
    assert r.status_code == 429 and r.json()["error"]["code"] == "mfa_throttled"  # back-off after a wrong code
    device.refresh_from_db()
    device.throttle_reset()  # simulate the back-off window passing
    r = c.post("/api/v1/auth/mfa/verify", {"token": token}, format="json")
    assert r.status_code == 200 and r.json()["memberships"][0]["role"] == "owner"
    assert c.get("/api/v1/auth/me").status_code == 200


def test_login_without_mfa_for_cashier(company_a):
    t, _, b = company_a
    add_member(t, "cashier2@mykids.test", "cashier", branch=b["HAW"])
    r = APIClient().post("/api/v1/auth/login", {"email": "cashier2@mykids.test", "password": "Staff-Pass-2026!"},
                         format="json")
    assert r.status_code == 200 and r.json()["memberships"][0]["permissions"] == ["booking.manage", "booking.view", "cash.session.open", "catalog.view", "customers.manage", "customers.view", "inventory.view", "pos.discount.line", "pos.invoices.view", "pos.sell", "staff.view"]


def test_platform_onboarding_api_requires_platform_staff(db):
    staff = User.objects.create_user("support@qassa.test", "Support-Pass-2026!", is_platform_staff=True)
    normal = User.objects.create_user("x@x.test", "Some-Pass-2026!")
    body = {"tenant_name": "Lamsa", "owner_email": "owner@lamsa.test", "owner_name": "Noura",
            "legal_name_ar": "صالون لمسة", "legal_name_en": "Lamsa Salon", "business_type": "women",
            "branches": [{"name_ar": "حولي", "code": "HAW", "business_type": "women"}]}
    c = APIClient()
    c.force_login(normal)
    assert c.post("/api/v1/platform/tenants", body, format="json", HTTP_IDEMPOTENCY_KEY="t1").status_code == 403
    c.force_login(staff)
    from tests.conftest import ensure_plans; ensure_plans()
    r1 = c.post("/api/v1/platform/tenants", body, format="json", HTTP_IDEMPOTENCY_KEY="t2")
    r2 = c.post("/api/v1/platform/tenants", body, format="json", HTTP_IDEMPOTENCY_KEY="t2")
    assert r1.status_code == 201 and r1.json() == r2.json()
    assert User.objects.filter(email="owner@lamsa.test").count() == 1
