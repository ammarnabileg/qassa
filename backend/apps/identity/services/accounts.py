"""Staff invitations and password reset. Links use Django's token generator, which stops working as soon as the
password changes (one use). Delivery: email if SMTP is configured, else the platform WhatsApp number, else the
link is returned to the administrator to pass on — never silently dropped."""
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from apps.core.errors import DomainError
from apps.identity.models import User
from apps.identity.services import second_factor
from apps.notifications import whatsapp


def link_for(user, purpose: str) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return f"{settings.QASSA['PUBLIC_ADMIN_URL'].rstrip('/')}/set-password?uid={uid}&token={token}&p={purpose}"


def deliver(user, purpose: str) -> dict:
    """Send an invitation / reset link. Returns how it went out; includes the link only when nothing could send it."""
    link = link_for(user, purpose)
    ar = user.preferred_language == "ar"
    subject = ("دعوة لقصّة POS" if purpose == "invite" else "تغيير كلمة المرور — قصّة POS") if ar else \
        ("Your Qassa POS invitation" if purpose == "invite" else "Reset your Qassa POS password")
    body = (f"اضغط الرابط لتعيين كلمة المرور (صالح مرة واحدة):\n{link}" if ar
            else f"Open this link to set your password (single use):\n{link}")
    if settings.QASSA["EMAIL_CONFIGURED"]:
        send_mail(subject, body, None, [user.email])
        return {"channel": "email"}
    if user.phone and whatsapp.platform_available():
        try:
            whatsapp.send_platform_text(user.phone, body, kind=f"staff_{purpose}")
            return {"channel": "whatsapp", "to": second_factor.mask(user.phone)}
        except DomainError:
            pass
    return {"channel": "manual", "link": link}


def set_password(uidb64: str, token: str, password: str) -> User:
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uidb64)), is_active=True)
    except (User.DoesNotExist, ValueError, TypeError, OverflowError):
        raise DomainError(code="link_invalid")
    if not default_token_generator.check_token(user, token):
        raise DomainError(code="link_invalid", message="The link is invalid, used or expired")
    try:
        validate_password(password, user)
    except ValidationError as e:
        raise DomainError(code="password_weak", details={"reasons": e.messages})
    user.set_password(password)
    user.save(update_fields=["password"])
    second_factor.revoke_all(user)  # a new password forgets remembered devices
    return user
