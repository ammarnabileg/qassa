"""Invitations, password set/reset, and the front-desk customer login link (D-003 fallback)."""
from urllib.parse import parse_qs, urlparse

import pytest
from django.core import mail
from rest_framework.test import APIClient

from apps.identity.models import User
from apps.platform.models import TenantDomain
from tests.conftest import add_member, client_for

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
