"""Customer login by phone + one-time code (D-003). Codes are hashed, expire in 5 minutes, allow 5 attempts,
and a phone can request at most 3 codes per 10 minutes (60 s apart)."""
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core import signing
from django.db import transaction
from django.utils import timezone

from apps.audit.services.log import record as audit
from apps.core.errors import DomainError
from apps.customers.models import Customer, OtpChallenge
from apps.notifications import whatsapp

MAX_ATTEMPTS = 5
WINDOW = timedelta(minutes=10)
PER_WINDOW = 3
COOLDOWN = timedelta(seconds=60)
TOKEN_SALT = "qassa.customer"
REG_SALT = "qassa.customer.register"


class OtpThrottled(DomainError):
    status_code = 429
    code = "otp_throttled"


def request_code(tenant, phone: str, *, lang="ar", ip=None) -> dict:
    now = timezone.now()
    recent = OtpChallenge.objects.filter(phone=phone, created_at__gte=now - WINDOW).order_by("-created_at")
    if recent.count() >= PER_WINDOW or (recent and now - recent[0].created_at < COOLDOWN):
        raise OtpThrottled(message="Too many codes requested; wait a little")
    code = f"{secrets.randbelow(10**6):06d}"
    text = (f"كود الدخول لـ {tenant.name}: {code}\nصالح لمدة 5 دقائق. لا تشاركه مع أحد." if lang == "ar"
            else f"Your {tenant.name} login code: {code}\nValid for 5 minutes. Do not share it.")
    channel = whatsapp.send_text(phone, text)  # raises whatsapp_unavailable when no channel can deliver
    OtpChallenge.objects.create(phone=phone, code_hash=make_password(code), channel=channel, ip=ip,
                                expires_at=now + timedelta(seconds=settings.QASSA["OTP_TTL_SECONDS"]))
    out = {"sent": True, "channel": channel, "expires_in": settings.QASSA["OTP_TTL_SECONDS"]}
    if settings.QASSA["OTP_ECHO"]:
        out["debug_code"] = code  # testing environments only (never production, enforced in settings)
    return out


def verify_code(tenant, phone: str, code: str) -> dict:
    # The attempt is committed before any error is raised: a wrong guess must always count.
    with transaction.atomic():
        ch = (OtpChallenge.objects.select_for_update().filter(phone=phone, consumed_at__isnull=True)
              .order_by("-created_at").first())
        if ch is None or ch.expires_at < timezone.now():
            error = DomainError(code="otp_expired", message="The code expired; request a new one")
        elif ch.attempts >= MAX_ATTEMPTS:
            error = OtpThrottled(message="Too many wrong attempts; request a new code")
        else:
            ch.attempts += 1
            ok = check_password(code.strip(), ch.code_hash)
            if ok:
                ch.consumed_at = timezone.now()
            ch.save(update_fields=["attempts", "consumed_at"])
            error = None if ok else DomainError(code="otp_invalid", message="Wrong code",
                                                details={"left": MAX_ATTEMPTS - ch.attempts})
    if error is not None:
        raise error
    customer = Customer.objects.filter(phone=phone, is_active=True).first()
    if customer is None:
        return {"new": True, "registration_token": signing.dumps({"t": tenant.id, "p": phone}, salt=REG_SALT)}
    audit("customer.login", tenant_id=tenant.id, obj=customer, data={"channel": ch.channel})
    return {"new": False, "token": issue_token(tenant, customer)}


def issue_token(tenant, customer) -> str:
    return signing.dumps({"t": tenant.id, "c": customer.id}, salt=TOKEN_SALT)


def read_token(token: str) -> dict | None:
    try:
        return signing.loads(token, salt=TOKEN_SALT, max_age=timedelta(days=settings.QASSA["CUSTOMER_TOKEN_DAYS"]))
    except signing.BadSignature:
        return None


def read_registration(token: str) -> dict:
    try:
        return signing.loads(token, salt=REG_SALT, max_age=timedelta(minutes=30))
    except signing.BadSignature:
        raise DomainError(code="registration_expired", message="Start again with your phone number")
