from django.db import migrations

from apps.core.db import composite_tenant_fk

BALANCE_FN = """
CREATE OR REPLACE FUNCTION accounting_check_entry_balanced() RETURNS trigger AS $$
DECLARE
  eid bigint;
  st text;
  d numeric; c numeric; n int;
BEGIN
  IF TG_TABLE_NAME = 'accounting_journalline' THEN
    eid := COALESCE(NEW.entry_id, OLD.entry_id);
  ELSE
    eid := COALESCE(NEW.id, OLD.id);
  END IF;
  SELECT status INTO st FROM accounting_journalentry WHERE id = eid;
  IF st = 'posted' THEN
    SELECT COALESCE(SUM(debit),0), COALESCE(SUM(credit),0), COUNT(*) INTO d, c, n
      FROM accounting_journalline WHERE entry_id = eid;
    IF d <> c OR n < 2 OR d = 0 THEN
      RAISE EXCEPTION 'journal entry % is not balanced (debit %, credit %, lines %)', eid, d, c, n
        USING ERRCODE = 'check_violation';
    END IF;
  END IF;
  RETURN NULL;
END $$ LANGUAGE plpgsql;
"""

IMMUTABLE_FN = """
CREATE OR REPLACE FUNCTION accounting_posted_immutable() RETURNS trigger AS $$
DECLARE st text;
BEGIN
  IF TG_TABLE_NAME = 'accounting_journalentry' THEN
    IF OLD.status = 'posted' THEN
      RAISE EXCEPTION 'posted journal entry % is immutable; reverse it instead', OLD.id USING ERRCODE = 'restrict_violation';
    END IF;
  ELSE
    SELECT status INTO st FROM accounting_journalentry WHERE id = COALESCE(NEW.entry_id, OLD.entry_id);
    IF st = 'posted' THEN
      RAISE EXCEPTION 'lines of a posted journal entry are immutable' USING ERRCODE = 'restrict_violation';
    END IF;
  END IF;
  IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;
"""


class Migration(migrations.Migration):
    dependencies = [("accounting", "0003_fiscalyear_uniq_fy_tenant_id"), ("tenancy", "0002_same_tenant_fks")]
    operations = [
        composite_tenant_fk("accounting_account", "legal_entity_id", "tenancy_legalentity"),
        composite_tenant_fk("accounting_account", "parent_id", "accounting_account"),
        composite_tenant_fk("accounting_accountrolemapping", "account_id", "accounting_account"),
        composite_tenant_fk("accounting_accountrolemapping", "legal_entity_id", "tenancy_legalentity"),
        composite_tenant_fk("accounting_fiscalyear", "legal_entity_id", "tenancy_legalentity"),
        composite_tenant_fk("accounting_fiscalperiod", "fiscal_year_id", "accounting_fiscalyear"),
        composite_tenant_fk("accounting_fiscalperiod", "legal_entity_id", "tenancy_legalentity"),
        composite_tenant_fk("accounting_journalentry", "legal_entity_id", "tenancy_legalentity"),
        composite_tenant_fk("accounting_journalentry", "branch_id", "tenancy_branch"),
        composite_tenant_fk("accounting_journalentry", "period_id", "accounting_fiscalperiod"),
        composite_tenant_fk("accounting_journalentry", "reversal_of_id", "accounting_journalentry"),
        composite_tenant_fk("accounting_journalline", "entry_id", "accounting_journalentry"),
        composite_tenant_fk("accounting_journalline", "account_id", "accounting_account"),
        composite_tenant_fk("accounting_journalline", "branch_id", "tenancy_branch"),
        migrations.RunSQL(BALANCE_FN, "DROP FUNCTION IF EXISTS accounting_check_entry_balanced();"),
        migrations.RunSQL(
            """CREATE CONSTRAINT TRIGGER jl_balanced AFTER INSERT OR UPDATE OR DELETE ON accounting_journalline
               DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION accounting_check_entry_balanced();
               CREATE CONSTRAINT TRIGGER je_balanced AFTER INSERT OR UPDATE ON accounting_journalentry
               DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION accounting_check_entry_balanced();""",
            "DROP TRIGGER IF EXISTS jl_balanced ON accounting_journalline; DROP TRIGGER IF EXISTS je_balanced ON accounting_journalentry;"),
        migrations.RunSQL(IMMUTABLE_FN, "DROP FUNCTION IF EXISTS accounting_posted_immutable();"),
        migrations.RunSQL(
            """CREATE TRIGGER je_immutable BEFORE UPDATE OR DELETE ON accounting_journalentry
               FOR EACH ROW EXECUTE FUNCTION accounting_posted_immutable();
               CREATE TRIGGER jl_immutable BEFORE INSERT OR UPDATE OR DELETE ON accounting_journalline
               FOR EACH ROW EXECUTE FUNCTION accounting_posted_immutable();""",
            "DROP TRIGGER IF EXISTS je_immutable ON accounting_journalentry; DROP TRIGGER IF EXISTS jl_immutable ON accounting_journalline;"),
    ]
