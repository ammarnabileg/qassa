"""Bring customers (and their children) over from a spreadsheet. Existing phone numbers are matched, never duplicated;
imported customers get no marketing consent (it must be given by the customer)."""
from datetime import date

from django.db import transaction

from apps.core.errors import DomainError
from apps.core.services.tabular import read_rows
from apps.customers.models import Beneficiary, Customer
from apps.customers.services.phone import normalize_phone

ALIASES = {
    "name": {"الاسم", "اسم العميل", "ولي الأمر", "اسم ولي الأمر", "customer", "full name", "guardian"},
    "phone": {"الموبايل", "الهاتف", "التليفون", "رقم الموبايل", "mobile", "phone number", "tel"},
    "child": {"الطفل", "اسم الطفل", "child name", "kid"},
    "child_birth": {"ميلاد الطفل", "تاريخ ميلاد الطفل", "birth date", "child birth date", "birthday"},
    "email": {"الإيميل", "البريد", "e-mail"},
    "notes": {"ملاحظات", "note"},
}


def _date(v):
    if not v:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            from datetime import datetime
            d = datetime.strptime(v[:10], fmt).date()
            return d if date(1900, 1, 1) < d <= date.today() else None
        except ValueError:
            continue
    return None


def run(upload, *, commit: bool) -> dict:
    rows = read_rows(upload, ALIASES)
    created = updated = kids = 0
    errors = []
    seen = {}
    with transaction.atomic():
        for r in rows:
            try:
                phone = normalize_phone(r.get("phone", ""))
            except DomainError:
                errors.append({"row": r["_row"], "code": "phone_invalid"})
                continue
            name = r.get("name", "")[:120] or r.get("child", "")[:120]
            if not name:
                errors.append({"row": r["_row"], "code": "name_missing"})
                continue
            if r.get("child_birth") and _date(r["child_birth"]) is None:
                errors.append({"row": r["_row"], "code": "date_ignored"})   # imported without the date
            c = seen.get(phone) or Customer.objects.filter(phone=phone).first()
            if c is None:
                c = Customer(full_name=name, phone=phone, email=r.get("email", "")[:254] if "@" in r.get("email", "") else "",
                             notes=r.get("notes", ""))
                if commit:
                    c.save()
                created += 1
            elif phone not in seen:
                updated += 1
            seen[phone] = c
            child = r.get("child", "")[:120]
            if child and r.get("name"):
                exists = c.pk and Beneficiary.objects.filter(customer=c, full_name=child).exists()
                if not exists:
                    if commit:
                        Beneficiary.objects.create(customer=c, full_name=child, relation="child", birth_date=_date(r.get("child_birth", "")))
                    kids += 1
        if not commit:
            transaction.set_rollback(True)
    return {"rows": len(rows), "created": created, "matched": updated, "children": kids, "errors": errors[:100], "error_count": len(errors)}
