"""Is a staff member working at a branch for a whole time range? Weekly hours (if any) and time off."""
from datetime import datetime

from django.utils import timezone

from apps.staff.models import TimeOff, WorkingHours


def available(staff_id, branch, start: datetime, end: datetime, hours=None, offs=None) -> bool:
    local_s, local_e = timezone.localtime(start), timezone.localtime(end)
    if hours is None:
        hours = list(WorkingHours.objects.filter(staff_id=staff_id, branch=branch))
    if hours:  # a schedule exists: the range must fit inside one interval of that weekday
        if local_s.date() != local_e.date() and local_e.time() != datetime.min.time():
            return False
        ok = any(h.weekday == local_s.weekday() and h.starts_at <= local_s.time() and
                 (local_e.time() <= h.ends_at or (local_e.time() == datetime.min.time() and h.ends_at == datetime.max.time()))
                 for h in hours)
        if not ok:
            return False
    if offs is None:
        offs = list(TimeOff.objects.filter(staff_id=staff_id, starts_at__lt=end, ends_at__gt=start))
    return not any(o.starts_at < end and o.ends_at > start for o in offs)
