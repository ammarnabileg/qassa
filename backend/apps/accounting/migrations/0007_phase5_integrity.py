from django.db import migrations

from apps.core.db import composite_tenant_fk

FKS = [("accounting_expense", "legal_entity_id", "tenancy_legalentity"), ("accounting_expense", "branch_id", "tenancy_branch"),
       ("accounting_expense", "account_id", "accounting_account"),
       ("accounting_fixedasset", "legal_entity_id", "tenancy_legalentity"), ("accounting_fixedasset", "branch_id", "tenancy_branch"),
       ("accounting_clearingsettlement", "legal_entity_id", "tenancy_legalentity"),
       ("accounting_reportversion", "legal_entity_id", "tenancy_legalentity")]
IMMUTABLE = ["accounting_clearingsettlement", "accounting_reportversion"]


class Migration(migrations.Migration):
    dependencies = [("accounting", "0006_phase5"), ("pos", "0002_integrity"), ("tenancy", "0006_sync_role_permissions_phase4")]
    operations = [composite_tenant_fk(t, c, r) for t, c, r in FKS] + [migrations.RunSQL(
        f"CREATE TRIGGER {t}_immutable BEFORE UPDATE OR DELETE ON {t} FOR EACH ROW EXECUTE FUNCTION pos_immutable();",
        f"DROP TRIGGER {t}_immutable ON {t};") for t in IMMUTABLE]
