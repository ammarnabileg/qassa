"""Visit ratings over WhatsApp (link → public page → salon list) and the 'we miss you' message (marketing opt-in only)."""
from datetime import timedelta

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
