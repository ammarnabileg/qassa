from django.db import migrations

from apps.core.db import composite_tenant_fk


class Migration(migrations.Migration):
    dependencies = [("staff", "0005_tip_payout"), ("pos", "__first__")]
    operations = [
        composite_tenant_fk("staff_tippayout", "staff_id", "staff_staffmember"),
        composite_tenant_fk("staff_tippayout", "branch_id", "tenancy_branch"),
        composite_tenant_fk("staff_tippayout", "cash_session_id", "pos_cashsession"),
    ]
