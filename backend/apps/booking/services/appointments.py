"""Booking rules. The database is the last line against double-booking (exclusion constraint); these checks give
clear errors first."""
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.services.log import record as audit
from apps.booking.models import ACTIVE, Appointment, AppointmentItem
from apps.catalog.models import Service
from apps.core.dates import business_date
from apps.core.errors import ConflictError, DomainError
from apps.customers.models import Beneficiary, Customer
from apps.notifications import auto
from apps.staff.models import StaffBranch, StaffMember, StaffSkill
from apps.tenancy.models import Branch

S = Appointment.Status
TRANSITIONS = {
    S.BOOKED: {S.ARRIVED, S.IN_SERVICE, S.CANCELLED, S.NO_SHOW},
    S.ARRIVED: {S.IN_SERVICE, S.BOOKED, S.CANCELLED},
    S.IN_SERVICE: {S.COMPLETED, S.ARRIVED},
    S.COMPLETED: {S.IN_SERVICE},  # reopen if marked done by mistake (before invoicing)
    S.INVOICED: set(), S.CANCELLED: set(), S.NO_SHOW: set(),
}


class SlotTaken(ConflictError):
    code = "slot_taken"


@dataclass
class ItemSpec:
    service_id: int
    staff_id: int


def _plan(branch: Branch, starts_at: datetime, specs: list[ItemSpec]):
    if not specs:
        raise DomainError(code="appointment_empty")
    services = {s.id: s for s in Service.objects.select_related("category").filter(id__in=[x.service_id for x in specs])}
    staff = {s.id: s for s in StaffMember.objects.filter(id__in=[x.staff_id for x in specs])}
    t, plan = starts_at, []
    for i, spec in enumerate(specs):
        svc, person = services.get(spec.service_id), staff.get(spec.staff_id)
        if svc is None or not svc.is_active:
            raise DomainError(code="service_unknown", details={"position": i})
        if svc.category.business_type != branch.business_type:
            raise DomainError(code="service_not_for_branch", details={"position": i})
        if person is None or not person.is_active:
            raise DomainError(code="staff_unknown", details={"position": i})
        if not StaffBranch.objects.filter(staff=person, branch=branch).exists():
            raise DomainError(code="staff_not_in_branch", details={"position": i})
        if not StaffSkill.objects.filter(staff=person, service=svc).exists():
            raise DomainError(code="staff_lacks_skill", details={"position": i})
        end = t + timedelta(minutes=svc.duration_minutes)
        from apps.staff.services.availability import available
        if not available(person.id, branch, t, end):
            raise DomainError(code="staff_unavailable", message="Outside the staff member's hours or on time off",
                              details={"position": i})
        plan.append((svc, person, t, end))
        t = end
    return plan


def _write_items(appt, plan):
    try:
        with transaction.atomic():
            for pos, (svc, person, start, end) in enumerate(plan):
                AppointmentItem.objects.create(appointment=appt, service=svc, staff=person, position=pos,
                                               starts_at=start, ends_at=end)
    except IntegrityError as e:
        if "apptitem_no_overlap" in str(e):
            raise SlotTaken(message="The staff member is already booked at this time")
        raise


def create_appointment(*, branch: Branch, starts_at: datetime, items: list[ItemSpec], customer_id=None,
                       beneficiary_id=None, walk_in_name="", source=Appointment.Source.RECEPTION, notes="", user=None):
    if starts_at < timezone.now() - timedelta(minutes=15) and source != Appointment.Source.WALK_IN:
        raise DomainError(code="appointment_in_past")
    customer = beneficiary = None
    if customer_id:
        customer = Customer.objects.filter(id=customer_id).first()
        if customer is None:
            raise DomainError(code="customer_unknown")
    if beneficiary_id:
        beneficiary = Beneficiary.objects.filter(id=beneficiary_id, customer=customer).first()
        if beneficiary is None:
            raise DomainError(code="beneficiary_unknown")
    if customer is None and not walk_in_name.strip():
        raise DomainError(code="appointment_needs_customer")
    with transaction.atomic():
        plan = _plan(branch, starts_at, items)
        appt = Appointment.objects.create(
            branch=branch, customer=customer, beneficiary=beneficiary, walk_in_name=walk_in_name.strip(),
            status=S.ARRIVED if source == Appointment.Source.WALK_IN else S.BOOKED, source=source,
            starts_at=starts_at, ends_at=plan[-1][3], business_date=business_date(starts_at), notes=notes,
            created_by=user)
        _write_items(appt, plan)
        audit("booking.created", tenant_id=appt.tenant_id, actor=user, obj=appt,
              data={"branch": branch.id, "starts_at": starts_at.isoformat(), "items": len(plan)})
        auto.booking_created(appt)
    return appt


def reschedule(appt: Appointment, *, starts_at: datetime, items: list[ItemSpec], user=None):
    if appt.status not in {S.BOOKED, S.ARRIVED}:
        raise DomainError(code="appointment_locked", details={"status": appt.status})
    with transaction.atomic():
        appt = Appointment.objects.select_for_update().get(id=appt.id)
        AppointmentItem.objects.filter(appointment=appt).delete()
        plan = _plan(appt.branch, starts_at, items)
        _write_items(appt, plan)
        appt.starts_at, appt.ends_at, appt.business_date = starts_at, plan[-1][3], business_date(starts_at)
        appt.save(update_fields=["starts_at", "ends_at", "business_date", "updated_at"])
        audit("booking.rescheduled", tenant_id=appt.tenant_id, actor=user, obj=appt, data={"starts_at": starts_at.isoformat()})
        auto.booking_rescheduled(appt)
    return appt


def set_status(appt: Appointment, new: str, *, user=None, reason=""):
    with transaction.atomic():
        appt = Appointment.objects.select_for_update().get(id=appt.id)
        if new not in TRANSITIONS[appt.status]:
            raise DomainError(code="appointment_bad_transition", details={"from": appt.status, "to": new})
        if new in {S.CANCELLED, S.NO_SHOW} and not reason.strip():
            raise DomainError(code="reason_required")
        appt.status, appt.status_reason = new, reason.strip()
        appt.save(update_fields=["status", "status_reason", "updated_at"])
        if new not in ACTIVE:
            AppointmentItem.objects.filter(appointment=appt).update(active=False)
        audit(f"booking.{new}", tenant_id=appt.tenant_id, actor=user, obj=appt, reason=reason)
    return appt
