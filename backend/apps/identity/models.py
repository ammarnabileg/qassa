from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.update(is_staff=True, is_superuser=True, is_platform_staff=True, mfa_required=True)
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """Staff identity (platform and salon staff). Salon customers are a separate model in the CRM module."""
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    preferred_language = models.CharField(max_length=5, default="ar", choices=[("ar", "Arabic"), ("en", "English")])
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)  # Django admin access only
    is_platform_staff = models.BooleanField(default=False)
    mfa_required = models.BooleanField(default=False)
    date_joined = models.DateTimeField(auto_now_add=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    def __str__(self):
        return self.email


class StaffOtp(models.Model):
    """Second factor sent over the platform's WhatsApp number (alternative to an authenticator app). Hash only."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class TrustedDevice(models.Model):
    """"Remember this device": skips the second factor on this browser until it expires or is revoked.
    The browser holds a random token in an HttpOnly cookie; only its SHA-256 is stored."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="trusted_devices")
    token_hash = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=200, blank=True)  # browser user agent, for the user's device list
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
