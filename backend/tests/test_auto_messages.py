"""Automatic WhatsApp service messages (D-012): booking confirmation, reschedule, reminder window, receipt;
opt-out and disconnected numbers are respected and never reported as sent."""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.booking.services.appointments import ItemSpec, create_appointment, reschedule, set_status
from apps.catalog.models import Service, ServiceCategory
from apps.catalog.services.pricing import set_price
from apps.core.services.infra import process_outbox
from apps.customers.models import Customer
from apps.notifications.auto import queue_reminders
from apps.notifications.models import MessagingSettings, WhatsAppChannel, WhatsAppMessage
from apps.staff.models import StaffBranch, StaffMember, StaffSkill
from apps.tenancy.context import tenant_context
from tests.test_whatsapp import FakeEvolution, gw  # noqa: F401  (fixture)

pytestmark = pytest.mark.django_db


@pytest.fixture
def salon(company_a, gw):  # noqa: F811
    t, _, b = company_a
    with tenant_context(t.id):
        from apps.tenancy.models import Branch
        Branch.objects.filter(id=b["HAW"].id).update(opens_at="00:00", closes_at="23:59")
        cat = ServiceCategory.objects.create(name_ar="قصات", business_type="kids")
        cut = Service.objects.create(category=cat, name_ar="قص", name_en="Cut", duration_minutes=30)
        set_price(cut, price="4.500")
        mona = StaffMember.objects.create(full_name_ar="منى")
        StaffBranch.objects.create(staff=mona, branch=b["HAW"])
        StaffSkill.objects.create(staff=mona, service=cut)
        cust = Customer.objects.create(full_name="سارة علي", phone="96555551111")
        ch = WhatsAppChannel.objects.create(instance_name="qassa-mykids", state="open")
    gw.instances["qassa-mykids"] = "open"
    return {"t": t, "b": Branch.unscoped.get(id=b["HAW"].id), "cut": cut, "mona": mona, "cust": cust, "gw": gw, "ch": ch}


def book(s, hours):
    with tenant_context(s["t"].id):
        start = (timezone.now() + timedelta(hours=hours)).replace(second=0, microsecond=0)
        start = start - timedelta(minutes=start.minute % 5)
        return create_appointment(branch=s["b"], starts_at=start, items=[ItemSpec(s["cut"].id, s["mona"].id)], customer_id=s["cust"].id)


def test_confirmation_then_reschedule_then_reminder_once(salon):
    a = book(salon, 30)
    process_outbox()
    assert len(salon["gw"].sent) == 1 and "اتأكد" in salon["gw"].sent[0][2] and salon["gw"].sent[0][1] == "96555551111"
    with tenant_context(salon["t"].id):
        a = reschedule(a, starts_at=a.starts_at - timedelta(hours=28), items=[ItemSpec(salon["cut"].id, salon["mona"].id)])
    process_outbox()
    assert "اتغيّر" in salon["gw"].sent[-1][2]
    assert queue_reminders() == 1 and queue_reminders() == 0   # within 3h window; queued once
    process_outbox()
    assert "تذكير" in salon["gw"].sent[-1][2] and len(salon["gw"].sent) == 3


def test_opt_out_disabled_and_cancelled_are_not_messaged(salon):
    with tenant_context(salon["t"].id):
        MessagingSettings.objects.create(booking_confirmation=False)
    book(salon, 30)
    process_outbox()
    assert salon["gw"].sent == []
    with tenant_context(salon["t"].id):
        MessagingSettings.objects.update(booking_confirmation=True)
        Customer.objects.filter(id=salon["cust"].id).update(whatsapp_opt_in=False)
    book(salon, 40)
    process_outbox()
    assert salon["gw"].sent == []
    with tenant_context(salon["t"].id):
        Customer.objects.filter(id=salon["cust"].id).update(whatsapp_opt_in=True)
        a = book(salon, 2)
        set_status(a, "cancelled", reason="x")
    queue_reminders()
    process_outbox()
    assert all("تذكير" not in m[2] for m in salon["gw"].sent)


def test_disconnected_number_is_logged_failed_not_retried(salon):
    with tenant_context(salon["t"].id):
        WhatsAppChannel.objects.update(state="close")
    book(salon, 30)
    assert process_outbox() == 1                    # handled (not left for retries)
    with tenant_context(salon["t"].id):
        m = WhatsAppMessage.objects.get(kind="booking.confirmed")
    assert m.status == "failed" and salon["gw"].sent == []


def test_settings_api(salon):
    from apps.identity.models import User
    from tests.conftest import client_for
    owner = User.objects.get(memberships__tenant=salon["t"], memberships__role__key="owner")
    c = client_for(owner, salon["t"])
    assert c.get("/api/v1/whatsapp/auto-settings").json() == {"booking_confirmation": True, "reminder": True, "reminder_hours": 3, "receipt": False,
                                                                 "feedback": False, "google_review_url": "", "winback": False,
                                                                 "winback_days": 45, "winback_coupon": ""}
    assert c.patch("/api/v1/whatsapp/auto-settings", {"receipt": True, "reminder_hours": 24}, format="json").json()["reminder_hours"] == 24
    assert c.patch("/api/v1/whatsapp/auto-settings", {"reminder_hours": 99}, format="json").status_code == 400
