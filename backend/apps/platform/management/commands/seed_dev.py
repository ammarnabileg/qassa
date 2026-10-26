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
            self.stdout.write("Companies already seeded.")
            self.seed_catalog()
            return
        specs = [("My Kids", "My Kids", "ماي كيدز", "kids", "mykids"), ("Gentleman Cut", "Gentleman Cut", "جنتلمان كت", "men", "gentle"),
                 ("Lamsa", "Lamsa Salon", "صالون لمسة", "women", "lamsa")]
        for name, en, ar, btype, dom in specs:
            t = onboard_tenant(OnboardingSpec(tenant_name=name, owner_email=f"owner@{dom}.dev", owner_name="Owner",
                                              legal_name_ar=ar, legal_name_en=en, business_type=btype, owner_password=password, plan_code="pro",
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
        self.seed_catalog()

    def seed_catalog(self):
        """Synthetic services, prices and staff per company (only where a company has no services yet)."""
        from apps.catalog.models import Service, ServiceCategory
        from apps.catalog.services.pricing import set_price
        from apps.staff.models import StaffBranch, StaffMember, StaffSkill
        menus = {
            "kids": [("قصات", "Cuts", [("قص شعر أطفال", "Kids haircut", 30, "4.500"), ("أول قصة للطفل", "First haircut", 30, "6.000"),
                                        ("قصة + غسيل", "Cut + wash", 45, "6.000")]),
                     ("تسريحات", "Styling", [("ضفائر", "Braids", 40, "5.000"), ("تسريحة مناسبة", "Party style", 45, "7.500")])],
            "men": [("حلاقة", "Barber", [("قص شعر", "Haircut", 30, "5.000"), ("تحديد لحية", "Beard trim", 20, "3.000"),
                                          ("حلاقة كاملة + لحية", "Cut + beard", 45, "7.000")]),
                    ("عناية", "Care", [("ماسك وجه", "Face mask", 20, "4.000"), ("صبغة", "Colour", 60, "12.000")])],
            "women": [("شعر", "Hair", [("قص وتسريح", "Cut & style", 60, "12.000"), ("صبغة", "Colour", 120, "25.000"),
                                        ("سشوار", "Blow-dry", 40, "8.000")]),
                      ("سبا", "Spa", [("مساج استرخاء", "Relaxing massage", 60, "20.000"), ("مانيكير", "Manicure", 45, "7.000")])],
        }
        names = {"kids": ["منى", "سارة", "هدى"], "men": ["أحمد", "خالد", "يوسف"], "women": ["نورة", "ريم", "دانة"]}
        for t in Tenant.objects.all():
            with tenant_context(t.id):
                if Service.objects.exists():
                    continue
                btype = t.default_business_type
                services = []
                for i, (cat_ar, cat_en, items) in enumerate(menus[btype]):
                    cat = ServiceCategory.objects.create(name_ar=cat_ar, name_en=cat_en, business_type=btype, sort=i)
                    for ar, en, minutes, price in items:
                        svc = Service.objects.create(category=cat, name_ar=ar, name_en=en, duration_minutes=minutes)
                        set_price(svc, price=price)
                        services.append(svc)
                branches = list(Branch.objects.filter(business_type=btype))
                for j, name in enumerate(names[btype]):
                    person = StaffMember.objects.create(full_name_ar=name)
                    for br in branches[: 1 + j % len(branches)] if branches else []:
                        StaffBranch.objects.create(staff=person, branch=br)
                    for svc in services:
                        StaffSkill.objects.create(staff=person, service=svc)
                Membership.objects.filter(tenant=t, role__key="cashier").update(discount_limit_percent=10)
                self.stdout.write(f"Catalog seeded for {t.slug}")
