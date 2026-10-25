from decimal import Decimal

import pytest

from apps.core.money import MoneyError, allocate, money


def test_rounds_half_up_to_fils():
    assert money("1.0005") == Decimal("1.001")
    assert money("2.0004") == Decimal("2.000")
    assert money(Decimal("-1.0005")) == Decimal("-1.001")


def test_floats_and_bools_rejected():
    with pytest.raises(MoneyError):
        money(1.1)
    with pytest.raises(MoneyError):
        money(True)


def test_allocation_sums_exactly():
    parts = allocate("10.000", [1, 1, 1])
    assert parts == [Decimal("3.333"), Decimal("3.333"), Decimal("3.334")]
    assert sum(parts) == Decimal("10.000")
    assert sum(allocate("30", ["4.5", "6", "2.5"])) == Decimal("30.000")
