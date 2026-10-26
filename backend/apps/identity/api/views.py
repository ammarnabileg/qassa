"""Session authentication for the web apps, with TOTP for roles that require it.

Login is two-step when MFA is required: password → session marked `mfa_pending` → /auth/mfa/verify.
Until verified, the session is not authenticated as far as the API is concerned.
"""
from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django_otp import login as otp_login
from django_otp.plugins.otp_totp.models import TOTPDevice
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.services.log import record as audit
from apps.identity.services import second_factor as f2
from apps.tenancy.models import Membership

PENDING = "mfa_pending_user_id"


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)


class MfaSerializer(serializers.Serializer):
    token = serializers.RegexField(r"^\d{6}$")
    method = serializers.ChoiceField(choices=["totp", "whatsapp"], default="totp")
    remember = serializers.BooleanField(default=False)  # trust this browser for TRUSTED_DEVICE_DAYS


def me_payload(user):
    ms = Membership.objects.select_related("tenant", "role").filter(user=user, is_active=True)
    return {
        "id": user.id, "email": user.email, "full_name": user.full_name, "language": user.preferred_language,
        "is_platform_staff": user.is_platform_staff, "mfa_required": user.mfa_required,
        "memberships": [{"tenant_id": m.tenant_id, "tenant_name": m.tenant.name, "tenant_status": m.tenant.status,
                         "tenant_business_type": m.tenant.default_business_type,
                         "role": m.role.key, "role_name": {"ar": m.role.name_ar, "en": m.role.name_en},
                         "permissions": sorted(m.role.permissions), "all_branches": m.all_branches,
                         "branch_ids": sorted(m.branch_ids() or [])} for m in ms],
    }


MembershipOut = inline_serializer("MembershipOut", {
    "tenant_id": serializers.IntegerField(), "tenant_name": serializers.CharField(), "tenant_status": serializers.CharField(),
    "tenant_business_type": serializers.CharField(),
    "role": serializers.CharField(), "role_name": serializers.DictField(), "permissions": serializers.ListField(child=serializers.CharField()),
    "all_branches": serializers.BooleanField(), "branch_ids": serializers.ListField(child=serializers.IntegerField())})
MeOut = inline_serializer("MeOut", {
    "id": serializers.IntegerField(), "email": serializers.EmailField(), "full_name": serializers.CharField(),
    "language": serializers.CharField(), "is_platform_staff": serializers.BooleanField(), "mfa_required": serializers.BooleanField(),
    "memberships": MembershipOut})
MfaStep = inline_serializer("MfaStep", {"mfa": serializers.ChoiceField(choices=["setup", "verify"]),
                                        "methods": serializers.ListField(child=serializers.CharField()),
                                        "phone": serializers.CharField()})


class CsrfView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=inline_serializer("Csrf", {"csrfToken": serializers.CharField()}))
    def get(self, request):
        return Response({"csrfToken": get_token(request)})


class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "login"
    from rest_framework.throttling import ScopedRateThrottle
    throttle_classes = [ScopedRateThrottle]

    @extend_schema(request=LoginSerializer, responses={200: MeOut, 401: None}, description="Returns MeOut, or MfaStep when MFA is required.")
    def post(self, request):
        s = LoginSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = authenticate(request, email=s.validated_data["email"].lower(), password=s.validated_data["password"])
        if user is None or not user.is_active:
            audit("auth.login_failed", data={"email": s.validated_data["email"].lower()}, ip=request.META.get("REMOTE_ADDR"))
            return Response({"error": {"code": "invalid_credentials", "message": "", "details": {}}},
                            status=status.HTTP_401_UNAUTHORIZED)
        if user.mfa_required:
            if f2.trusted(request, user):  # "remember this device"
                login(request, user)
                audit("auth.login", actor=user, data={"mfa": "trusted_device"}, ip=request.META.get("REMOTE_ADDR"))
                return Response(me_payload(user))
            request.session.flush()
            request.session[PENDING] = user.id
            has_device = TOTPDevice.objects.filter(user=user, confirmed=True).exists()
            methods = ["totp"] + (["whatsapp"] if f2.whatsapp_available(user) else [])
            return Response({"mfa": "verify" if has_device else "setup", "methods": methods,
                             "phone": f2.mask(user.phone) if "whatsapp" in methods else ""}, status=status.HTTP_200_OK)
        login(request, user)
        audit("auth.login", actor=user, ip=request.META.get("REMOTE_ADDR"))
        return Response(me_payload(user))


def _pending_user(request):
    from apps.identity.models import User
    uid = request.session.get(PENDING)
    return User.objects.filter(pk=uid, is_active=True).first() if uid else None


class MfaSetupView(APIView):
    serializer_class = None
    """Returns an otpauth:// URL for an authenticator app. Only during a pending login without a device."""
    permission_classes = [AllowAny]
    throttle_scope = "mfa"
    from rest_framework.throttling import ScopedRateThrottle
    throttle_classes = [ScopedRateThrottle]

    @extend_schema(request=None, responses=inline_serializer("MfaSetup", {"otpauth_url": serializers.CharField()}))
    def post(self, request):
        user = _pending_user(request)
        if user is None:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        if TOTPDevice.objects.filter(user=user, confirmed=True).exists():
            return Response({"error": {"code": "mfa_already_configured", "message": "", "details": {}}}, status=409)
        TOTPDevice.objects.filter(user=user, confirmed=False).delete()  # noqa
        device = TOTPDevice.objects.create(user=user, name="authenticator", confirmed=False)
        return Response({"otpauth_url": device.config_url})


class MfaVerifyView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "mfa"
    from rest_framework.throttling import ScopedRateThrottle
    throttle_classes = [ScopedRateThrottle]

    @extend_schema(request=MfaSerializer, responses={200: MeOut, 401: None, 429: None})
    def post(self, request):
        user = _pending_user(request)
        if user is None:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        s = MfaSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        if s.validated_data["method"] == "whatsapp":
            if not f2.verify_code(user, s.validated_data["token"]):
                audit("auth.mfa_failed", actor=user, data={"method": "whatsapp"}, ip=request.META.get("REMOTE_ADDR"))
                return Response({"error": {"code": "invalid_mfa_token", "message": "", "details": {}}}, status=401)
            del request.session[PENDING]
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            audit("auth.login", actor=user, data={"mfa": "whatsapp"}, ip=request.META.get("REMOTE_ADDR"))
            return self._done(request, user, s.validated_data["remember"])
        devices = list(TOTPDevice.objects.filter(user=user))
        for device in devices:
            allowed, info = device.verify_is_allowed()
            if not allowed:
                return Response({"error": {"code": "mfa_throttled", "message": "", "details": {
                    "retry_after": str((info or {}).get("locked_until", ""))}}}, status=429)
        for device in devices:
            if device.verify_token(s.validated_data["token"]):
                if not device.confirmed:
                    device.confirmed = True
                    device.save(update_fields=["confirmed"])
                del request.session[PENDING]
                login(request, user, backend="django.contrib.auth.backends.ModelBackend")
                otp_login(request, device)
                audit("auth.login", actor=user, data={"mfa": "totp"}, ip=request.META.get("REMOTE_ADDR"))
                return self._done(request, user, s.validated_data["remember"])
        audit("auth.mfa_failed", actor=user, ip=request.META.get("REMOTE_ADDR"))
        return Response({"error": {"code": "invalid_mfa_token", "message": "", "details": {}}}, status=401)


    def _done(self, request, user, remember):
        response = Response(me_payload(user))
        if remember:
            f2.remember(response, user, request.META.get("HTTP_USER_AGENT", ""))
            audit("auth.device_trusted", actor=user, ip=request.META.get("REMOTE_ADDR"))
        return response


class MfaWhatsAppView(APIView):
    """Send the second-factor code over the platform's WhatsApp number to the phone on the account."""
    permission_classes = [AllowAny]
    throttle_scope = "mfa"
    from rest_framework.throttling import ScopedRateThrottle
    throttle_classes = [ScopedRateThrottle]

    @extend_schema(request=None, responses=inline_serializer("MfaWhatsAppSent", {"sent": serializers.BooleanField(), "to": serializers.CharField()}))
    def post(self, request):
        user = _pending_user(request)
        if user is None:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        return Response(f2.send_code(user))


class TrustedDevicesView(APIView):
    """List this user's remembered browsers, or forget all of them (e.g. after losing a laptop)."""
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=inline_serializer("TrustedDevices", {"devices": serializers.ListField(child=serializers.DictField())}))
    def get(self, request):
        from django.utils import timezone
        rows = request.user.trusted_devices.filter(revoked_at__isnull=True, expires_at__gt=timezone.now()).order_by("-created_at")
        return Response({"devices": [{"id": d.id, "label": d.label, "created_at": d.created_at, "last_used_at": d.last_used_at,
                                      "expires_at": d.expires_at} for d in rows]})

    @extend_schema(request=None, responses={204: None})
    def delete(self, request):
        f2.revoke_all(request.user)
        audit("auth.devices_revoked", actor=request.user, ip=request.META.get("REMOTE_ADDR"))
        response = Response(status=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(f2.COOKIE)
        return response


class SetPasswordIn(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False, min_length=10)


class SetPasswordView(APIView):
    """Accept an invitation or finish a reset. The link works once."""
    permission_classes = [AllowAny]
    throttle_scope = "login"
    from rest_framework.throttling import ScopedRateThrottle
    throttle_classes = [ScopedRateThrottle]

    @extend_schema(request=SetPasswordIn, responses={204: None})
    def post(self, request):
        from apps.identity.services import accounts
        s = SetPasswordIn(data=request.data)
        s.is_valid(raise_exception=True)
        user = accounts.set_password(s.validated_data["uid"], s.validated_data["token"], s.validated_data["password"])
        audit("auth.password_set", actor=user, ip=request.META.get("REMOTE_ADDR"))
        return Response(status=status.HTTP_204_NO_CONTENT)


class ForgotIn(serializers.Serializer):
    email = serializers.EmailField()


class ForgotPasswordView(APIView):
    """Always answers the same, whether or not the email exists (no account discovery)."""
    permission_classes = [AllowAny]
    throttle_scope = "login"
    from rest_framework.throttling import ScopedRateThrottle
    throttle_classes = [ScopedRateThrottle]

    @extend_schema(request=ForgotIn, responses={200: dict})
    def post(self, request):
        from apps.identity.models import User
        from apps.identity.services import accounts
        s = ForgotIn(data=request.data)
        s.is_valid(raise_exception=True)
        user = User.objects.filter(email=s.validated_data["email"].lower(), is_active=True).first()
        if user is not None and user.has_usable_password():
            out = accounts.deliver(user, "reset")
            audit("auth.reset_requested", actor=user, data={"channel": out["channel"]}, ip=request.META.get("REMOTE_ADDR"))
            # a reset link is never shown to an anonymous caller; without email/WhatsApp an administrator must help
        return Response({"ok": True})


class LogoutView(APIView):
    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=MeOut)
    def get(self, request):
        return Response(me_payload(request.user))
