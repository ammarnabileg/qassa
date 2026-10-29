"""Between 00:00 and 04:00 Kuwait time the business day is still the previous day: a price set then must be
sellable immediately (found by CI running at 00:03)."""
from datetime import datetime
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.catalog.models import Service, ServiceCategory
from apps.catalog.services.pricing import price_on, set_price
from apps.core.dates import business_date
from apps.tenancy.context import tenant_context


def test_price_set_after_midnight_applies_to_the_current_business_day(company_a, monkeypatch):
    t, _, b = company_a
    one_am = datetime(2026, 10, 30, 1, 0, tzinfo=ZoneInfo("Asia/Kuwait"))
    monkeypatch.setattr(timezone, "now", lambda: one_am)
    assert business_date().isoformat() == "2026-10-29"
    with tenant_context(t.id):
        cat = ServiceCategory.objects.create(name_ar="قصات", business_type="kids")
        cut = Service.objects.create(category=cat, name_ar="قص", duration_minutes=30)
        set_price(cut, price="4.500")
        assert str(price_on(cut, b["HAW"].id, business_date())) == "4.500"
