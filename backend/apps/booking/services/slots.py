"""Free start times for online booking: within the branch's opening hours, in 15-minute steps, where at least one
qualified staff member has no overlapping active slot. Final protection is still the database constraint."""
from datetime import datetime, timedelta

from django.utils import timezone

from apps.booking.models import AppointmentItem
from apps.staff.models import StaffMember

STEP = timedelta(minutes=15)
LEAD = timedelta(minutes=30)  # earliest online start from now


def qualified_staff(branch, service):
    return list(StaffMember.objects.filter(is_active=True, branch_links__branch=branch, skill_links__service=service).distinct())


def free_slots(branch, service, day, staff_id=None) -> list[dict]:
    staff = [s for s in qualified_staff(branch, service) if staff_id in (None, s.id)]
    if not staff:
        return []
    tz = timezone.get_current_timezone()
    open_at = datetime.combine(day, branch.opens_at, tzinfo=tz)
    close_at = datetime.combine(day, branch.closes_at, tzinfo=tz)
    if close_at <= open_at:  # closes after midnight
        close_at += timedelta(days=1)
    length = timedelta(minutes=service.duration_minutes)
    busy = {}
    for it in AppointmentItem.objects.filter(active=True, staff__in=staff, starts_at__lt=close_at, ends_at__gt=open_at):
        busy.setdefault(it.staff_id, []).append((it.starts_at, it.ends_at))
    from apps.staff.models import TimeOff, WorkingHours
    from apps.staff.services.availability import available
    hours = {s.id: list(WorkingHours.objects.filter(staff=s, branch=branch)) for s in staff}
    offs = {s.id: list(TimeOff.objects.filter(staff=s, starts_at__lt=close_at, ends_at__gt=open_at)) for s in staff}
    earliest = timezone.now() + LEAD
    out, t = [], open_at
    while t + length <= close_at:
        if t >= earliest:
            free = [s.id for s in staff if all(not (t < e and t + length > b) for b, e in busy.get(s.id, []))
                    and available(s.id, branch, t, t + length, hours[s.id], offs[s.id])]
            if free:
                out.append({"starts_at": t.isoformat(), "time": t.strftime("%H:%M"), "staff_ids": free})
        t += STEP
    return out
