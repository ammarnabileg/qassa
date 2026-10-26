"""Phase 4 permissions for existing system roles."""
from django.db import migrations

from apps.tenancy.permissions_catalog import ROLE_TEMPLATES


def sync(apps, schema_editor):
    Role = apps.get_model("tenancy", "Role")
    for role in Role.objects.filter(is_system=True):
        template = ROLE_TEMPLATES.get(role.key)
        if template:
            role.permissions = sorted(set(role.permissions) | set(template["permissions"]))
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):
    dependencies = [("tenancy", "0005_branch_closes_at_branch_latitude_branch_longitude_and_more")]
    operations = [migrations.RunPython(sync, migrations.RunPython.noop)]
