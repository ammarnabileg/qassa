"""Staging-only accounts without MFA: refused in production, closed when the password is removed."""
import pytest
from django.core.management import CommandError, call_command

from apps.identity.models import User


def test_refused_in_production(db, settings):
    settings.ENVIRONMENT = "production"
    with pytest.raises(CommandError):
        call_command("e2e_users")


def test_created_without_mfa_then_closed(company_a, settings, monkeypatch):
    from apps.tenancy.models import Tenant
    Tenant.objects.filter(id=company_a[0].id).update(slug="my-kids")
    monkeypatch.setenv("E2E_PASSWORD", "a-long-staging-password")
    call_command("e2e_users")
    u = User.objects.get(email="e2e-owner@qassa.test")
    assert u.is_active and not u.mfa_required and u.memberships.get().role.key == "owner"
    monkeypatch.delenv("E2E_PASSWORD")
    call_command("e2e_users")
    assert not User.objects.filter(email__startswith="e2e-", is_active=True).exists()
