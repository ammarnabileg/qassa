"""Point of sale. Money is numeric(18,3). An issued invoice is never edited: corrections are credit notes.
Prices are copied onto the line at issue time, so later price changes never touch it."""
from django.db import models
from django.db.models import F, Q

from apps.tenancy.scoping import TenantScopedModel

MONEY = dict(max_digits=18, decimal_places=3)


class CashSession(TenantScopedModel):
    """A drawer shift at a branch. One open session per branch; cash cannot be taken or refunded without it."""
    class Status(models.TextChoices):
        OPEN = "open"
        CLOSED = "closed"

    class Variance(models.TextChoices):
        NONE = "none"          # counted == expected
        PENDING = "pending"    # waiting for a second person to approve
        APPROVED = "approved"  # approved and posted to CASH_OVER_SHORT

    branch = models.ForeignKey("tenancy.Branch", on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=6, choices=Status.choices, default=Status.OPEN)
    opened_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    opened_at = models.DateTimeField(auto_now_add=True)
    opening_float = models.DecimalField(**MONEY)
    closed_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    closed_at = models.DateTimeField(null=True, blank=True)
    expected_cash = models.DecimalField(**MONEY, null=True, blank=True)
    counted_cash = models.DecimalField(**MONEY, null=True, blank=True)
    variance = models.DecimalField(**MONEY, null=True, blank=True)  # counted - expected
    variance_status = models.CharField(max_length=8, choices=Variance.choices, default=Variance.NONE)
    variance_approved_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    notes = models.TextField(blank=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "id"], name="uniq_cashsession_tenant_id"),
            models.UniqueConstraint(fields=["branch"], condition=Q(status="open"), name="one_open_session_per_branch"),
            models.CheckConstraint(condition=Q(opening_float__gte=0), name="cashsession_float_non_negative"),
        ]


class Invoice(TenantScopedModel):
    legal_entity = models.ForeignKey("tenancy.LegalEntity", on_delete=models.PROTECT, related_name="+")
    branch = models.ForeignKey("tenancy.Branch", on_delete=models.PROTECT, related_name="+")
    number = models.CharField(max_length=24)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    beneficiary = models.ForeignKey("customers.Beneficiary", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    appointment = models.OneToOneField("booking.Appointment", on_delete=models.PROTECT, null=True, blank=True, related_name="invoice")
    cash_session = models.ForeignKey(CashSession, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    subtotal = models.DecimalField(**MONEY)
    discount_total = models.DecimalField(**MONEY)
    total = models.DecimalField(**MONEY)
    is_credit = models.BooleanField(default=False)  # issued with an unpaid balance (deferred payment)
    business_date = models.DateField(db_index=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    issued_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    discount_approved_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, null=True, blank=True, related_name="+")

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "id"], name="uniq_invoice_tenant_id"),
            models.UniqueConstraint(fields=["tenant", "number"], name="uniq_invoice_number"),
            models.CheckConstraint(condition=Q(total=F("subtotal") - F("discount_total")), name="invoice_total_math"),
            models.CheckConstraint(condition=Q(total__gte=0) & Q(discount_total__gte=0), name="invoice_non_negative"),
        ]


class InvoiceLine(TenantScopedModel):
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="lines")
    service = models.ForeignKey("catalog.Service", on_delete=models.PROTECT, related_name="+")
    staff = models.ForeignKey("staff.StaffMember", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    name_ar = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120, blank=True)
    qty = models.PositiveSmallIntegerField()
    unit_price = models.DecimalField(**MONEY)
    discount = models.DecimalField(**MONEY)
    line_total = models.DecimalField(**MONEY)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "id"], name="uniq_invline_tenant_id"),
            models.CheckConstraint(condition=Q(qty__gte=1), name="invline_qty_positive"),
            models.CheckConstraint(condition=Q(line_total=F("qty") * F("unit_price") - F("discount")), name="invline_math"),
            models.CheckConstraint(condition=Q(discount__gte=0) & Q(line_total__gte=0), name="invline_non_negative"),
        ]


class CreditNote(TenantScopedModel):
    """A return against an issued invoice (partial or full). Approved by someone with pos.return."""
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="credit_notes")
    number = models.CharField(max_length=24)
    reason = models.CharField(max_length=300)
    total = models.DecimalField(**MONEY)
    business_date = models.DateField()
    issued_at = models.DateTimeField(auto_now_add=True)
    issued_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "id"], name="uniq_creditnote_tenant_id"),
            models.UniqueConstraint(fields=["tenant", "number"], name="uniq_creditnote_number"),
            models.CheckConstraint(condition=Q(total__gt=0), name="creditnote_positive"),
        ]


class CreditNoteLine(TenantScopedModel):
    credit_note = models.ForeignKey(CreditNote, on_delete=models.PROTECT, related_name="lines")
    invoice_line = models.ForeignKey(InvoiceLine, on_delete=models.PROTECT, related_name="credit_lines")
    amount = models.DecimalField(**MONEY)

    class Meta(TenantScopedModel.Meta):
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="cnline_positive")]


class Payment(TenantScopedModel):
    """Money in (receipt) or out (refund) against an invoice. Cash always belongs to an open drawer session."""
    class Direction(models.TextChoices):
        IN = "in"
        OUT = "out"

    class Method(models.TextChoices):
        CASH = "cash"
        KNET = "knet"          # card terminal, not integrated: the cashier types the approval code
        TRANSFER = "transfer"  # bank transfer / link, confirmed manually

    branch = models.ForeignKey("tenancy.Branch", on_delete=models.PROTECT, related_name="+")
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    credit_note = models.ForeignKey(CreditNote, on_delete=models.PROTECT, null=True, blank=True, related_name="refunds")
    direction = models.CharField(max_length=3, choices=Direction.choices)
    method = models.CharField(max_length=8, choices=Method.choices)
    amount = models.DecimalField(**MONEY)
    reference = models.CharField(max_length=60, blank=True)
    cash_session = models.ForeignKey(CashSession, on_delete=models.PROTECT, null=True, blank=True, related_name="payments")
    business_date = models.DateField()
    received_at = models.DateTimeField(auto_now_add=True)
    received_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "id"], name="uniq_payment_tenant_id"),
            models.CheckConstraint(condition=Q(amount__gt=0), name="payment_positive"),
            models.CheckConstraint(condition=~Q(method="cash") | Q(cash_session__isnull=False), name="cash_needs_session"),
            models.CheckConstraint(condition=Q(method="cash") | ~Q(reference=""), name="noncash_needs_reference"),
        ]
