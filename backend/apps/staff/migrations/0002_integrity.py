from django.db import migrations

from apps.core.db import composite_tenant_fk


class Migration(migrations.Migration):
    dependencies = [("staff", "0001_initial"), ("catalog", "0002_integrity")]
    operations = [
        composite_tenant_fk("staff_staffbranch", "staff_id", "staff_staffmember"),
        composite_tenant_fk("staff_staffbranch", "branch_id", "tenancy_branch"),
        composite_tenant_fk("staff_staffskill", "staff_id", "staff_staffmember"),
        composite_tenant_fk("staff_staffskill", "service_id", "catalog_service"),
    ]
