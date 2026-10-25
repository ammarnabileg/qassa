import pytest
from rest_framework.test import APIClient

from apps.tenancy.context import tenant_context
from apps.tenancy.models import Branch, Tenant
from tests.conftest import make_company

pytestmark = pytest.mark.django_db


def test_public_salon_profile_shows_only_active_branches_and_no_private_fields():
    t, _, branches = make_company("My Kids", "o@k.dev")
    with tenant_context(t.id):
        Branch.objects.filter(id=branches["JAH"].id).update(is_active=False)
    r = APIClient().get(f"/api/v1/public/salons/{t.slug}")
    assert r.status_code == 200
    assert r.json()["business_type"] == "kids"
    assert [b["name_en"] or b["name_ar"] for b in r.json()["branches"]] == ["حولي", "السالمية"]
    assert set(r.json()["branches"][0]) == {"id", "name_ar", "name_en", "business_type", "address", "phone"}


def test_public_salon_unknown_or_suspended_is_404():
    t, _, _ = make_company("Gone", "o@g.dev")
    Tenant.objects.filter(id=t.id).update(status=Tenant.Status.SUSPENDED)
    c = APIClient()
    assert c.get(f"/api/v1/public/salons/{t.slug}").status_code == 404
    r = c.get("/api/v1/public/salons/nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "salon_not_found"
