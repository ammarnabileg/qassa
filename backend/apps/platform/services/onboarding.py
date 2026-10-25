"""Create a tenant with its first legal entity, branches, default roles, owner, chart of accounts and fiscal year."""
from dataclasses import dataclass, field

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.accounting.services.ledger import create_fiscal_year, install_chart
from apps.audit.services.log import record as audit
from apps.identity.models import User
from apps.tenancy.context import tenant_context
from apps.tenancy.models import Branch, LegalEntity, Membership, Role, Tenant
from apps.tenancy.permissions_catalog import ROLE_TEMPLATES


@dataclass
class BranchSpec:
    name_ar: str
    code: str
    business_type: str
    name_en: str = ""


@dataclass
class OnboardingSpec:
    tenant_name: str
    owner_email: str
    owner_name: str
    legal_name_ar: str
    business_type: str
    branches: list[BranchSpec] = field(default_factory=list)
    legal_name_en: str = ""
    commercial_registration: str = ""
    owner_password: str | None = None  # None → unusable password + invitation (email delivery is phase 2)


def onboard_tenant(spec: OnboardingSpec, actor=None) -> Tenant:
    with transaction.atomic():
        base = slugify(spec.legal_name_en or spec.tenant_name, allow_unicode=False) or "tenant"
        slug, n = base, 1
        while Tenant.objects.filter(slug=slug).exists():
            n += 1
            slug = f"{base}-{n}"
        tenant = Tenant.objects.create(name=spec.tenant_name, slug=slug, default_business_type=spec.business_type)
        with tenant_context(tenant.id):
            entity = LegalEntity.objects.create(name_ar=spec.legal_name_ar, name_en=spec.legal_name_en,
                                                commercial_registration=spec.commercial_registration)
            for b in spec.branches or [BranchSpec(name_ar="الفرع الرئيسي", name_en="Main branch", code="MAIN",
                                                  business_type=spec.business_type)]:
                Branch.objects.create(legal_entity=entity, name_ar=b.name_ar, name_en=b.name_en, code=b.code,
                                      business_type=b.business_type)
            roles = {key: Role.objects.create(key=key, name_ar=t["name_ar"], name_en=t["name_en"],
                                              permissions=sorted(t["permissions"]), is_system=True)
                     for key, t in ROLE_TEMPLATES.items()}
            owner = User.objects.filter(email=spec.owner_email.lower()).first()
            if owner is None:
                owner = User.objects.create_user(spec.owner_email, spec.owner_password, full_name=spec.owner_name,
                                                 mfa_required=True)
            Membership.objects.create(user=owner, tenant=tenant, role=roles["owner"], all_branches=True)
            install_chart(entity)
            create_fiscal_year(entity, timezone.localdate().year)
            audit("tenant.onboarded", tenant_id=tenant.id, actor=actor, obj=tenant,
                  data={"entity": entity.id, "branches": [b.code for b in spec.branches]})
        return tenant
