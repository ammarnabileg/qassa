"""Staff second factor by WhatsApp (platform number) and 'remember this device'."""
import pytest
from rest_framework.test import APIClient

from apps.identity.models import TrustedDevice, User
from apps.notifications import whatsapp
from tests.conftest import client_for

pytestmark = pytest.mark.django_db
PW = "Owner-Pass-2026!"


@pytest.fixture
def platform_wa(monkeypatch, settings):
    sent = []
    settings.QASSA = {**settings.QASSA, "WHATSAPP_ADAPTER": "evolution", "PLATFORM_WA_INSTANCE": "Testapp", "OTP_ECHO": False}
    monkeypatch.setattr(whatsapp, "_call", lambda m, p, b=None: sent.append((p, b)) or {"key": {"id": "1"}})
    return sent


def owner_with_phone(t):
    u = User.objects.get(memberships__tenant=t, memberships__role__key="owner")
    u.phone = "96550001111"
    u.save()
    return u


def login(c, email):
    return c.post("/api/v1/auth/login", {"email": email, "password": PW}, format="json").json()


def code_from(sent):
    path, body = sent[-1]
    assert path == "/message/sendText/Testapp" and body["number"] == "96550001111"
    return "".join(ch for ch in body["text"].split(":")[1][:8] if ch.isdigit())


def test_whatsapp_code_instead_of_authenticator_app(platform_wa, company_a):
    t, _, _ = company_a
    u = owner_with_phone(t)
    c = APIClient()
    step = login(c, u.email)
    assert step["mfa"] == "setup" and step["methods"] == ["totp", "whatsapp"] and step["phone"].endswith("111")
    r = c.post("/api/v1/auth/mfa/whatsapp")
    assert r.status_code == 200 and "debug_code" not in r.json()
    code = code_from(platform_wa)
    bad = c.post("/api/v1/auth/mfa/verify", {"token": "000000" if code != "000000" else "111111", "method": "whatsapp"}, format="json")
    assert bad.status_code == 401
    r = c.post("/api/v1/auth/mfa/verify", {"token": code, "method": "whatsapp"}, format="json")
    assert r.status_code == 200 and r.json()["email"] == u.email
    assert c.get("/api/v1/auth/me").status_code == 200
    # single use
    c2 = APIClient()
    login(c2, u.email)
    assert c2.post("/api/v1/auth/mfa/verify", {"token": code, "method": "whatsapp"}, format="json").status_code == 401


def test_no_phone_means_no_whatsapp_option(platform_wa, company_a):
    t, _, _ = company_a
    u = User.objects.get(memberships__tenant=t, memberships__role__key="owner")
    c = APIClient()
    assert login(c, u.email)["methods"] == ["totp"]
    r = c.post("/api/v1/auth/mfa/whatsapp")
    assert r.status_code == 422 and r.json()["error"]["code"] == "mfa_no_phone"


def test_remember_this_device_skips_the_second_factor_until_revoked(platform_wa, company_a):
    t, _, _ = company_a
    u = owner_with_phone(t)
    c = APIClient()
    login(c, u.email)
    c.post("/api/v1/auth/mfa/whatsapp")
    r = c.post("/api/v1/auth/mfa/verify", {"token": code_from(platform_wa), "method": "whatsapp", "remember": True}, format="json")
    cookie = r.cookies["qassa_td"]
    assert cookie["httponly"] and int(cookie["max-age"]) == 60 * 86400
    assert TrustedDevice.objects.get(user=u).token_hash not in cookie.value  # only a hash is stored
    c.post("/api/v1/auth/logout")
    again = login(c, u.email)  # same browser
    assert again.get("email") == u.email  # signed in directly, no second factor
    # a different browser still needs the second factor
    assert login(APIClient(), u.email)["mfa"] == "setup"
    # forget all devices
    assert c.delete("/api/v1/auth/devices").status_code == 204
    c.post("/api/v1/auth/logout")
    c.cookies["qassa_td"] = cookie.value
    assert login(c, u.email)["mfa"] == "setup"


def test_cookie_for_another_user_is_ignored(platform_wa, company_a, company_b):
    ta, _, _ = company_a
    tb, _, _ = company_b
    ua = owner_with_phone(ta)
    c = APIClient()
    login(c, ua.email)
    c.post("/api/v1/auth/mfa/whatsapp")
    c.post("/api/v1/auth/mfa/verify", {"token": code_from(platform_wa), "method": "whatsapp", "remember": True}, format="json")
    c.post("/api/v1/auth/logout")
    ub = User.objects.get(memberships__tenant=tb, memberships__role__key="owner")
    assert login(c, ub.email)["mfa"] == "setup"


def test_platform_sets_owner_phone(company_a):
    t, _, _ = company_a
    staff = User.objects.create_user("ops@qassa.test", "Ops-Pass-2026!!", is_platform_staff=True)
    r = client_for(staff).patch(f"/api/v1/platform/tenants/{t.id}", {"owner_phone": "5000 1111", "reason": "MFA by WhatsApp"}, format="json")
    assert r.status_code == 200 and r.json()["owner_phone"] == "96550001111"
