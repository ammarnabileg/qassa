"""Give every company its <slug>.<QASSA_TENANT_BASE_DOMAIN> address after the base domain changes.
Old addresses stay active (links already shared keep working); prints the hosts to add in Coolify."""
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.platform.middleware import forget_host
from apps.platform.models import TenantDomain
from apps.tenancy.models import Tenant


class Command(BaseCommand):
    help = "Create the subdomain on the current base domain for each company (idempotent)"

    def handle(self, *args, **opts):
        base = settings.TENANT_BASE_DOMAIN
        for t in Tenant.objects.order_by("id"):
            host = f"{t.slug}.{base}"
            if t.slug in settings.RESERVED_SUBDOMAINS:
                self.stdout.write(self.style.WARNING(f"skip {t.slug}: reserved name — give this company another slug first"))
                continue
            d, made = TenantDomain.objects.get_or_create(host=host, defaults=dict(
                tenant=t, kind=TenantDomain.Kind.SUBDOMAIN, is_active=True, activated_at=timezone.now()))
            if d.tenant_id != t.id:
                self.stdout.write(self.style.ERROR(f"{host} already belongs to company {d.tenant_id}"))
                continue
            forget_host(host)
            self.stdout.write(f"{'added' if made else 'exists'} {host}")
