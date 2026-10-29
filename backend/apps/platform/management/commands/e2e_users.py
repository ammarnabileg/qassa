"""Accounts without MFA for automated browser checks on STAGING only (owner's request, 2026-10-30).

With E2E_PASSWORD set (16+ chars): creates/refreshes
  e2e-owner@qassa.test — owner of the demo company "My Kids" (no MFA)
  e2e-ops@qassa.test   — platform staff (no MFA)
Without E2E_PASSWORD: both accounts are deactivated (removing the variable in Coolify closes them on the next deploy).
Refuses to run outside development/test/staging."""
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.identity.models import User
from apps.tenancy.models import Membership, Role, Tenant

OWNER, OPS = "e2e-owner@qassa.test", "e2e-ops@qassa.test"


class Command(BaseCommand):
    help = "Create or deactivate the staging-only test accounts (no MFA)."

    def handle(self, *args, **opts):
        if settings.ENVIRONMENT not in {"development", "test", "staging"}:
            raise CommandError("e2e_users never runs in production")
        password = os.environ.get("E2E_PASSWORD", "")
        if not password:
            n = User.objects.filter(email__in=[OWNER, OPS]).update(is_active=False)
            self.stdout.write(f"E2E_PASSWORD not set: {n} test account(s) deactivated")
            return
        if len(password) < 16:
            raise CommandError("E2E_PASSWORD must be 16+ characters")
        tenant = Tenant.objects.filter(slug="my-kids").first()
        if tenant is None:
            raise CommandError("demo company my-kids not found (run seed_dev first)")
        for email, staff in ((OWNER, False), (OPS, True)):
            u = User.objects.filter(email=email).first() or User.objects.create_user(email, password, full_name="E2E")
            u.set_password(password)
            u.is_active, u.mfa_required, u.is_platform_staff = True, False, staff
            u.save()
        u = User.objects.get(email=OWNER)
        role = Role.unscoped.get(tenant=tenant, key="owner")
        Membership.objects.update_or_create(user=u, tenant=tenant, defaults={"role": role, "all_branches": True, "is_active": True})
        self.stdout.write(self.style.SUCCESS("E2E accounts ready (staging only, no MFA)"))
