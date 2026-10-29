"""Price lookup and price changes. Past prices are never edited."""
from datetime import date

from django.db import transaction
from django.db.models import Q

from apps.audit.services.log import record as audit
from apps.catalog.models import Service, ServicePrice
from apps.core.dates import business_date
from apps.core.errors import DomainError
from apps.core.money import money


def _active(service_id, branch_id, on: date):
    return (ServicePrice.objects.filter(service_id=service_id, branch_id=branch_id, valid_from__lte=on)
            .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=on)))


def price_on(service: Service, branch_id, on: date):
    """Branch price if one applies on that date, else the company default; None if the service has no price."""
    row = (branch_id and _active(service.id, branch_id, on).first()) or _active(service.id, None, on).first()
    return row.price if row else None


def set_price(service: Service, *, price, branch_id=None, valid_from: date | None = None, user=None) -> ServicePrice:
    today = business_date()  # the same day the till and the app price by (starts 04:00)
    valid_from = valid_from or today
    if valid_from < today:
        raise DomainError(code="price_backdated", message="A price change cannot start in the past")
    amount = money(price)
    if amount < 0:
        raise DomainError(code="price_negative")
    with transaction.atomic():
        rows = list(ServicePrice.objects.select_for_update().filter(service_id=service.id, branch_id=branch_id)
                    .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=valid_from)).order_by("valid_from"))
        for row in rows:
            if row.valid_from >= valid_from:
                # a not-yet-effective future row is replaced; it was never used by any document
                row.delete()
            else:
                row.valid_to = valid_from
                row.save(update_fields=["valid_to"])
        new = ServicePrice.objects.create(service=service, branch_id=branch_id, price=amount, valid_from=valid_from,
                                          created_by=user)
        audit("catalog.price.set", tenant_id=service.tenant_id, actor=user, obj=new,
              data={"service": service.id, "branch": branch_id, "price": str(amount), "from": valid_from.isoformat()})
    return new
