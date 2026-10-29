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


class XbrlMapping(TenantScopedModel):
    """Account → MOCI XBRL line (annual financial statements). Overrides the role-based default (D-009)."""
    legal_entity = models.ForeignKey("tenancy.LegalEntity", on_delete=models.PROTECT)
    account = models.ForeignKey(Account, on_delete=models.CASCADE)
    tag = models.CharField(max_length=200)

    class Meta(TenantScopedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["legal_entity", "account"], name="uniq_xbrl_account")]


EXPENSE_ROLES = ["RENT", "UTILITIES", "SALARIES", "MARKETING", "PAYMENT_FEES", "OTHER_EXPENSES", "COST_OF_SERVICES_SUPPLIES"]


class Expense(TenantScopedModel):
    """An operating expense: paid now (bank / branch cash) or accrued and paid later (ACCRUED_EXPENSES)."""
    class PaidFrom(models.TextChoices):
        BANK = "bank"
        CASH = "cash"          # the branch cash drawer
        ACCRUED = "accrued"    # owed; settled later with pay_accrued()

    legal_entity = models.ForeignKey("tenancy.LegalEntity", on_delete=models.PROTECT)
    branch = models.ForeignKey("tenancy.Branch", null=True, blank=True, on_delete=models.PROTECT)
    expense_date = models.DateField()
    account = models.ForeignKey(Account, on_delete=models.PROTECT)
    description = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=18, decimal_places=3)
    paid_from = models.CharField(max_length=8, choices=PaidFrom.choices)
    reference = models.CharField(max_length=80, blank=True)
    paid_on = models.DateField(null=True, blank=True)        # for accrued: when settled
    paid_reference = models.CharField(max_length=80, blank=True)
    created_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [models.CheckConstraint(condition=models.Q(amount__gt=0), name="expense_amount_gt_0"),
                       models.UniqueConstraint(fields=["tenant", "id"], name="uniq_expense_tenant_id")]
        ordering = ["-expense_date", "-id"]


class FixedAsset(TenantScopedModel):
    """Straight-line depreciation, monthly, from the month after acquisition (accountant policy, D-011)."""
    legal_entity = models.ForeignKey("tenancy.LegalEntity", on_delete=models.PROTECT)
    branch = models.ForeignKey("tenancy.Branch", null=True, blank=True, on_delete=models.PROTECT)
    name = models.CharField(max_length=150)
    acquired_on = models.DateField()
    cost = models.DecimalField(max_digits=18, decimal_places=3)
    residual_value = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    life_months = models.PositiveSmallIntegerField()
    paid_from = models.CharField(max_length=8, choices=[("bank", "bank"), ("payable", "payable")])
    reference = models.CharField(max_length=80, blank=True)
    disposed_on = models.DateField(null=True, blank=True)
    created_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [models.CheckConstraint(condition=models.Q(cost__gt=0) & models.Q(residual_value__gte=0) &
                                              models.Q(life_months__gt=0), name="asset_values_valid"),
                       models.UniqueConstraint(fields=["tenant", "id"], name="uniq_asset_tenant_id")]
        ordering = ["-acquired_on", "-id"]


class ClearingSettlement(TenantScopedModel):
    """KNET / gateway settlement per the provider's report (example 11): bank receives net, fees expensed."""
    legal_entity = models.ForeignKey("tenancy.LegalEntity", on_delete=models.PROTECT)
    channel = models.CharField(max_length=8, choices=[("knet", "knet"), ("gateway", "gateway")])
    settled_on = models.DateField()
    gross = models.DecimalField(max_digits=18, decimal_places=3)
    fees = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    reference = models.CharField(max_length=80)
    created_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [models.CheckConstraint(condition=models.Q(gross__gt=0) & models.Q(fees__gte=0) &
                                              models.Q(fees__lt=models.F("gross")), name="settlement_values_valid"),
                       models.UniqueConstraint(fields=["legal_entity", "channel", "reference"], name="uniq_settlement_ref")]
        ordering = ["-settled_on", "-id"]


class ReportVersion(TenantScopedModel):
    """A frozen copy of a statement as issued (with a content hash), so a past version can be shown exactly."""
    legal_entity = models.ForeignKey("tenancy.LegalEntity", on_delete=models.PROTECT)
    kind = models.CharField(max_length=30)          # income_statement | balance_sheet | trial_balance | xbrl
    params = models.JSONField()
    data = models.JSONField()
    sha256 = models.CharField(max_length=64)
    note = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        ordering = ["-id"]
