import re

from apps.core.errors import DomainError


def normalize_phone(raw: str) -> str:
    """Kuwait local 8-digit numbers get 965; other numbers must already carry a country code."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 8:
        digits = "965" + digits
    if not 10 <= len(digits) <= 15 or (digits.startswith("965") and len(digits) != 11):
        raise DomainError(code="phone_invalid", message="Invalid phone number")
    return digits
