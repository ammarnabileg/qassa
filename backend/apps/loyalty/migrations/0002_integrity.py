from django.db import migrations

from apps.core.db import composite_tenant_fk


class Migration(migrations.Migration):
    dependencies = [("loyalty", "0001_initial"), ("pos", "0004_creditnoteline_restock_qty_invoice_coupon_and_more")]
    operations = [
        composite_tenant_fk("loyalty_packageplan", "service_id", "catalog_service"),
        composite_tenant_fk("loyalty_customerpackage", "customer_id", "customers_customer"),
        composite_tenant_fk("loyalty_customerpackage", "plan_id", "loyalty_packageplan"),
        composite_tenant_fk("loyalty_customerpackage", "sold_on_line_id", "pos_invoiceline"),
        composite_tenant_fk("loyalty_pointsentry", "customer_id", "customers_customer"),
        migrations.RunSQL("CREATE TRIGGER loyalty_pointsentry_immutable BEFORE UPDATE OR DELETE ON loyalty_pointsentry "
                          "FOR EACH ROW EXECUTE FUNCTION pos_immutable();", "DROP TRIGGER loyalty_pointsentry_immutable ON loyalty_pointsentry;"),
    ]
