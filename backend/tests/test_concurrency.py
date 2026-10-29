"""Real concurrent transactions (separate DB connections) — numbering and duplicate-event protection."""
import threading

import pytest
from django.db import connection

from apps.accounting.models import JournalEntry
from apps.accounting.services.posting import DuplicatePosting, Line, post_entry
from apps.tenancy.context import tenant_context

from .conftest import TODAY, make_company


def run_parallel(n, fn):
    errors, results, barrier = [], [], threading.Barrier(n)

    def worker(i):
        try:
            barrier.wait()
            results.append(fn(i))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            connection.close()
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    return results, errors


@pytest.mark.django_db(transaction=True)
def test_parallel_postings_get_unique_gapless_numbers():
    t, e, _ = make_company("Concurrent", "owner@conc.test")

    def post(i):
        with tenant_context(t.id):
            return post_entry(legal_entity_id=e.id, entry_date=TODAY, kind="auto", source_type="test", source_id=str(i),
                              event_type="x", lines=[Line("CASH_DRAWER", debit="1"), Line("SERVICE_REVENUE", credit="1")]).number
    numbers, errors = run_parallel(8, post)
    assert not errors
    assert sorted(int(n.rsplit("-", 1)[1]) for n in numbers) == list(range(1, 9))


@pytest.mark.django_db(transaction=True)
def test_same_event_posted_concurrently_only_once():
    t, e, _ = make_company("Concurrent2", "owner@conc2.test")

    def post(_):
        with tenant_context(t.id):
            return post_entry(legal_entity_id=e.id, entry_date=TODAY, kind="auto", source_type="pos.payment",
                              source_id="same", event_type="captured",
                              lines=[Line("CASH_DRAWER", debit="5"), Line("AR_CUSTOMERS", credit="5")]).id
    ok, errors = run_parallel(6, post)
    assert len(ok) == 1 and len(errors) == 5 and all(isinstance(x, DuplicatePosting) for x in errors)
    with tenant_context(t.id):
        assert JournalEntry.objects.filter(source_id="same").count() == 1


@pytest.mark.django_db(transaction=True)
def test_same_offline_receipt_synced_twice_at_once_makes_one_invoice():
    """A tablet retrying while the first sync is still running must not sell twice."""
    import uuid
    from datetime import timedelta

    from django.utils import timezone

    from apps.catalog.models import Service, ServiceCategory
    from apps.catalog.services.pricing import set_price
    from apps.identity.models import User
    from apps.pos.models import CashSession, Invoice, OfflineSale
    from apps.pos.services import offline
    from apps.tenancy.models import Membership
    t, e, b = make_company("Offline Co", "owner@off.test")
    owner = User.objects.get(email="owner@off.test")
    m = Membership.objects.select_related("role").get(user=owner, tenant=t)
    with tenant_context(t.id):
        cat = ServiceCategory.objects.create(name_ar="قصات", business_type="kids")
        cut = Service.objects.create(category=cat, name_ar="قص", duration_minutes=30)
        set_price(cut, price="5.000")
        CashSession.objects.create(branch=b["HAW"], opened_by=owner, opening_float=10)
        CashSession.objects.update(opened_at=timezone.now() - timedelta(hours=1))
        dev = offline.register_device(branch=b["HAW"], name="tab", user=owner)
    payload = {"uuid": str(uuid.uuid4()), "seq": 1, "created_at": (timezone.now() - timedelta(minutes=5)).isoformat(), "total": "5.000",
               "lines": [{"service_id": cut.id, "unit_price": "5.000"}], "payments": [{"method": "cash", "amount": "5.000"}]}
    item = {"payload": payload, "signature": offline.sign(dev.secret, payload)}

    def send(_):
        with tenant_context(t.id):
            return offline.receive(dev, item, user=owner, membership=m).invoice_id
    invoices, errors = run_parallel(4, send)
    assert not errors and len(set(invoices)) == 1
    with tenant_context(t.id):
        assert Invoice.objects.count() == 1 and OfflineSale.objects.count() == 1
