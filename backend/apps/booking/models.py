"""Appointments. One appointment = one visit of one beneficiary; items are the services in order, each with a
staff member and its own time slot. PostgreSQL forbids two active items overlapping for the same staff member."""
from django.db import models

from apps.tenancy.scoping import TenantScopedModel


class Appointment(TenantScopedModel):
    class Status(models.TextChoices):
        BOOKED = "booked"
        ARRIVED = "arrived"          # in the waiting queue
        IN_SERVICE = "in_service"    # on the chair
        COMPLETED = "completed"      # done, ready for the cashier
        INVOICED = "invoiced"
        CANCELLED = "cancelled"
        NO_SHOW = "no_show"

    class Source(models.TextChoices):
        RECEPTION = "reception"
        WALK_IN = "walk_in"
        ONLINE = "online"

    branch = models.ForeignKey("tenancy.Branch", on_delete=models.PROTECT, related_name="+")
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    beneficiary = models.ForeignKey("customers.Beneficiary", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    walk_in_name = models.CharField(max_length=120, blank=True)  # when there is no customer record
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.BOOKED)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.RECEPTION)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    business_date = models.DateField(db_index=True)
    notes = models.TextField(blank=True)
    status_reason = models.CharField(max_length=200, blank=True)
    created_by = models.ForeignKey("identity.User", on_delete=models.PROTECT, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "id"], name="uniq_appointment_tenant_id"),
            models.CheckConstraint(condition=models.Q(ends_at__gt=models.F("starts_at")), name="appointment_range_valid"),
        ]
        indexes = [models.Index(fields=["tenant", "branch", "business_date"])]


ACTIVE = {Appointment.Status.BOOKED, Appointment.Status.ARRIVED, Appointment.Status.IN_SERVICE,
          Appointment.Status.COMPLETED, Appointment.Status.INVOICED}


class AppointmentItem(TenantScopedModel):
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name="items")
    service = models.ForeignKey("catalog.Service", on_delete=models.PROTECT, related_name="+")
    staff = models.ForeignKey("staff.StaffMember", on_delete=models.PROTECT, related_name="+")
    position = models.PositiveSmallIntegerField()
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    active = models.BooleanField(default=True)  # false once the appointment is cancelled / no-show: frees the slot

    class Meta(TenantScopedModel.Meta):
        constraints = [
            models.UniqueConstraint(fields=["tenant", "id"], name="uniq_apptitem_tenant_id"),
            models.CheckConstraint(condition=models.Q(ends_at__gt=models.F("starts_at")), name="apptitem_range_valid"),
        ]
