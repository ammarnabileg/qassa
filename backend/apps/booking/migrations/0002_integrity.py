from django.db import migrations

from apps.core.db import composite_tenant_fk


class Migration(migrations.Migration):
    dependencies = [("booking", "0001_initial"), ("catalog", "0002_integrity"), ("staff", "0002_integrity"),
                    ("customers", "0002_integrity")]
    operations = [
        composite_tenant_fk("booking_appointment", "branch_id", "tenancy_branch"),
        composite_tenant_fk("booking_appointment", "customer_id", "customers_customer"),
        composite_tenant_fk("booking_appointment", "beneficiary_id", "customers_beneficiary"),
        composite_tenant_fk("booking_appointmentitem", "appointment_id", "booking_appointment"),
        composite_tenant_fk("booking_appointmentitem", "service_id", "catalog_service"),
        composite_tenant_fk("booking_appointmentitem", "staff_id", "staff_staffmember"),
        # a staff member cannot be in two active slots at once — whatever the application does
        migrations.RunSQL(
            "ALTER TABLE booking_appointmentitem ADD CONSTRAINT apptitem_no_overlap EXCLUDE USING gist ("
            "tenant_id WITH =, staff_id WITH =, tstzrange(starts_at, ends_at, '[)') WITH &&) WHERE (active);",
            "ALTER TABLE booking_appointmentitem DROP CONSTRAINT apptitem_no_overlap;"),
    ]
