from django.db import migrations

from apps.core.db import composite_tenant_fk


class Migration(migrations.Migration):
    """Database-level guarantee that org rows only reference rows of the same tenant."""
    dependencies = [("tenancy", "0001_initial")]
    operations = [
        composite_tenant_fk("tenancy_branch", "legal_entity_id", "tenancy_legalentity"),
        composite_tenant_fk("tenancy_membership", "role_id", "tenancy_role"),
        composite_tenant_fk("tenancy_membershipbranch", "branch_id", "tenancy_branch"),
        composite_tenant_fk("tenancy_membershipbranch", "membership_id", "tenancy_membership"),
    ]
