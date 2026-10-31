from django.db import migrations

from apps.core.db import composite_tenant_fk


class Migration(migrations.Migration):
    dependencies = [("notifications", "0003_feedback_winback")]
    operations = [
        composite_tenant_fk("notifications_feedback", "invoice_id", "pos_invoice"),
        composite_tenant_fk("notifications_feedback", "customer_id", "customers_customer"),
        composite_tenant_fk("notifications_feedback", "branch_id", "tenancy_branch"),
    ]
