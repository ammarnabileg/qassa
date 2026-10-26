"""Phase 2 acceptance: company with three branches of three business types; a guardian with two children;
a price change never alters what applied in the past; plan limits; permissions; isolation."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.catalog.models import Service, ServiceCategory, ServicePrice
from apps.catalog.services.pricing import price_on, set_price
from apps.core.errors import DomainError
from apps.identity.models import User
from apps.platform.models import Plan, Subscription
from apps.tenancy.context import tenant_context
from tests.conftest import add_member, client_for, ensure_plans

pytestmark = pytest.mark.django_db
TODAY = timezone.localdate()


def owner(t):
    return User.objects.get(memberships__tenant=t, memberships__role__key="owner")


def make_service(t, name="قص شعر", btype="kids", price="5.000"):
    c = client_for(owner(t), t)
    cat = c.post("/api/v1/catalog/categories", {"name_ar": "شعر", "business_type": btype}, format="json").json()
    r = c.post("/api/v1/catalog/services", {"category": cat["id"], "name_ar": name, "duration_minutes": 30,
                                            "price": price}, format="json")
    assert r.status_code == 201, r.content
    return r.json()


def test_platform_onboards_company_with_three_branches_of_three_types(db):
    ensure_plans()
    staff = User.objects.create_user("ops@qassa.test", "Ops-Pass-2026!!", is_platform_staff=True)
    body = {"tenant_name": "Mix", "owner_email": "o@mix.test", "owner_name": "O", "legal_name_ar": "ميكس",
            "business_type": "kids", "plan_code": "pro",
            "branches": [{"name_ar": "أ", "code": "A", "business_type": "kids"},
                         {"name_ar": "ب", "code": "B", "business_type": "men"},
                         {"name_ar": "ج", "code": "C", "business_type": "women"}]}
    r = client_for(staff).post("/api/v1/platform/tenants", body, format="json", HTTP_IDEMPOTENCY_KEY="mix-1")
    assert r.status_code == 201, r.content
    o = User.objects.get(email="o@mix.test")
    from apps.tenancy.models import Tenant
    t = Tenant.objects.get(id=r.json()["id"])
    org = client_for(o, t).get("/api/v1/org").json()
    assert sorted(b["business_type"] for b in org["branches"]) == ["kids", "men", "women"]
    assert client_for(o, t).get("/api/v1/subscription").json()["plan"]["code"] == "pro"
    listed = client_for(staff).get("/api/v1/platform/tenants").json()
    assert listed[0]["plan"] == "pro" and listed[0]["branches"] == 3


def test_onboarding_rejects_more_branches_than_plan(db):
    ensure_plans()
    staff = User.objects.create_user("ops@qassa.test", "Ops-Pass-2026!!", is_platform_staff=True)
    body = {"tenant_name": "Small", "owner_email": "o@s.test", "owner_name": "O", "legal_name_ar": "س",
            "business_type": "men", "plan_code": "basic",
            "branches": [{"name_ar": "أ", "code": "A", "business_type": "men"}, {"name_ar": "ب", "code": "B", "business_type": "men"}]}
    r = client_for(staff).post("/api/v1/platform/tenants", body, format="json", HTTP_IDEMPOTENCY_KEY="s-1")
    assert r.status_code == 422 and r.json()["error"]["code"] == "plan_limit_branches"


def test_guardian_with_two_children(company_a):
    t, _, b = company_a
    cashier = add_member(t, "c@k.test", "cashier", branch=b["HAW"])
    c = client_for(cashier, t)
    r = c.post("/api/v1/customers", {"full_name": "أم سارة", "phone": "5555 1234", "add_self": False}, format="json")
    assert r.status_code == 201, r.content
    cid = r.json()["id"]
    assert r.json()["phone"] == "96555551234"
    for name in ["سارة", "يوسف"]:
        assert c.post(f"/api/v1/customers/{cid}/beneficiaries",
                      {"full_name": name, "relation": "child", "birth_date": "2020-03-01"}, format="json").status_code == 201
    got = c.get(f"/api/v1/customers/{cid}").json()
    assert sorted(x["full_name"] for x in got["beneficiaries"]) == ["سارة", "يوسف"]
    # search finds the guardian by a child's name and by phone digits
    assert [x["id"] for x in c.get("/api/v1/customers", {"q": "يوسف"}).json()] == [cid]
    assert [x["id"] for x in c.get("/api/v1/customers", {"q": "5123"}).json()] == [cid]
    # same phone twice → clear error, not a 500
    dup = c.post("/api/v1/customers", {"full_name": "x", "phone": "+965 5555-1234"}, format="json")
    assert dup.status_code == 422 and dup.json()["error"]["code"] == "customer_phone_exists"


def test_customer_self_beneficiary_is_unique(company_a):
    t, _, _ = company_a
    c = client_for(owner(t), t)
    cid = c.post("/api/v1/customers", {"full_name": "خالد", "phone": "99887766"}, format="json").json()["id"]
    r = c.post(f"/api/v1/customers/{cid}/beneficiaries", {"full_name": "خالد", "relation": "self"}, format="json")
    assert r.status_code == 422 and r.json()["error"]["code"] == "beneficiary_self_exists"


def test_invalid_phone_rejected(company_a):
    t, _, _ = company_a
    r = client_for(owner(t), t).post("/api/v1/customers", {"full_name": "x", "phone": "123"}, format="json")
    assert r.status_code == 400


def test_price_change_never_alters_the_past(company_a):
    t, _, b = company_a
    svc = make_service(t)
    assert svc["current_price"] == "5.000"
    with tenant_context(t.id):
        service = Service.objects.get(id=svc["id"])
        # simulate that the 5.000 price has been in force since last month (as if created back then)
        ServicePrice.objects.filter(service=service).update(valid_from=TODAY - timedelta(days=30))
        set_price(service, price="6.500", valid_from=TODAY + timedelta(days=1))
        assert price_on(service, None, TODAY - timedelta(days=10)) == Decimal("5.000")
        assert price_on(service, None, TODAY) == Decimal("5.000")
        assert price_on(service, None, TODAY + timedelta(days=1)) == Decimal("6.500")
        # branch override applies only to that branch
        set_price(service, price="7.000", branch_id=b["SAL"].id)
        assert price_on(service, b["SAL"].id, TODAY) == Decimal("7.000")
        assert price_on(service, b["HAW"].id, TODAY) == Decimal("5.000")
        with pytest.raises(DomainError) as e:
            set_price(service, price="1.000", valid_from=TODAY - timedelta(days=1))
        assert e.value.code == "price_backdated"


def test_database_rejects_overlapping_prices(company_a):
    t, _, _ = company_a
    svc = make_service(t)
    with tenant_context(t.id), pytest.raises(IntegrityError), transaction.atomic():
        ServicePrice.objects.create(service_id=svc["id"], price="9.000", valid_from=TODAY)


def test_price_endpoint_requires_price_permission_and_cashier_cannot_create_services(company_a):
    t, _, b = company_a
    svc = make_service(t)
    cashier = add_member(t, "c@k.test", "cashier", branch=b["HAW"])
    c = client_for(cashier, t)
    assert c.get("/api/v1/catalog/services").status_code == 200
    assert c.post(f"/api/v1/catalog/services/{svc['id']}/prices", {"price": "1.000"}, format="json",
                  HTTP_IDEMPOTENCY_KEY="p1").status_code == 403
    assert c.post("/api/v1/catalog/categories", {"name_ar": "x", "business_type": "kids"}, format="json").status_code == 403


def test_staff_with_branches_and_skills_and_plan_limit(company_a):
    t, _, b = company_a
    svc = make_service(t)
    c = client_for(owner(t), t)
    r = c.post("/api/v1/staff", {"full_name_ar": "منى", "branch_ids": [b["HAW"].id], "service_ids": [svc["id"]]}, format="json")
    assert r.status_code == 201 and r.json()["service_ids"] == [svc["id"]]
    sid = r.json()["id"]
    r = c.patch(f"/api/v1/staff/{sid}", {"branch_ids": [b["HAW"].id, b["SAL"].id]}, format="json")
    assert r.json()["branch_ids"] == sorted([b["HAW"].id, b["SAL"].id])
    # pro plan allows 10 active staff
    for i in range(9):
        assert c.post("/api/v1/staff", {"full_name_ar": f"s{i}"}, format="json").status_code == 201
    r = c.post("/api/v1/staff", {"full_name_ar": "11th"}, format="json")
    assert r.status_code == 422 and r.json()["error"]["code"] == "plan_limit_staff"
    # a branch-scoped manager sees only staff linked to their branch
    bm = add_member(t, "bm@k.test", "branch_manager", branch=b["SAL"])
    assert [s["id"] for s in client_for(bm, t).get("/api/v1/staff").json()] == [sid]


def test_branch_create_respects_plan(company_a):
    t, entity, _ = company_a
    c = client_for(owner(t), t)
    r = c.post("/api/v1/org/branches", {"legal_entity": entity.id, "name_ar": "الفحيحيل", "code": "FAH",
                                        "business_type": "women"}, format="json")
    assert r.status_code == 422 and r.json()["error"]["code"] == "plan_limit_branches"  # pro = 3, already 3
    Subscription.objects.filter(tenant=t).update(plan=Plan.objects.get(code="chains"))
    r = c.post("/api/v1/org/branches", {"legal_entity": entity.id, "name_ar": "الفحيحيل", "code": "FAH",
                                        "business_type": "women"}, format="json")
    assert r.status_code == 201
    dup = c.post("/api/v1/org/branches", {"legal_entity": entity.id, "name_ar": "x", "code": "FAH",
                                          "business_type": "women"}, format="json")
    assert dup.status_code == 422 and dup.json()["error"]["code"] == "branch_code_exists"


def test_isolation_for_phase2_data(company_a, company_b):
    ta, _, ba = company_a
    tb, _, bb = company_b
    svc_a = make_service(ta)
    ca = client_for(owner(ta), ta)
    cust = ca.post("/api/v1/customers", {"full_name": "A", "phone": "55550000"}, format="json").json()
    cb = client_for(owner(tb), tb)
    assert cb.get(f"/api/v1/customers/{cust['id']}").status_code == 404
    assert cb.get("/api/v1/catalog/services").json() == []
    # cannot attach another tenant's branch or service to own staff
    r = cb.post("/api/v1/staff", {"full_name_ar": "x", "branch_ids": [ba["HAW"].id]}, format="json")
    assert r.status_code == 422 and r.json()["error"]["code"] == "branch_unknown"
    r = cb.post("/api/v1/staff", {"full_name_ar": "x", "service_ids": [svc_a["id"]]}, format="json")
    assert r.status_code == 422 and r.json()["error"]["code"] == "service_unknown"
    # same phone may exist in two different companies
    assert cb.post("/api/v1/customers", {"full_name": "B", "phone": "55550000"}, format="json").status_code == 201
    # category of another tenant is invisible
    with tenant_context(ta.id):
        cat_a = ServiceCategory.objects.first().id
    r = cb.post("/api/v1/catalog/services", {"category": cat_a, "name_ar": "x", "duration_minutes": 30}, format="json")
    assert r.status_code == 400


def test_platform_changes_plan_with_reason_and_blocks_downgrade_below_usage(company_a):
    t, _, _ = company_a
    staff = User.objects.create_user("ops@qassa.test", "Ops-Pass-2026!!", is_platform_staff=True)
    c = client_for(staff)
    assert c.patch(f"/api/v1/platform/tenants/{t.id}", {"plan_code": "chains"}, format="json").status_code == 400  # reason required
    r = c.patch(f"/api/v1/platform/tenants/{t.id}", {"plan_code": "basic", "reason": "downgrade"}, format="json")
    assert r.status_code == 422 and r.json()["error"]["code"] == "plan_limit_branches"
    r = c.patch(f"/api/v1/platform/tenants/{t.id}", {"plan_code": "chains", "status": "active", "reason": "paid"}, format="json")
    assert r.status_code == 200 and r.json()["plan"] == "chains" and r.json()["status"] == "active"
    from apps.audit.models import AuditLog
    assert AuditLog.objects.filter(tenant_id=t.id, action="platform.tenant.changed", reason="paid").exists()
    # non-staff cannot
    assert client_for(owner(t)).patch(f"/api/v1/platform/tenants/{t.id}", {"status": "active", "reason": "x"},
                                      format="json").status_code == 403


def test_public_plans_list(db):
    ensure_plans()
    from rest_framework.test import APIClient
    plans = APIClient().get("/api/v1/platform/plans").json()
    assert [p["code"] for p in plans] == ["basic", "pro", "chains"] and plans[0]["monthly_price"] == "15.000"


def test_duplicate_service_name_in_category_is_a_clear_error(company_a):
    t, _, _ = company_a
    svc = make_service(t)
    r = client_for(owner(t), t).post("/api/v1/catalog/services", {"category": svc["category"], "name_ar": "قص شعر",
                                                                  "duration_minutes": 30}, format="json")
    assert r.status_code == 422 and r.json()["error"]["code"] == "service_name_exists"


def test_duplicate_category_name_is_a_clear_error(company_a):
    t, _, _ = company_a
    c = client_for(owner(t), t)
    assert c.post("/api/v1/catalog/categories", {"name_ar": "قصات", "business_type": "kids"}, format="json").status_code == 201
    r = c.post("/api/v1/catalog/categories", {"name_ar": "قصات", "business_type": "kids"}, format="json")
    assert r.status_code == 422 and r.json()["error"]["code"] == "category_name_exists"
    assert c.post("/api/v1/catalog/categories", {"name_ar": "قصات", "business_type": "men"}, format="json").status_code == 201
