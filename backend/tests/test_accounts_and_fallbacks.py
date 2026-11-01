"""Invitations, password set/reset, and the front-desk customer login link (D-003 fallback)."""
from urllib.parse import parse_qs, urlparse

import pytest
from django.core import mail
from rest_framework.test import APIClient

from apps.identity.models import User
from apps.platform.models import TenantDomain
from tests.conftest import add_member, client_for
from tests.test_whatsapp import FakeEvolution, gw  # noqa: F401

pytestmark = pytest.mark.django_db


def owner(t):
    return User.objects.get(memberships__tenant=t, memberships__role__key="owner")


def params(link):
    q = parse_qs(urlparse(link).query)
    return q["uid"][0], q["token"][0]


def test_invite_without_email_gives_link_to_admin_then_link_works_once(company_a, settings):
    settings.QASSA = {**settings.QASSA, "EMAIL_CONFIGURED": False, "WHATSAPP_ADAPTER": "disabled"}
    t, _, b = company_a
    c = client_for(owner(t), t)
    r = c.post("/api/v1/users", {"email": "Sara@Kids.test", "full_name": "سارة", "role": "cashier", "branch_ids": [b["HAW"].id]},
               format="json")
    assert r.status_code == 201, r.content
    out = r.json()
    assert out["delivery"]["channel"] == "manual" and out["has_password"] is False and out["branch_ids"] == [b["HAW"].id]
    uid, token = params(out["delivery"]["link"])
    anon = APIClient()
    assert anon.post("/api/v1/auth/password/set", {"uid": uid, "token": token, "password": "short"}, format="json").status_code == 400
    weak = anon.post("/api/v1/auth/password/set", {"uid": uid, "token": token, "password": "1234567890"}, format="json")
    assert weak.status_code == 422 and weak.json()["error"]["code"] == "password_weak"
    assert anon.post("/api/v1/auth/password/set", {"uid": uid, "token": token, "password": "Sara-Kids-2026!"}, format="json").status_code == 204
    again = anon.post("/api/v1/auth/password/set", {"uid": uid, "token": token, "password": "Other-Pass-2026!"}, format="json")
    assert again.status_code == 422 and again.json()["error"]["code"] == "link_invalid"   # single use
    login = anon.post("/api/v1/auth/login", {"email": "sara@kids.test", "password": "Sara-Kids-2026!"}, format="json")
    assert login.status_code == 200 and login.json()["memberships"][0]["role"] == "cashier"


def test_invite_by_email_when_configured(company_a, settings):
    settings.QASSA = {**settings.QASSA, "EMAIL_CONFIGURED": True}
    t, _, _ = company_a
    r = client_for(owner(t), t).post("/api/v1/users", {"email": "acc@kids.test", "full_name": "محاسب", "role": "accountant",
                                                       "all_branches": True}, format="json")
    assert r.json()["delivery"] == {"channel": "email"} and "link" not in r.json()["delivery"]
    assert mail.outbox[-1].to == ["acc@kids.test"] and "set-password" in mail.outbox[-1].body


def test_forgot_password_never_reveals_accounts(company_a, settings):
    settings.QASSA = {**settings.QASSA, "EMAIL_CONFIGURED": True}
    t, _, _ = company_a
    anon = APIClient()
    a = anon.post("/api/v1/auth/password/forgot", {"email": owner(t).email}, format="json")
    b = anon.post("/api/v1/auth/password/forgot", {"email": "nobody@x.test"}, format="json")
    assert a.json() == b.json() == {"ok": True} and "link" not in str(a.json())
    assert len(mail.outbox) == 1


def test_only_owner_adds_owner_and_cashier_cannot_manage_users(company_a):
    t, _, b = company_a
    bm = add_member(t, "bm@k.test", "operations_manager")
    r = client_for(bm, t).post("/api/v1/users", {"email": "o2@k.test", "full_name": "x", "role": "owner", "all_branches": True}, format="json")
    assert r.status_code == 422 and r.json()["error"]["code"] == "owner_only"
    cashier = add_member(t, "c@k.test", "cashier", branch=b["HAW"])
    assert client_for(cashier, t).get("/api/v1/users").status_code == 403


def test_invite_with_a_password_set_now_or_a_ready_whatsapp_text(company_a):
    t, _, b = company_a
    owner = User.objects.get(memberships__tenant=t, memberships__role__key="owner")
    c = client_for(owner, t)
    r = c.post("/api/v1/users", {"email": "cash1@k.test", "full_name": "كاشير", "role": "cashier", "all_branches": True,
                                 "password": "Cashier-Pass-2026!"}, format="json")
    assert r.status_code == 201 and r.json()["delivery"] == {"channel": "password_set"} and "password" not in r.json()
    assert APIClient().post("/api/v1/auth/login", {"email": "cash1@k.test", "password": "Cashier-Pass-2026!"}, format="json").status_code == 200
    weak = c.post("/api/v1/users", {"email": "cash2@k.test", "full_name": "x", "role": "cashier", "all_branches": True, "password": "123"}, format="json")
    assert weak.json()["error"]["code"] == "password_weak"
    # nothing could send it (no email, no phone to message): the link and a ready-to-share text come back
    r = c.post("/api/v1/users", {"email": "cash3@k.test", "full_name": "كاشير ٣", "role": "cashier", "all_branches": True},
               format="json").json()["delivery"]
    assert r["channel"] == "manual" and r["link"] in r["text"]


def test_invite_link_goes_out_on_the_salons_connected_number(company_a, gw):  # noqa: F811
    from apps.notifications.models import WhatsAppChannel, WhatsAppMessage
    from apps.tenancy.context import tenant_context
    t, _, _ = company_a
    with tenant_context(t.id):
        WhatsAppChannel.objects.create(instance_name="qassa-inv", state="open")
    gw.instances["qassa-inv"] = "open"
    owner = User.objects.get(memberships__tenant=t, memberships__role__key="owner")
    r = client_for(owner, t).post("/api/v1/users", {"email": "cash4@k.test", "full_name": "ك", "phone": "55511133", "role": "cashier",
                                                    "all_branches": True}, format="json").json()["delivery"]
    assert r["channel"] == "whatsapp" and "link" not in r
    assert gw.sent[-1][1] == "96555511133" and "/set-password?" in gw.sent[-1][2]
    with tenant_context(t.id):
        assert "set-password" not in WhatsAppMessage.objects.get(kind="staff_invite").preview      # the link isn't kept in the log


def test_two_step_is_the_users_choice_but_not_for_platform_staff(company_a):
    t, _, _ = company_a
    owner = User.objects.get(memberships__tenant=t, memberships__role__key="owner")
    owner.set_password("Owner-Pass-2026!!"); owner.mfa_required = False; owner.save()
    c = client_for(owner, t)
    assert c.post("/api/v1/auth/mfa/preference", {"enabled": True, "password": "wrong"}, format="json").json()["error"]["code"] == "invalid_credentials"
    assert c.post("/api/v1/auth/mfa/preference", {"enabled": True, "password": "Owner-Pass-2026!!"}, format="json").json()["mfa_required"] is True
    r = APIClient().post("/api/v1/auth/login", {"email": owner.email, "password": "Owner-Pass-2026!!"}, format="json").json()
    assert r["mfa"] == "setup"                                                # next sign-in asks to set it up
    assert c.post("/api/v1/auth/mfa/preference", {"enabled": False, "password": "Owner-Pass-2026!!"}, format="json").json()["mfa_required"] is False
    assert "id" in APIClient().post("/api/v1/auth/login", {"email": owner.email, "password": "Owner-Pass-2026!!"}, format="json").json()
    staff = User.objects.create_user("ops9@q.test", "Ops-Pass-2026!!", is_platform_staff=True, mfa_required=True)
    assert client_for(staff).post("/api/v1/auth/mfa/preference", {"enabled": False, "password": "Ops-Pass-2026!!"},
                                  format="json").json()["error"]["code"] == "mfa_mandatory"
