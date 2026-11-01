"""Symmetric encryption for third-party credentials kept in the database (e.g. each salon's KlickPay client secret).

The key is derived from DJANGO_SECRET_KEY: rotating that key makes stored secrets unreadable, and they must be
entered again (decrypt() returns "" rather than failing)."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(f"qassa-secrets:{settings.SECRET_KEY}".encode()).digest()))


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode() if value else ""


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return ""
