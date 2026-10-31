"""Each company serves its customer PWA on its own host; the platform host serves the back-office."""
import pytest
from rest_framework.test import APIClient

from apps.identity.models import User
from apps.platform.models import Plan, Subscription, TenantDomain
from tests.conftest import client_for

pytestmark = pytest.mark.django_db


@pytest.fixture
def settings_hosts(settings):
    settings.PLATFORM_HOSTS = ["qassa.test", "testserver"]
    settings.TENANT_BASE_DOMAIN = "qassa.test"
    return settings


def test_company_subdomain_resolves_its_salon_and_cannot_switch(settings_hosts, company_a, company_b):
    ta, _, _ = company_a
    tb, _, _ = company_b
    TenantDomain.objects.filter(tenant=ta).update(host=f"{ta.slug}.qassa.test")  # created at onboarding
    c = APIClient(HTTP_HOST=f"{ta.slug}.qassa.test")
    r = c.get("/api/v1/public/salon")
    assert r.status_code == 200 and r.json()["slug"] == ta.slug and r.json()["locked"] is True
    # a slug in the path cannot show another company on this company's domain
    assert c.get(f"/api/v1/public/salons/{tb.slug}").json()["slug"] == ta.slug
    m = c.get("/api/v1/public/manifest").json()
    assert m["name"] == ta.name and m["start_url"] == "/"


def test_unknown_or_inactive_host_is_rejected(settings_hosts, company_a):
    ta, _, _ = company_a
    assert APIClient(HTTP_HOST="evil.example").get("/api/v1/public/salon").status_code == 400
    TenantDomain.objects.filter(tenant=ta).update(host="x.qassa.test", is_active=False)
    assert APIClient(HTTP_HOST="x.qassa.test").get("/api/v1/public/salon").status_code == 400


def test_platform_host_uses_slug_and_is_not_locked(settings_hosts, company_a):
    ta, _, _ = company_a
    c = APIClient(HTTP_HOST="qassa.test")
    assert c.get(f"/api/v1/public/salons/{ta.slug}").json()["locked"] is False
    assert c.get("/api/v1/public/salon").status_code == 404


def test_custom_domain_needs_plan_then_activation(settings_hosts, company_a):
    ta, _, _ = company_a
    staff = User.objects.create_user("ops@qassa.test", "Ops-Pass-2026!!", is_platform_staff=True)
    c = client_for(staff)
    r = c.post(f"/api/v1/platform/tenants/{ta.id}/domains", {"host": "book.mykids.com"}, format="json")
    assert r.status_code == 422 and r.json()["error"]["code"] == "plan_no_custom_domain"  # pro plan
    Subscription.objects.filter(tenant=ta).update(plan=Plan.objects.get(code="chains"))
    Plan.objects.filter(code="chains").update(custom_domain=True)
    r = c.post(f"/api/v1/platform/tenants/{ta.id}/domains", {"host": "Book.MyKids.com."}, format="json")
    assert r.status_code == 201 and r.json()["host"] == "book.mykids.com" and r.json()["is_active"] is False
    did = r.json()["id"]
    assert APIClient(HTTP_HOST="book.mykids.com").get("/api/v1/public/salon").status_code == 400  # not active yet
    assert c.patch(f"/api/v1/platform/domains/{did}", {"is_active": True, "reason": "DNS verified"},
                   format="json").status_code == 200
    assert APIClient(HTTP_HOST="book.mykids.com").get("/api/v1/public/salon").json()["slug"] == ta.slug
    # reserved and duplicate hosts
    assert c.post(f"/api/v1/platform/tenants/{ta.id}/domains", {"host": "other.qassa.test"},
                  format="json").json()["error"]["code"] == "domain_reserved"
    assert c.post(f"/api/v1/platform/tenants/{ta.id}/domains", {"host": "book.mykids.com"},
                  format="json").json()["error"]["code"] == "domain_taken"
    # owners cannot manage domains
    owner = User.objects.get(memberships__tenant=ta, memberships__role__key="owner")
    assert client_for(owner).post(f"/api/v1/platform/tenants/{ta.id}/domains", {"host": "a.mykids.com"},
                                  format="json").status_code == 403


def test_dashboard_on_salon_host_is_locked_to_that_salon(settings_hosts, company_a, company_b):
    from tests.conftest import add_member
    ta, _, _ = company_a
    tb, _, _ = company_b
    TenantDomain.objects.filter(tenant=ta).update(host=f"{ta.slug}.qassa.test")
    u = add_member(ta, "both@x.test", "branch_manager")
    add_member(tb, "both@x.test", "branch_manager")
    c = APIClient(HTTP_HOST=f"{ta.slug}.qassa.test")
    c.force_login(User.objects.get(email="both@x.test"))
    me = c.get("/api/v1/auth/me").json()
    assert me["domain_tenant_id"] == ta.id and [m["tenant_id"] for m in me["memberships"]] == [ta.id]
    assert c.get("/api/v1/customers", HTTP_X_TENANT=str(ta.id)).status_code == 200
    assert c.get("/api/v1/customers", HTTP_X_TENANT=str(tb.id)).status_code == 403    # other salon refused on this address
    p = APIClient(HTTP_HOST="qassa.test")
    p.force_login(u)
    assert len(p.get("/api/v1/auth/me").json()["memberships"]) == 2                    # platform address: all of them


def test_new_base_domain_command_adds_subdomains_and_skips_reserved(settings_hosts, company_a):
    from django.core.management import call_command
    ta, _, _ = company_a
    settings_hosts.TENANT_BASE_DOMAIN = "kuw.test"
    call_command("add_subdomains")
    call_command("add_subdomains")                    # idempotent
    assert TenantDomain.objects.filter(tenant=ta, host=f"{ta.slug}.kuw.test", is_active=True).count() == 1
    assert TenantDomain.objects.filter(tenant=ta).count() == 2                          # the old address keeps working
    settings_hosts.RESERVED_SUBDOMAINS = {ta.slug}
    settings_hosts.TENANT_BASE_DOMAIN = "other.test"
    call_command("add_subdomains")
    assert not TenantDomain.objects.filter(host=f"{ta.slug}.other.test").exists()
