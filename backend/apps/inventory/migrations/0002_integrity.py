from django.db import migrations

from apps.core.db import composite_tenant_fk

FKS = [("inventory_stocklevel", "branch_id", "tenancy_branch"), ("inventory_stocklevel", "product_id", "inventory_product"),
       ("inventory_stockmove", "branch_id", "tenancy_branch"), ("inventory_stockmove", "product_id", "inventory_product"),
       ("inventory_goodsreceipt", "branch_id", "tenancy_branch"), ("inventory_goodsreceipt", "supplier_id", "inventory_supplier"),
       ("inventory_goodsreceiptline", "receipt_id", "inventory_goodsreceipt"),
       ("inventory_goodsreceiptline", "product_id", "inventory_product"),
       ("inventory_supplierbill", "receipt_id", "inventory_goodsreceipt"),
       ("inventory_supplierpayment", "bill_id", "inventory_supplierbill")]
IMMUTABLE = ["inventory_stockmove", "inventory_goodsreceipt", "inventory_goodsreceiptline", "inventory_supplierbill",
             "inventory_supplierpayment"]


class Migration(migrations.Migration):
    dependencies = [("inventory", "0001_initial"), ("pos", "0002_integrity")]
    operations = [composite_tenant_fk(t, c, r) for t, c, r in FKS] + [migrations.RunSQL(
        f"CREATE TRIGGER {t}_immutable BEFORE UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION pos_immutable();",
        f"DROP TRIGGER {t}_immutable ON {t};") for t in IMMUTABLE]
