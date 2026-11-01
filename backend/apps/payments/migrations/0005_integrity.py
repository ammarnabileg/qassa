from django.db import migrations

from apps.core.db import composite_tenant_fk


class Migration(migrations.Migration):
    dependencies = [("payments", "0004_onlinepayment_tenant_id"), ("booking", "0003_appointment_deposit_amount_and_more")]
    operations = [
        composite_tenant_fk("payments_onlinepayment", "appointment_id", "booking_appointment"),
        composite_tenant_fk("payments_onlinerefund", "online_payment_id", "payments_onlinepayment"),
        composite_tenant_fk("payments_onlinerefund", "payment_id", "pos_payment"),
    ]
