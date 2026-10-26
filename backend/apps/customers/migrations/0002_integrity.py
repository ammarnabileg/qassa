from django.db import migrations

from apps.core.db import composite_tenant_fk


class Migration(migrations.Migration):
    dependencies = [("customers", "0001_initial")]
    operations = [composite_tenant_fk("customers_beneficiary", "customer_id", "customers_customer")]
