"""PostgreSQL helpers used in migrations."""
from django.db import migrations


def composite_tenant_fk(table, column, ref_table, name=None):
    """FOREIGN KEY (tenant_id, column) REFERENCES ref_table (tenant_id, id).

    Guarantees at the database level that a row can only reference rows of the same tenant.
    The referenced table needs UNIQUE(tenant_id, id).
    """
    name = name or f"fk_{table}_{column}_same_tenant"[:63]
    return migrations.RunSQL(
        f'ALTER TABLE "{table}" ADD CONSTRAINT "{name}" FOREIGN KEY ("tenant_id", "{column}") '
        f'REFERENCES "{ref_table}" ("tenant_id", "id") DEFERRABLE INITIALLY IMMEDIATE;',
        f'ALTER TABLE "{table}" DROP CONSTRAINT "{name}";',
    )
