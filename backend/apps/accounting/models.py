from django.db import models

from apps.tenancy.scoping import TenantScopedModel

MONEY = dict(max_digits=18, decimal_places=3)


class AccountType(models.TextChoices):
    ASSET = "asset"
    LIABILITY = "liability"
    EQUITY = "equity"
    REVENUE = "revenue"
    EXPENSE = "expense"


DEBIT_NORMAL = {AccountType.ASSET, AccountType.EXPENSE}


class Account(TenantScopedModel):
    legal_entity = models.ForeignKey("tenancy.LegalEntity", on_delete=models.PROTECT, related_name="accounts")
    code = models.CharField(max_length=20)
    name_ar = models.CharField(max_length=150)
    name_en = models.CharField(max_length=150)
    type = models.CharField(max_length=10, choices=AccountType.choices)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    is_postable = models.BooleanField(default=True)   # header accounts are not postable
    is_control = models.BooleanField(default=False)   # AR/AP/inventory: only subledger events may post
    is_active = models.BooleanField(default=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "id"], name="uniq_account_tenant_id"),
            models.UniqueConstraint(fields=["legal_entity", "code"], name="uniq_account_code"),
        ]
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} {self.name_en}"


class AccountRoleMapping(TenantScopedModel):
    """Operational account roles (CASH_DRAWER, SERVICE_REVENUE…) → real accounts, configurable per entity."""
    legal_entity = models.ForeignKey("tenancy.LegalEntity", on_delete=models.PROTECT)
    role = models.CharField(max_length=60)
    account = models.ForeignKey(Account, on_delete=models.PROTECT)

    class Meta(TenantScopedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["legal_entity", "role"], name="uniq_account_role")]


class FiscalYear(TenantScopedModel):
    legal_entity = models.ForeignKey("tenancy.LegalEntity", on_delete=models.PROTECT)
    name = models.CharField(max_length=20)
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta(TenantScopedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["legal_entity", "name"], name="uniq_fiscal_year"),
                       models.UniqueConstraint(fields=["tenant", "id"], name="uniq_fy_tenant_id")]


class FiscalPeriod(TenantScopedModel):
    class Status(models.TextChoices):
        OPEN = "open"
        CLOSED = "closed"

    fiscal_year = models.ForeignKey(FiscalYear, on_delete=models.PROTECT, related_name="periods")
    legal_entity = models.ForeignKey("tenancy.LegalEntity", on_delete=models.PROTECT)
    number = models.PositiveSmallIntegerField()
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.OPEN)
    closed_at = models.DateTimeField(null=True)
    closed_by = models.ForeignKey("identity.User", null=True, on_delete=models.PROTECT, related_name="+")

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "id"], name="uniq_period_tenant_id"),
            models.UniqueConstraint(fields=["fiscal_year", "number"], name="uniq_period_number"),
        ]


class JournalEntry(TenantScopedModel):
    class Status(models.TextChoices):
        DRAFT = "draft"
        POSTED = "posted"

    legal_entity = models.ForeignKey("tenancy.LegalEntity", on_delete=models.PROTECT)
    branch = models.ForeignKey("tenancy.Branch", null=True, blank=True, on_delete=models.PROTECT)
    period = models.ForeignKey(FiscalPeriod, on_delete=models.PROTECT)
    number = models.CharField(max_length=30, blank=True)
    entry_date = models.DateField()
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.DRAFT)
    kind = models.CharField(max_length=10, default="manual")  # manual | auto
    source_type = models.CharField(max_length=60, blank=True)  # e.g. "pos.invoice"
    source_id = models.CharField(max_length=64, blank=True)
    event_type = models.CharField(max_length=60, blank=True)   # e.g. "invoice.approved"
    memo = models.TextField(blank=True)
    reversal_of = models.OneToOneField("self", null=True, blank=True, on_delete=models.PROTECT,
                                       related_name="reversed_by")
    created_by = models.ForeignKey("identity.User", null=True, on_delete=models.PROTECT, related_name="+")
    posted_by = models.ForeignKey("identity.User", null=True, on_delete=models.PROTECT, related_name="+")
    posted_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "id"], name="uniq_je_tenant_id"),
            models.UniqueConstraint(fields=["tenant", "source_type", "source_id", "event_type"],
                                    condition=~models.Q(source_type=""), name="uniq_je_source_event"),
            models.UniqueConstraint(fields=["legal_entity", "number"], condition=~models.Q(number=""),
                                    name="uniq_je_number"),
        ]
        indexes = [models.Index(fields=["legal_entity", "entry_date"])]


class JournalLine(TenantScopedModel):
    entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name="lines")
    line_no = models.PositiveSmallIntegerField()
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="lines")
    debit = models.DecimalField(**MONEY, default=0)
    credit = models.DecimalField(**MONEY, default=0)
    branch = models.ForeignKey("tenancy.Branch", null=True, blank=True, on_delete=models.PROTECT)
    description = models.CharField(max_length=255, blank=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.CheckConstraint(condition=models.Q(debit__gte=0) & models.Q(credit__gte=0),
                                   name="jl_non_negative"),
            models.CheckConstraint(condition=(models.Q(debit=0) & models.Q(credit__gt=0)) |
                                   (models.Q(credit=0) & models.Q(debit__gt=0)), name="jl_one_side"),
            models.UniqueConstraint(fields=["entry", "line_no"], name="uniq_jl_line_no"),
        ]
        indexes = [models.Index(fields=["account", "entry"])]
