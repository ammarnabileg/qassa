from django.contrib import admin
from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView

from apps.accounting.api import views as acc
from apps.identity.api import views as auth
from apps.platform.api import views as plat
from apps.tenancy.api import views as org

api = "api/v1/"
urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularRedocView.as_view(url_name="schema")),
    # identity
    path(api + "auth/csrf", auth.CsrfView.as_view()),
    path(api + "auth/login", auth.LoginView.as_view()),
    path(api + "auth/mfa/setup", auth.MfaSetupView.as_view()),
    path(api + "auth/mfa/verify", auth.MfaVerifyView.as_view()),
    path(api + "auth/logout", auth.LogoutView.as_view()),
    path(api + "auth/me", auth.MeView.as_view()),
    # tenant-scoped (X-Tenant header)
    path(api + "org", org.OrgView.as_view()),
    path(api + "accounting/accounts", acc.AccountListView.as_view()),
    path(api + "accounting/journal-entries", acc.JournalEntryListCreateView.as_view()),
    path(api + "accounting/journal-entries/<int:pk>/reverse", acc.JournalEntryReverseView.as_view()),
    path(api + "accounting/trial-balance", acc.TrialBalanceView.as_view()),
    path(api + "accounting/periods/<int:pk>/<str:action>", acc.PeriodCloseView.as_view()),
    # platform
    path(api + "platform/tenants", plat.TenantCreateView.as_view()),
]
