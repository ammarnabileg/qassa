"""Customer = the account holder who books and pays (a parent/guardian for kids).
Beneficiary = the person who receives the service (the customer themself, or a child)."""
from django.db import models

from apps.tenancy.scoping import TenantScopedModel


class Customer(TenantScopedModel):
    full_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=16)  # E.164 without "+", e.g. 96555551234
    email = models.EmailField(blank=True)
    preferred_language = models.CharField(max_length=2, choices=[("ar", "ar"), ("en", "en")], default="ar")
    whatsapp_opt_in = models.BooleanField(default=True)    # service messages (booking reminders, receipts)
    marketing_opt_in = models.BooleanField(default=False)  # offers — explicit consent only (D-002)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "id"], name="uniq_customer_tenant_id"),
            models.UniqueConstraint(fields=["tenant", "phone"], name="uniq_customer_phone"),
        ]


class Beneficiary(TenantScopedModel):
    class Relation(models.TextChoices):
        SELF = "self"
        CHILD = "child"
        OTHER = "other"

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="beneficiaries")
    full_name = models.CharField(max_length=120)
    relation = models.CharField(max_length=8, choices=Relation.choices)
    birth_date = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=1, choices=[("m", "m"), ("f", "f")], blank=True)
    notes = models.TextField(blank=True)  # allergies, sensitivities, preferences
    is_active = models.BooleanField(default=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "id"], name="uniq_beneficiary_tenant_id"),
            models.UniqueConstraint(fields=["customer"], condition=models.Q(relation="self"), name="uniq_beneficiary_self"),
        ]
