from django.db import migrations

from apps.core.db import composite_tenant_fk


class Migration(migrations.Migration):
    dependencies = [("catalog", "0006_upsell_rebook")]
    operations = [composite_tenant_fk("catalog_service", "upsell_id", "catalog_service")]
