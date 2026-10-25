"""Shared fixtures: two independent salon companies with three branches each, and staff in different roles."""
from datetime import date

import pytest
from rest_framework.test import APIClient

from apps.identity.models import User
from apps.platform.services.onboarding import BranchSpec, OnboardingSpec, onboard_tenant
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Branch, LegalEntity, Membership, MembershipBranch, Role

TODAY = date.today()


def make_company(name, email, btype="kids"):
    t = onboard_tenant(OnboardingSpec(
        tenant_name=name, owner_email=email, owner_name="Owner", legal_name_ar=name, legal_name_en=name,
        business_type=btype, owner_password="Owner-Pass-2026!",
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
