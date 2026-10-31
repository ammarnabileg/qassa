"""Visit ratings over WhatsApp (link → public page → salon list) and the 'we miss you' message (marketing opt-in only)."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.core.dates import business_date
from apps.core.models import OutboxEvent
from apps.core.services.infra import process_outbox
from apps.customers.models import Customer
from apps.loyalty.models import Coupon
from apps.notifications.auto import queue_winback
from apps.notifications.models import Feedback, MessagingSettings, WhatsAppChannel
from apps.pos.models import Invoice
from apps.tenancy.context import tenant_context
from rest_framework.test import APIClient

from tests.conftest import client_for
from tests.test_phase3_operations import checkout, open_drawer, salon  # noqa: F401
from tests.test_whatsapp import FakeEvolution, gw  # noqa: F401

pytestmark = pytest.mark.django_db


@pytest.fixture
def s(salon, gw):  # noqa: F811
    with tenant_context(salon["t"].id):
        WhatsAppChannel.objects.create(instance_name="qassa-fb", state="open")
        MessagingSettings.objects.create(feedback=True, google_review_url="https://g.page/r/test/review", winback=True, winback_days=30)
        salon["cust"] = Customer.objects.create(full_name="سارة علي", phone="96555551111", marketing_opt_in=True)
    gw.instances["qassa-fb"] = "open"
    salon["gw"] = gw
    return salon


def pay(s, key="k1"):
    open_drawer(s) if key == "k1" else None
    r = checkout(s, s["cashier"], [{"service_id": s["wash"].id}], [{"method": "cash", "amount": "15.000"}], customer_id=s["cust"].id, key=key)
    assert r.status_code == 201, r.content
    return r.json()


def due_now():
    OutboxEvent.objects.filter(status="pending").update(available_at=timezone.now())


def test_rating_link_sent_later_rated_once_and_listed(s):
    pay(s)
    process_outbox()
    assert not any("قيّمنا" in m[2] for m in s["gw"].sent)          # not straight away
    due_now()
    process_outbox()
    msg = next(m[2] for m in s["gw"].sent if "قيّمنا" in m[2])
    token = msg.rsplit("/rate/", 1)[1].strip()
    anon = APIClient()
    assert anon.get(f"/api/v1/public/feedback/{token}").json()["rating"] is None
    r = anon.post(f"/api/v1/public/feedback/{token}", {"rating": 5, "comment": "ممتاز"}, format="json")
    assert r.status_code == 200 and r.json()["review_url"] == "https://g.page/r/test/review"
    again = anon.post(f"/api/v1/public/feedback/{token}", {"rating": 1}, format="json")
    assert again.json()["error"]["code"] == "feedback_already_rated"
    assert anon.get("/api/v1/public/feedback/nope").status_code == 404
    lst = client_for(s["manager"], s["t"]).get("/api/v1/feedback").json()
    assert lst["rated"] == 1 and lst["average"] == 5 and lst["items"][0]["comment"] == "ممتاز"


def test_low_rating_gets_no_review_link(s):
    pay(s)
    due_now()
    process_outbox()
    with tenant_context(s["t"].id):
        token = Feedback.objects.get().token
    r = APIClient().post(f"/api/v1/public/feedback/{token}", {"rating": 2}, format="json").json()
    assert r["review_url"] == ""
    assert client_for(s["manager"], s["t"]).get("/api/v1/feedback").json()["low"] == 1


def test_winback_once_per_absence_with_coupon_and_only_to_opted_in(s):
    pay(s)
    today = business_date()
    later = today + timedelta(days=31)              # invoices are immutable, so move the clock instead
    with tenant_context(s["t"].id):
        Coupon.objects.create(code="BACK10", kind="percent", value=10, valid_from=today, valid_to=today + timedelta(days=60))
        MessagingSettings.objects.update(winback_coupon="back10")
    assert queue_winback(today + timedelta(days=29)) == 0          # not away long enough
    assert queue_winback(later) == 1 and queue_winback(later) == 0
    process_outbox()
    msg = s["gw"].sent[-1][2]
    assert "وحشتنا" in msg and "BACK10" in msg and "10%" in msg
    pay(s, key="k2")                                                # came back → a later absence counts again
    assert queue_winback(later) == 1
    with tenant_context(s["t"].id):
        Customer.objects.update(marketing_opt_in=False)
    pay(s, key="k3")
    assert queue_winback(later) == 0                                # no marketing consent, no message
    assert queue_winback(today + timedelta(days=200)) == 0          # long-gone customers aren't swept up when it's switched on


def test_rebook_reminder_when_due_unless_back_or_booked(s):
    from apps.catalog.models import Service
    from apps.notifications.auto import queue_rebook
    with tenant_context(s["t"].id):
        Service.objects.filter(id=s["wash"].id).update(rebook_days=21)
        MessagingSettings.objects.update(rebook=True)
    pay(s)
    today = business_date()
    assert queue_rebook(today + timedelta(days=20)) == 0
    assert queue_rebook(today + timedelta(days=21)) == 1 and queue_rebook(today + timedelta(days=22)) == 0   # once
    process_outbox()
    assert "21" in s["gw"].sent[-1][2] and "غسيل" in s["gw"].sent[-1][2]
    pay(s, key="k2")
    checkout(s, s["cashier"], [{"service_id": s["cut"].id}], [{"method": "cash", "amount": "5.000"}], customer_id=s["cust"].id, key="k3")
    assert queue_rebook(today + timedelta(days=21)) == 0      # the wash visit was followed by another visit


def test_upsell_and_rebook_fields(s):
    c = client_for(s["owner"], s["t"])
    r = c.patch(f"/api/v1/catalog/services/{s['cut'].id}", {"upsell": s["wash"].id, "rebook_days": 21}, format="json")
    assert r.status_code == 200 and r.json()["upsell"] == s["wash"].id
    assert c.patch(f"/api/v1/catalog/services/{s['cut'].id}", {"upsell": s["cut"].id}, format="json").status_code == 400
    assert c.patch(f"/api/v1/catalog/services/{s['cut'].id}", {"rebook_days": 3}, format="json").status_code == 400


def _file(name, content: bytes):
    from django.core.files.uploadedfile import SimpleUploadedFile
    return SimpleUploadedFile(name, content)


def test_import_customers_preview_then_commit_and_match(s):
    c = client_for(s["owner"], s["t"])
    csv = "الاسم,الموبايل,الطفل,ميلاد الطفل\nأحمد سالم,55512345,يوسف,2019-03-02\nأحمد سالم,55512345,ليلى,\nبدون رقم,123,,\nسارة علي,96555551111,مريم,31/12/2020\n"
    pre = c.post("/api/v1/import/customers", {"file": _file("c.csv", csv.encode())}, format="multipart").json()
    assert pre["committed"] is False and pre["created"] == 1 and pre["matched"] == 1 and pre["error_count"] == 1
    with tenant_context(s["t"].id):
        assert not Customer.objects.filter(phone="96555512345").exists()        # preview wrote nothing
    done = c.post("/api/v1/import/customers", {"file": _file("c.csv", csv.encode()), "commit": "true"}, format="multipart").json()
    assert done["committed"] and done["children"] == 3
    with tenant_context(s["t"].id):
        a = Customer.objects.get(phone="96555512345")
        assert sorted(b.full_name for b in a.beneficiaries.all()) == ["ليلى", "يوسف"] and not a.marketing_opt_in
        assert Customer.objects.get(phone="96555551111").full_name == "سارة علي"   # existing customer not renamed
    again = c.post("/api/v1/import/customers", {"file": _file("c.csv", csv.encode()), "commit": "true"}, format="multipart").json()
    assert again["created"] == 0 and again["children"] == 0                       # re-running doesn't duplicate


def test_import_services_xlsx_creates_and_reprices(s):
    import io
    from openpyxl import Workbook
    from apps.catalog.models import Service
    from apps.catalog.services.pricing import price_on
    wb = Workbook(); ws = wb.active
    ws.append(["الخدمة", "القسم", "المدة", "السعر"])
    ws.append(["قص أطفال جديد", "قصات", 25, 4.5])
    ws.append(["", "قصات", 10, 1])
    buf = io.BytesIO(); wb.save(buf)
    c = client_for(s["owner"], s["t"])
    r = c.post("/api/v1/import/services", {"file": _file("m.xlsx", buf.getvalue()), "commit": "1"}, format="multipart").json()
    assert r["created"] == 1 and r["error_count"] == 1
    with tenant_context(s["t"].id):
        svc = Service.objects.get(name_ar="قص أطفال جديد")
        assert svc.duration_minutes == 25 and price_on(svc, None, business_date()) == Decimal("4.500")
    assert client_for(s["cashier"], s["t"]).post("/api/v1/import/services", {"file": _file("m.xlsx", buf.getvalue())},
                                                  format="multipart").status_code == 403
