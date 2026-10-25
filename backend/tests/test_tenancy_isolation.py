"""Two companies must never see or link each other's data — in the ORM, the API and the database."""
import pytest
from django.db import IntegrityError, transaction

from apps.accounting.models import Account, JournalEntry, JournalLine
from apps.core.errors import TenantContextMissing
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Branch, LegalEntity

from .conftest import add_member, client_for


def test_scoped_manager_refuses_without_context(company_a):
    with pytest.raises(TenantContextMissing):
        list(Branch.objects.all())


def test_scoped_manager_filters_by_tenant(company_a, company_b):
    ta, _, _ = company_a
    tb, _, _ = company_b
    with tenant_context(ta.id):
        assert {b.tenant_id for b in Branch.objects.all()} == {ta.id}
        assert Branch.objects.count() == 3
    with tenant_context(tb.id):
        assert {b.tenant_id for b in Branch.objects.all()} == {tb.id}


def test_cannot_save_row_into_another_tenant(company_a, company_b):
    ta, ea, _ = company_a
    tb, _, _ = company_b
    with tenant_context(tb.id):
        with pytest.raises(TenantContextMissing):
            ea.name_ar = "hijack"
            ea.save()


def test_database_blocks_cross_tenant_reference(company_a, company_b):
    """Even bypassing the ORM guards, PostgreSQL rejects a line of tenant A pointing to an account of tenant B."""
    ta, ea, _ = company_a
    tb, eb, _ = company_b
    foreign_account = Account.unscoped.filter(legal_entity=eb, is_postable=True).first()
    with tenant_context(ta.id):
        from apps.accounting.models import FiscalPeriod
        period = FiscalPeriod.objects.filter(legal_entity=ea).first()
        je = JournalEntry.objects.create(legal_entity=ea, period=period, entry_date=period.start_date)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            JournalLine.unscoped.create(tenant_id=ta.id, entry=je, line_no=1, account=foreign_account, debit=1)


def test_branch_cannot_point_to_other_tenants_entity(company_a, company_b):
    ta, _, _ = company_a
    _, eb, _ = company_b
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Branch.unscoped.create(tenant_id=ta.id, legal_entity=eb, name_ar="x", code="X", business_type="kids")


def test_api_rejects_tenant_without_membership(company_a, company_b):
    ta, _, _ = company_a
    tb, _, _ = company_b
    user = add_member(ta, "acc@mykids.test", "accountant")
    r = client_for(user, tb).get("/api/v1/org")
    assert r.status_code == 403


def test_api_returns_404_for_other_tenants_objects(company_a, company_b):
    ta, ea, _ = company_a
    tb, eb, _ = company_b
    user = add_member(ta, "acc2@mykids.test", "accountant")
    c = client_for(user, ta)
    assert c.get(f"/api/v1/accounting/accounts?legal_entity_id={ea.id}").status_code == 200
    assert c.get(f"/api/v1/accounting/accounts?legal_entity_id={eb.id}").status_code == 404


def test_tenant_header_required(company_a):
    ta, _, _ = company_a
    user = add_member(ta, "acc3@mykids.test", "accountant")
    assert client_for(user).get("/api/v1/org").status_code == 403


def test_branch_scoped_member_sees_only_own_branch(company_a):
    ta, _, branches = company_a
    user = add_member(ta, "cashier@mykids.test", "cashier", branch=branches["HAW"])
    data = client_for(user, ta).get("/api/v1/org").json()
    assert [b["code"] for b in data["branches"]] == ["HAW"]


def test_suspended_tenant_blocked_and_read_only_blocks_writes(company_a):
    ta, ea, _ = company_a
    user = add_member(ta, "acc4@mykids.test", "accountant")
    c = client_for(user, ta)
    ta.status = ta.Status.READ_ONLY
    ta.save()
    assert c.get("/api/v1/org").status_code == 200
    r = c.post("/api/v1/accounting/journal-entries", {}, format="json", HTTP_IDEMPOTENCY_KEY="k1")
    assert r.status_code == 403
    ta.status = ta.Status.SUSPENDED
    ta.save()
    assert c.get("/api/v1/org").status_code == 403
