"""Money helpers. KWD has 3 decimal places (fils). Floats are never accepted."""
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

KWD_PLACES = Decimal("0.001")
COST_PLACES = Decimal("0.000001")
QTY_PLACES = Decimal("0.0001")


class MoneyError(ValueError):
    pass


def _to_decimal(value) -> Decimal:
    if isinstance(value, float):
        raise MoneyError("Floats are not allowed for money; pass str or Decimal.")
    if isinstance(value, bool):
        raise MoneyError("Booleans are not money.")
    try:
        return Decimal(value) if not isinstance(value, Decimal) else value
    except (InvalidOperation, TypeError) as exc:
        raise MoneyError(f"Invalid amount: {value!r}") from exc


def money(value) -> Decimal:
    """Round to 3 decimals (fils), half-up."""
    d = _to_decimal(value)
    if not d.is_finite():
        raise MoneyError("Amount must be finite.")
    return d.quantize(KWD_PLACES, rounding=ROUND_HALF_UP)


def cost(value) -> Decimal:
    return _to_decimal(value).quantize(COST_PLACES, rounding=ROUND_HALF_UP)


def allocate(total, weights) -> list[Decimal]:
    """Split `total` proportionally to `weights`; rounding remainder goes to the last item so the sum is exact."""
    total = money(total)
    weights = [_to_decimal(w) for w in weights]
    if not weights:
        raise MoneyError("No weights to allocate to.")
    wsum = sum(weights)
    if wsum <= 0:
        raise MoneyError("Weights must sum to a positive number.")
    parts = [money(total * w / wsum) for w in weights[:-1]]
    parts.append(total - sum(parts, Decimal("0")))
    return parts
