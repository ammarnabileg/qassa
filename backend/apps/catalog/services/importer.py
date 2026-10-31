"""Bring a service menu over from a spreadsheet: categories are created as needed, a service with the same Arabic name
in the same category is matched and only its price is updated (a new price row, from today — history is kept)."""
from decimal import Decimal, InvalidOperation

from django.db import transaction

from apps.catalog.models import Service, ServiceCategory
from apps.catalog.services.pricing import price_on, set_price
from apps.core.dates import business_date
from apps.core.services.tabular import read_rows

ALIASES = {
    "name_ar": {"الخدمة", "اسم الخدمة", "الاسم", "service", "name", "service name"},
    "name_en": {"الاسم بالإنجليزي", "english name", "name en"},
    "category": {"القسم", "الفئة", "التصنيف", "category"},
    "duration": {"المدة", "المدة بالدقائق", "دقائق", "duration", "minutes"},
    "price": {"السعر", "price"},
    "type": {"النوع", "النشاط", "business type"},
}
TYPES = {"kids": "kids", "أطفال": "kids", "اطفال": "kids", "men": "men", "رجالي": "men", "رجال": "men",
         "women": "women", "حريمي": "women", "نسائي": "women", "ستات": "women"}


def run(upload, *, commit: bool, user, default_type: str) -> dict:
    rows = read_rows(upload, ALIASES)
    created = repriced = 0
    errors = []
    with transaction.atomic():
        for r in rows:
            name = r.get("name_ar", "")[:120]
            if not name:
                errors.append({"row": r["_row"], "code": "name_missing"})
                continue
            try:
                price = Decimal(r.get("price", "").replace(",", ".")) if r.get("price") else None
                minutes = int(float(r.get("duration") or 30))
            except (InvalidOperation, ValueError):
                errors.append({"row": r["_row"], "code": "number_invalid"})
                continue
            if (price is not None and price < 0) or not 5 <= minutes <= 600:
                errors.append({"row": r["_row"], "code": "number_invalid"})
                continue
            btype = TYPES.get(r.get("type", "").strip().lower(), default_type)
            cat_name = r.get("category", "")[:80] or "عام"
            cat = ServiceCategory.objects.filter(name_ar=cat_name, business_type=btype).first()
            if cat is None:
                cat = ServiceCategory.objects.create(name_ar=cat_name, business_type=btype)
            svc = Service.objects.filter(category=cat, name_ar=name).first()
            if svc is None:
                svc = Service.objects.create(category=cat, name_ar=name, name_en=r.get("name_en", "")[:120], duration_minutes=minutes)
                created += 1
                if price is not None:
                    set_price(svc, price=price, user=user)
            elif price is not None and price_on(svc, None, business_date()) != price:
                set_price(svc, price=price, user=user)
                repriced += 1
        if not commit:
            transaction.set_rollback(True)
    return {"rows": len(rows), "created": created, "repriced": repriced, "errors": errors[:100], "error_count": len(errors)}
