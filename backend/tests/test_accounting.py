"""Ledger rules: balanced, open period, single posting per event, immutable once posted, reversal, trial balance."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, connection, transaction

from apps.accounting.models import Account, FiscalPeriod, JournalEntry, JournalLine
from apps.accounting.services.ledger import close_period, reopen_period, trial_balance
from apps.accounting.services.posting import DuplicatePosting, Line, post_entry, reverse_entry
from apps.core.errors import DomainError
from apps.tenancy.context import tenant_context

from .conftest import TODAY, add_member


def acc(entity, role):
    from apps.accounting.models import AccountRoleMapping
    return AccountRoleMapping.objects.get(legal_entity=entity, role=role).account


@pytest.fixture
def ctx(company_a):
    t, e, b = company_a
    with tenant_context(t.id):
        yield t, e, b


def test_balanced_entry_posts_with_number(ctx):
    t, e, b = ctx
    je = post_entry(legal_entity_id=e.id, entry_date=TODAY, branch_id=b["HAW"].id, kind="auto",
                    source_type="pos.invoice", source_id="1", event_type="approved",
                    lines=[Line("AR_CUSTOMERS", debit="5"), Line("SERVICE_REVENUE", credit="5.000")])
    assert je.status == "posted" and je.number.startswith(f"JE-{TODAY.year}-")
    assert [l.debit for l in je.lines.order_by("line_no")] == [Decimal("5.000"), Decimal("0.000")]


def test_unbalanced_rejected(ctx):
    _, e, _ = ctx
    with pytest.raises(DomainError) as ei:
        post_entry(legal_entity_id=e.id, entry_date=TODAY,
                   lines=[Line(acc(e, "CASH_DRAWER"), debit="5"), Line(acc(e, "SERVICE_REVENUE"), credit="4.999")])
    assert ei.value.code == "je_unbalanced"
    assert JournalEntry.objects.count() == 0


def test_float_amounts_rejected(ctx):
    _, e, _ = ctx
    with pytest.raises(ValueError):
        post_entry(legal_entity_id=e.id, entry_date=TODAY,
                   lines=[Line(acc(e, "CASH_DRAWER"), debit=0.1), Line(acc(e, "SERVICE_REVENUE"), credit=0.1)])


def test_line_must_be_one_sided(ctx):
    _, e, _ = ctx
    with pytest.raises(DomainError):
        post_entry(legal_entity_id=e.id, entry_date=TODAY,
                   lines=[Line(acc(e, "CASH_DRAWER"), debit="5", credit="5"), Line(acc(e, "SERVICE_REVENUE"), credit="0")])


def test_manual_entry_cannot_hit_control_account(ctx):
    _, e, _ = ctx
    with pytest.raises(DomainError) as ei:
        post_entry(legal_entity_id=e.id, entry_date=TODAY, kind="manual",
                   lines=[Line(acc(e, "AR_CUSTOMERS"), debit="5"), Line(acc(e, "SERVICE_REVENUE"), credit="5")])
    assert ei.value.code == "je_control_account"


def test_header_account_not_postable(ctx):
    _, e, _ = ctx
    header = Account.objects.get(legal_entity=e, code="1")
    with pytest.raises(DomainError):
        post_entry(legal_entity_id=e.id, entry_date=TODAY,
                   lines=[Line(header, debit="1"), Line(acc(e, "SERVICE_REVENUE"), credit="1")])


def test_same_event_cannot_post_twice(ctx):
    _, e, _ = ctx
    kw = dict(legal_entity_id=e.id, entry_date=TODAY, kind="auto", source_type="pos.payment", source_id="77",
              event_type="captured", lines=[Line("CASH_DRAWER", debit="5"), Line("AR_CUSTOMERS", credit="5")])
    post_entry(**kw)
    with pytest.raises(DuplicatePosting):
        post_entry(**kw)
    assert JournalEntry.objects.filter(source_id="77").count() == 1


def test_closed_period_rejects_posting_and_reopen_requires_reason(ctx):
    t, e, _ = ctx
    owner = t.memberships.first().user
    period = FiscalPeriod.objects.get(legal_entity=e, start_date__lte=TODAY, end_date__gte=TODAY)
    close_period(period, owner)
    with pytest.raises(DomainError) as ei:
        post_entry(legal_entity_id=e.id, entry_date=TODAY,
                   lines=[Line(acc(e, "CASH_DRAWER"), debit="1"), Line(acc(e, "SERVICE_REVENUE"), credit="1")])
    assert ei.value.code == "period_closed"
    with pytest.raises(DomainError):
        reopen_period(period, owner, "")
    reopen_period(period, owner, "late supplier bill")
    post_entry(legal_entity_id=e.id, entry_date=TODAY,
               lines=[Line(acc(e, "CASH_DRAWER"), debit="1"), Line(acc(e, "SERVICE_REVENUE"), credit="1")])


def test_date_without_period_rejected(ctx):
    _, e, _ = ctx
    with pytest.raises(DomainError) as ei:
        post_entry(legal_entity_id=e.id, entry_date=TODAY.replace(year=TODAY.year - 5),
                   lines=[Line(acc(e, "CASH_DRAWER"), debit="1"), Line(acc(e, "SERVICE_REVENUE"), credit="1")])
    assert ei.value.code == "no_fiscal_period"


def test_posted_entry_is_immutable_in_database(ctx):
    _, e, _ = ctx
    je = post_entry(legal_entity_id=e.id, entry_date=TODAY,
                    lines=[Line(acc(e, "CASH_DRAWER"), debit="5"), Line(acc(e, "SERVICE_REVENUE"), credit="5")])
    with pytest.raises(Exception):
        with transaction.atomic():
            JournalLine.objects.filter(entry=je).update(debit=Decimal("6"))
    with pytest.raises(Exception):
        with transaction.atomic():
            JournalEntry.objects.filter(pk=je.pk).update(memo="edited")
    with pytest.raises(Exception):
        with transaction.atomic():
            JournalLine.objects.filter(entry=je).delete()


def test_database_rejects_unbalanced_posted_entry_inserted_directly(ctx):
    """Bypass the service: insert a posted entry with one-sided lines; the deferred trigger must reject it."""
    t, e, _ = ctx
    period = FiscalPeriod.objects.get(legal_entity=e, start_date__lte=TODAY, end_date__gte=TODAY)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            je = JournalEntry.objects.create(legal_entity=e, period=period, entry_date=TODAY)
            JournalLine.objects.create(entry=je, line_no=1, account=acc(e, "CASH_DRAWER"), debit=Decimal("5"))
            JournalLine.objects.create(entry=je, line_no=2, account=acc(e, "SERVICE_REVENUE"), credit=Decimal("4"))
            JournalEntry.objects.filter(pk=je.pk).update(status="posted")
            with connection.cursor() as cur:
                cur.execute("SET CONSTRAINTS ALL IMMEDIATE")  # force the deferred check inside the test transaction


def test_reversal_mirrors_lines_once(ctx):
    t, e, _ = ctx
    user = add_member(t, "fm@mykids.test", "finance_manager")
    je = post_entry(legal_entity_id=e.id, entry_date=TODAY,
                    lines=[Line(acc(e, "RENT"), debit="300"), Line(acc(e, "BANK"), credit="300")])
    rev = reverse_entry(je, on=TODAY, user=user, reason="wrong month")
    assert rev.reversal_of_id == je.id
    assert [(l.debit, l.credit) for l in rev.lines.order_by("line_no")] == [(0, 300), (300, 0)]
    with pytest.raises(DomainError):
        reverse_entry(je, on=TODAY, user=user, reason="again")
    with pytest.raises(DomainError):
        reverse_entry(rev, on=TODAY, user=user, reason="reverse the reversal")
    tb = trial_balance(e.id, TODAY - timedelta(days=1), TODAY)
    assert all(Decimal(r["closing"]) == 0 for r in tb["rows"])


def test_trial_balance_balances_and_filters_branch(ctx):
    _, e, b = ctx
    post_entry(legal_entity_id=e.id, entry_date=TODAY, kind="auto", branch_id=b["HAW"].id,
               source_type="pos.invoice", source_id="10", event_type="approved",
               lines=[Line("AR_CUSTOMERS", debit="20"), Line("SERVICE_REVENUE", credit="20")])
    post_entry(legal_entity_id=e.id, entry_date=TODAY, kind="auto", branch_id=b["HAW"].id,
               source_type="pos.payment", source_id="11", event_type="captured",
               lines=[Line("CASH_DRAWER", debit="5"), Line("KNET_CLEARING", debit="15"), Line("AR_CUSTOMERS", credit="20")])
    post_entry(legal_entity_id=e.id, entry_date=TODAY, kind="auto", branch_id=b["SAL"].id,
               source_type="pos.invoice", source_id="12", event_type="approved",
               lines=[Line("AR_CUSTOMERS", debit="7"), Line("SERVICE_REVENUE", credit="7")])
    tb = trial_balance(e.id, TODAY.replace(day=1), TODAY)
    assert tb["balanced"] and tb["total_debit"] == Decimal("47.000")
    rows = {r["code"]: r for r in tb["rows"]}
    assert rows["4101"]["closing"] == Decimal("-27.000")  # credit balance
    assert rows["1110"]["closing"] == Decimal("7.000")
    haw = {r["code"]: r for r in trial_balance(e.id, TODAY.replace(day=1), TODAY, b["HAW"].id)["rows"]}
    assert haw["4101"]["closing"] == Decimal("-20.000") and haw["1110"]["closing"] == 0  # AR settled in Hawally


def test_numbering_is_sequential_without_gaps(ctx):
    _, e, _ = ctx
    nums = [post_entry(legal_entity_id=e.id, entry_date=TODAY,
                       lines=[Line(acc(e, "CASH_DRAWER"), debit="1"), Line(acc(e, "SERVICE_REVENUE"), credit="1")]).number
            for _ in range(3)]
    assert [int(n.rsplit("-", 1)[1]) for n in nums] == [1, 2, 3]
