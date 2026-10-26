from django.contrib.postgres.operations import BtreeGistExtension
from django.db import migrations

from apps.core.db import composite_tenant_fk


class Migration(migrations.Migration):
    dependencies = [("catalog", "0001_initial"), ("tenancy", "0002_same_tenant_fks")]
    operations = [
        BtreeGistExtension(),
        composite_tenant_fk("catalog_service", "category_id", "catalog_servicecategory"),
        composite_tenant_fk("catalog_serviceprice", "service_id", "catalog_service"),
        composite_tenant_fk("catalog_serviceprice", "branch_id", "tenancy_branch"),
        # one price per (service, branch-or-default) on any given day
        migrations.RunSQL(
            "ALTER TABLE catalog_serviceprice ADD CONSTRAINT svcprice_no_overlap EXCLUDE USING gist ("
            "tenant_id WITH =, service_id WITH =, (COALESCE(branch_id, 0)) WITH =, "
            "daterange(valid_from, valid_to, '[)') WITH &&);",
            "ALTER TABLE catalog_serviceprice DROP CONSTRAINT svcprice_no_overlap;"),
    ]
