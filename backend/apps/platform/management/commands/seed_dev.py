"""Synthetic development data. Never runs in production. On staging (public URL) it requires SEED_PASSWORD: no well-known password on the internet."""
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.identity.models import User
from apps.platform.services.onboarding import BranchSpec, OnboardingSpec, onboard_tenant
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Branch, Membership, MembershipBranch, Role, Tenant


class Command(BaseCommand):
    help = "Create synthetic companies and staff for local development."

    def handle(self, *args, **opts):
        if settings.ENVIRONMENT not in {"development", "test", "staging"}:
            raise CommandError("seed_dev is disabled outside development/test/staging")
        password = os.environ.get("SEED_PASSWORD") or ("Dev-Only-Pass-2026" if settings.ENVIRONMENT != "staging" else "")
        if len(password) < 12:
            raise CommandError("staging requires SEED_PASSWORD (12+ characters)")
        if Tenant.objects.filter(slug="my-kids").exists():
            self.stdout.write("Already seeded.")
            return
        specs = [("My Kids", "My Kids", "ماي كيدز", "kids", "mykids"), ("Gentleman Cut", "Gentleman Cut", "جنتلمان كت", "men", "gentle"),
                 ("Lamsa", "Lamsa Salon", "صالون لمسة", "women", "lamsa")]
        for name, en, ar, btype, dom in specs:
            t = onboard_tenant(OnboardingSpec(tenant_name=name, owner_email=f"owner@{dom}.dev", owner_name="Owner",
                                              legal_name_ar=ar, legal_name_en=en, business_type=btype, owner_password=password,
                                              branches=[BranchSpec("حولي", "HAW", btype, "Hawally"), BranchSpec("السالمية", "SAL", btype, "Salmiya"),
                                                        BranchSpec("الجهراء", "JAH", btype, "Jahra")]))
            with tenant_context(t.id):
                for key, branch in [("accountant", None), ("finance_manager", None), ("cashier", "HAW"), ("branch_manager", "HAW")]:
                    u = User.objects.create_user(f"{key.replace('_', '')}@{dom}.dev", password, full_name=key)
                    m = Membership.objects.create(user=u, tenant=t, role=Role.objects.get(key=key), all_branches=branch is None)
                    if branch:
                        MembershipBranch.objects.create(tenant=t, membership=m, branch=Branch.objects.get(code=branch))
        User.objects.create_user("support@qassa.dev", password, is_platform_staff=True, mfa_required=True)
        self.stdout.write(self.style.SUCCESS(f"Seeded 3 companies. Password for all dev users: {password if settings.ENVIRONMENT != 'staging' else '(SEED_PASSWORD)'}"))
