"""Fine-grained control: editable roles, custom roles, and per-person extra / removed permissions — never beyond the editor's own."""
import pytest

from apps.identity.models import User
from apps.tenancy.models import Membership
from tests.conftest import add_member, client_for

pytestmark = pytest.mark.django_db


def _m(email):
    return Membership.objects.get(user__email=email)


def test_per_person_extra_and_removed_permissions(company_a):
    t, _, b = company_a
    owner = User.objects.get(memberships__tenant=t, memberships__role__key="owner")
    cashier = add_member(t, "c1@k.test", "cashier", branch=b["HAW"])
    c = client_for(owner, t)
    mid = _m("c1@k.test").id
    assert client_for(cashier, t).post("/api/v1/pos/sessions", {}, format="json").status_code != 403   # has cash.session.open
    r = c.patch(f"/api/v1/users/{mid}", {"permissions": sorted((set(_m("c1@k.test").permissions()) - {"cash.session.open"}) | {"pos.return"})},
                format="json")
    assert r.status_code == 200 and r.json()["extra_permissions"] == ["pos.return"] and r.json()["denied_permissions"] == ["cash.session.open"]
    assert client_for(cashier, t).post("/api/v1/pos/sessions", {}, format="json").status_code == 403
    me = client_for(cashier, t).get("/api/v1/auth/me").json()["memberships"][0]["permissions"]
    assert "pos.return" in me and "cash.session.open" not in me
    # changing the role starts clean
    r = c.patch(f"/api/v1/users/{mid}", {"role": "branch_manager"}, format="json").json()
    assert r["extra_permissions"] == [] and r["denied_permissions"] == []
    assert c.patch(f"/api/v1/users/{mid}", {"permissions": ["nope.code"]}, format="json").json()["error"]["code"] == "permission_unknown"


def test_no_one_hands_out_what_they_do_not_have(company_a):
    t, _, b = company_a
    ops = add_member(t, "ops@k.test", "operations_manager")           # users.manage, but no accounting.setup
    add_member(t, "c2@k.test", "cashier", branch=b["HAW"])
    c = client_for(ops, t)
    mid = _m("c2@k.test").id
    r = c.patch(f"/api/v1/users/{mid}", {"permissions": sorted(_m("c2@k.test").permissions() | {"accounting.setup"})}, format="json")
    assert r.json()["error"]["code"] == "permission_not_yours"
    assert c.patch(f"/api/v1/users/{mid}", {"permissions": sorted(_m("c2@k.test").permissions() | {"pos.return"})}, format="json").status_code == 200
    roles = c.get("/api/v1/roles").json()
    owner_role = next(r for r in roles["roles"] if r["key"] == "owner")
    assert owner_role["editable"] is False and "pos.sell" in roles["catalog"]
    assert c.patch(f"/api/v1/roles/{owner_role['id']}", {"permissions": []}, format="json").json()["error"]["code"] == "owner_has_all"
    mine = next(r for r in roles["roles"] if r["key"] == "operations_manager")
    assert c.patch(f"/api/v1/roles/{mine['id']}", {"permissions": []}, format="json").json()["error"]["code"] == "cannot_edit_self"
    cash_role = next(r for r in roles["roles"] if r["key"] == "cashier")
    assert c.patch(f"/api/v1/roles/{cash_role['id']}", {"permissions": cash_role["permissions"] + ["accounting.setup"]},
                   format="json").json()["error"]["code"] == "permission_not_yours"
    assert client_for(User.objects.get(email="c2@k.test"), t).get("/api/v1/roles").status_code == 403


def test_custom_role_created_edited_and_deleted(company_a):
    t, _, b = company_a
    owner = User.objects.get(memberships__tenant=t, memberships__role__key="owner")
    c = client_for(owner, t)
    r = c.post("/api/v1/roles", {"name_ar": "استقبال فقط", "permissions": ["booking.view", "booking.manage", "customers.view"]}, format="json")
    assert r.status_code == 201 and r.json()["key"].startswith("custom-")
    rid, key = r.json()["id"], r.json()["key"]
    assert c.patch(f"/api/v1/roles/{rid}", {"permissions": ["booking.view"]}, format="json").json()["permissions"] == ["booking.view"]
    u = c.post("/api/v1/users", {"email": "rec@k.test", "full_name": "ر", "role": key, "all_branches": True, "password": "Reception-2026!!"},
               format="json")
    assert u.status_code == 201
    assert c.delete(f"/api/v1/roles/{rid}").json()["error"]["code"] == "role_in_use"
    c.patch(f"/api/v1/users/{u.json()['id']}", {"role": "cashier"}, format="json")
    assert c.delete(f"/api/v1/roles/{rid}").status_code == 204
    sys_role = next(x for x in c.get("/api/v1/roles").json()["roles"] if x["key"] == "cashier")
    assert c.delete(f"/api/v1/roles/{sys_role['id']}").json()["error"]["code"] == "role_is_system"
