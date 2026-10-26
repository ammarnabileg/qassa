from django.db import migrations

from apps.core.db import composite_tenant_fk

FKS = [
    ("pos_cashsession", "branch_id", "tenancy_branch"),
    ("pos_invoice", "legal_entity_id", "tenancy_legalentity"),
    ("pos_invoice", "branch_id", "tenancy_branch"),
    ("pos_invoice", "customer_id", "customers_customer"),
    ("pos_invoice", "beneficiary_id", "customers_beneficiary"),
    ("pos_invoice", "appointment_id", "booking_appointment"),
    ("pos_invoice", "cash_session_id", "pos_cashsession"),
    ("pos_invoiceline", "invoice_id", "pos_invoice"),
    ("pos_invoiceline", "service_id", "catalog_service"),
    ("pos_invoiceline", "staff_id", "staff_staffmember"),
    ("pos_creditnote", "invoice_id", "pos_invoice"),
    ("pos_payment", "branch_id", "tenancy_branch"),
    ("pos_payment", "invoice_id", "pos_invoice"),
    ("pos_payment", "credit_note_id", "pos_creditnote"),
    ("pos_payment", "cash_session_id", "pos_cashsession"),
]
# Issued financial documents are immutable; corrections are new documents (credit notes, refunds).
IMMUTABLE = ["pos_invoice", "pos_invoiceline", "pos_creditnote", "pos_creditnoteline", "pos_payment"]

FN = """
CREATE OR REPLACE FUNCTION pos_immutable() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'pos documents are immutable (% on %)', TG_OP, TG_TABLE_NAME; END $$ LANGUAGE plpgsql;
"""


class Migration(migrations.Migration):
    dependencies = [("pos", "0001_initial"), ("booking", "0002_integrity")]
    operations = [composite_tenant_fk(t, c, r) for t, c, r in FKS] + [
        composite_tenant_fk("pos_creditnoteline", "credit_note_id", "pos_creditnote", name="fk_pos_cnline_cn_same_tenant"),
        composite_tenant_fk("pos_creditnoteline", "invoice_line_id", "pos_invoiceline", name="fk_pos_cnline_il_same_tenant"),
        migrations.RunSQL(FN, "DROP FUNCTION pos_immutable();"),
    ] + [migrations.RunSQL(
        f"CREATE TRIGGER {t}_immutable BEFORE UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION pos_immutable();",
        f"DROP TRIGGER {t}_immutable ON {t};") for t in IMMUTABLE]
