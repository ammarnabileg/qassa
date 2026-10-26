"""Second factor by WhatsApp (platform number) and trusted devices ("remember this device")."""
import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone

from apps.core.errors import DomainError
from apps.identity.models import StaffOtp, TrustedDevice
from apps.notifications import whatsapp

COOKIE = "qassa_td"
TTL = timedelta(minutes=5)
MAX_ATTEMPTS = 5


class Throttled(DomainError):
    status_code = 429
    code = "mfa_throttled"


def whatsapp_available(user) -> bool:
    return bool(user.phone) and whatsapp.platform_available()


def mask(phone: str) -> str:
    return f"+{phone[:3]} •••• {phone[-3:]}" if len(phone) > 6 else "•••"


def send_code(user) -> dict:
    if not user.phone:
        raise DomainError(code="mfa_no_phone", message="No phone number on this account; ask an administrator")
    now = timezone.now()
    recent = StaffOtp.objects.filter(user=user, created_at__gte=now - timedelta(minutes=10)).order_by("-created_at")
    if recent.count() >= 3 or (recent and now - recent[0].created_at < timedelta(seconds=60)):
        raise Throttled(message="Too many codes requested; wait a little")
    code = f"{secrets.randbelow(10**6):06d}"
    lang = user.preferred_language
    text = (f"كود دخول قصّة POS: {code}\nصالح 5 دقائق. لو مش انت اللي بتدخل، غيّر كلمة السر فورًا." if lang == "ar"
            else f"Qassa POS sign-in code: {code}\nValid for 5 minutes. If this wasn't you, change your password now.")
    whatsapp.send_platform_text(user.phone, text, kind="staff_mfa")
    StaffOtp.objects.create(user=user, code_hash=make_password(code), expires_at=now + TTL)
    out = {"sent": True, "to": mask(user.phone)}
    if settings.QASSA["OTP_ECHO"]:
        out["debug_code"] = code
    return out


def verify_code(user, code: str) -> bool:
    """True if the code is right. Attempts are committed before returning, so wrong guesses always count."""
    with transaction.atomic():
        ch = StaffOtp.objects.select_for_update().filter(user=user, consumed_at__isnull=True).order_by("-created_at").first()
        if ch is None or ch.expires_at < timezone.now():
            return False
        if ch.attempts >= MAX_ATTEMPTS:
            raise_later = True
        else:
            raise_later = False
            ch.attempts += 1
            ok = check_password(code.strip(), ch.code_hash)
            if ok:
                ch.consumed_at = timezone.now()
            ch.save(update_fields=["attempts", "consumed_at"])
    if raise_later:
        raise Throttled(message="Too many wrong attempts; request a new code")
    return ok


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def remember(response, user, user_agent: str):
    raw = secrets.token_urlsafe(32)
    days = settings.QASSA["TRUSTED_DEVICE_DAYS"]
    TrustedDevice.objects.create(user=user, token_hash=_hash(raw), label=user_agent[:200],
                                 expires_at=timezone.now() + timedelta(days=days))
    response.set_cookie(COOKIE, f"{user.id}:{raw}", max_age=days * 86400, httponly=True,
                        secure=not settings.DEBUG, samesite="Lax")


def trusted(request, user) -> bool:
    value = request.COOKIES.get(COOKIE, "")
    uid, _, raw = value.partition(":")
    if not raw or uid != str(user.id):
        return False
    dev = TrustedDevice.objects.filter(user=user, token_hash=_hash(raw), revoked_at__isnull=True,
                                       expires_at__gt=timezone.now()).first()
    if dev is None:
        return False
    dev.last_used_at = timezone.now()
    dev.save(update_fields=["last_used_at"])
    return True


def revoke_all(user):
    TrustedDevice.objects.filter(user=user, revoked_at__isnull=True).update(revoked_at=timezone.now())
