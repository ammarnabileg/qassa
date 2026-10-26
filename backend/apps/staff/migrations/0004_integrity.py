from django.db import migrations

from apps.core.db import composite_tenant_fk


class Migration(migrations.Migration):
    dependencies = [("staff", "0003_staffmember_commission_percent_commissionentry_and_more"), ("pos", "0002_integrity")]
    operations = [
        composite_tenant_fk("staff_commissionentry", "staff_id", "staff_staffmember"),
        composite_tenant_fk("staff_workinghours", "staff_id", "staff_staffmember"),
        composite_tenant_fk("staff_workinghours", "branch_id", "tenancy_branch"),
        composite_tenant_fk("staff_timeoff", "staff_id", "staff_staffmember"),
        migrations.RunSQL("CREATE TRIGGER staff_commissionentry_immutable BEFORE UPDATE OR DELETE ON staff_commissionentry "
                          "FOR EACH ROW EXECUTE FUNCTION pos_immutable();", "DROP TRIGGER staff_commissionentry_immutable ON staff_commissionentry;"),
    ]
