from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("audit", "0002_initial")]
    operations = [migrations.RunSQL(
        """CREATE OR REPLACE FUNCTION audit_append_only() RETURNS trigger AS $$
           BEGIN RAISE EXCEPTION 'audit log is append-only' USING ERRCODE = 'restrict_violation'; END $$ LANGUAGE plpgsql;
           CREATE TRIGGER audit_no_update BEFORE UPDATE OR DELETE ON audit_auditlog
           FOR EACH ROW EXECUTE FUNCTION audit_append_only();""",
        "DROP TRIGGER IF EXISTS audit_no_update ON audit_auditlog; DROP FUNCTION IF EXISTS audit_append_only();")]
