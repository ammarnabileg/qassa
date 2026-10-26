"""Products, stock per branch at weighted-average cost, suppliers and purchasing (architecture §6.2 examples 2, 8).
Stock never goes negative (policy default). Moves are immutable; corrections are new moves."""
from django.db import models
from django.db.models import Q

from apps.tenancy.scoping import TenantScopedModel

MONEY = dict(max_digits=18, decimal_places=3)
COST = dict(max_digits=18, decimal_places=6)
QTY = dict(max_digits=12, decimal_places=3)


class Product(TenantScopedModel):
    class Kind(models.TextChoices):
        RETAIL = "retail"    # sold to customers
        SUPPLY = "supply"    # used in services (dye, shampoo…)

    sku = models.CharField(max_length=40)
    name_ar = models.CharField(max_length=120)
    name_en = models.CharField(max_length=120, blank=True)
    kind = models.CharField(max_length=6, choices=Kind.choices, default=Kind.RETAIL)
    unit = models.CharField(max_length=20, default="pcs")
    sale_price = models.DecimalField(**MONEY, null=True, blank=True)  # retail only
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "id"], name="uniq_product_tenant_id"),
            models.UniqueConstraint(fields=["tenant", "sku"], name="uniq_product_sku"),
            models.CheckConstraint(condition=Q(sale_price__isnull=True) | Q(sale_price__gte=0), name="product_price_non_negative"),
        ]


class StockLevel(TenantScopedModel):
    branch = models.ForeignKey("tenancy.Branch", on_delete=models.PROTECT, related_name="+")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="levels")
    qty = models.DecimalField(**QTY, default=0)
    avg_cost = models.DecimalField(**COST, default=0)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["branch", "product"], name="uniq_stock_level"),
            models.CheckConstraint(condition=Q(qty__gte=0), name="stock_not_negative"),
        ]


class StockMove(TenantScopedModel):
    class Kind(models.TextChoices):
        RECEIPT = "receipt"
        SALE = "sale"
        RETURN = "return"
        ADJUST = "adjust"
        CONSUME = "consume"

    branch = models.ForeignKey("tenancy.Branch", on_delete=models.PROTECT, related_name="+")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="moves")
    kind = models.CharField(max_length=8, choices=Kind.choices)
    qty = models.DecimalField(**QTY)              # + in, − out
    unit_cost = models.DecimalField(**COST)
    value = models.DecimalField(**MONEY)          # qty × unit_cost, signed
    source_type = models.CharField(max_length=40, blank=True)
    source_id = models.CharField(max_length=40, blank=True)
    reason = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [models.CheckConstraint(condition=~Q(qty=0), name="stockmove_nonzero")]
        indexes = [models.Index(fields=["tenant", "branch", "product", "created_at"])]


class Supplier(TenantScopedModel):
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "id"], name="uniq_supplier_tenant_id")]


class GoodsReceipt(TenantScopedModel):
    number = models.CharField(max_length=24)
    branch = models.ForeignKey("tenancy.Branch", on_delete=models.PROTECT, related_name="+")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="receipts")
    received_on = models.DateField()
    total = models.DecimalField(**MONEY)
    notes = models.CharField(max_length=300, blank=True)
    created_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "id"], name="uniq_grn_tenant_id"),
                       models.UniqueConstraint(fields=["tenant", "number"], name="uniq_grn_number")]


class GoodsReceiptLine(TenantScopedModel):
    receipt = models.ForeignKey(GoodsReceipt, on_delete=models.PROTECT, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="+")
    qty = models.DecimalField(**QTY)
    unit_cost = models.DecimalField(**COST)
    line_total = models.DecimalField(**MONEY)

    class Meta(TenantScopedModel.Meta):
        constraints = [models.CheckConstraint(condition=Q(qty__gt=0) & Q(unit_cost__gte=0), name="grnline_positive")]


class SupplierBill(TenantScopedModel):
    """The supplier's invoice for a receipt. Its amount must match the received value (price differences are
    an accountant's decision, see ARCHITECTURE §6.2 ex. 8 — not booked automatically)."""
    receipt = models.OneToOneField(GoodsReceipt, on_delete=models.PROTECT, related_name="bill")
    supplier_ref = models.CharField(max_length=60)
    bill_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    amount = models.DecimalField(**MONEY)
    created_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [models.UniqueConstraint(fields=["tenant", "id"], name="uniq_bill_tenant_id")]


class SupplierPayment(TenantScopedModel):
    bill = models.ForeignKey(SupplierBill, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(**MONEY)
    paid_on = models.DateField()
    reference = models.CharField(max_length=60)
    created_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name="supplierpayment_positive")]
