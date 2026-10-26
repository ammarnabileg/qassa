"""Shared fixtures: two independent salon companies with three branches each, and staff in different roles."""
from datetime import date

import pytest
from rest_framework.test import APIClient

from apps.identity.models import User
from apps.platform.services.onboarding import BranchSpec, OnboardingSpec, onboard_tenant
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Branch, LegalEntity, Membership, MembershipBranch, Role

TODAY = date.today()


@pytest.fixture(autouse=True)
def _clear_cache():
    """Host→tenant lookups are cached; tests recreate tenants with new ids, so start each test clean."""
    from django.core.cache import cache
    cache.clear()
    yield
    cache.clear()


def ensure_plans():
    """Plans come from a data migration; transactional tests flush tables, so recreate them when needed."""
    from apps.platform.models import Plan
    for code, ar, en, price, br, st, sort in [("basic", "أساسي", "Basic", "15.000", 1, 3, 1),
                                               ("pro", "احترافي", "Pro", "29.000", 3, 10, 2),
                                               ("chains", "سلاسل", "Chains", "69.000", 99, 99, 3)]:
        Plan.objects.get_or_create(code=code, defaults=dict(name_ar=ar, name_en=en, monthly_price=price,
                                                            max_branches=br, max_staff=st, sort=sort))


def make_company(name, email, btype="kids"):
    ensure_plans()
    t = onboard_tenant(OnboardingSpec(
        tenant_name=name, owner_email=email, owner_name="Owner", legal_name_ar=name, legal_name_en=name,
        business_type=btype, owner_password="Owner-Pass-2026!", plan_code="pro",
        branches=[BranchSpec("حولي", "HAW", btype), BranchSpec("السالمية", "SAL", "women"),
                  BranchSpec("الجهراء", "JAH", "men")]))
    with tenant_context(t.id):
        entity = LegalEntity.objects.get()
        branches = {b.code: b for b in Branch.objects.all()}
    return t, entity, branches


def add_member(tenant, email, role_key, branch=None, mfa=False):
    with tenant_context(tenant.id):
        role = Role.objects.get(key=role_key)
        user = User.objects.filter(email=email).first() or User.objects.create_user(email, "Staff-Pass-2026!", mfa_required=mfa)
        m = Membership.objects.create(user=user, tenant=tenant, role=role, all_branches=branch is None)
        if branch is not None:
            MembershipBranch.objects.create(tenant=tenant, membership=m, branch=branch)
    return user


@pytest.fixture
def company_a(db):
    return make_company("My Kids", "owner@mykids.test")


@pytest.fixture
def company_b(db):
    return make_company("Gentleman Cut", "owner@gentle.test", "men")


def client_for(user, tenant=None):
    c = APIClient()
    c.force_login(user)
    if tenant is not None:
        c.credentials(HTTP_X_TENANT=str(tenant.id))
    return c
