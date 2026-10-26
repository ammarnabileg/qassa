from django.conf import settings
from django.http import JsonResponse
from django.contrib import admin
from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView

from apps.accounting.api import views as acc
from apps.identity.api import views as auth
from apps.platform.api import views as plat
from apps.tenancy.api import views as org
from apps.tenancy.api.public import PublicManifestView, PublicSalonView
from apps.booking.api import views as bk
from apps.catalog.api import views as cat
from apps.notifications.api.views import WhatsAppView
from apps.pos.api import views as pos
from apps.customers.api import app as capp
from apps.customers.api import views as cust
from apps.staff.api import views as stf

api = "api/v1/"


def version(_request):
    return JsonResponse({"version": settings.QASSA_VERSION, "channel": settings.QASSA_CHANNEL})


urlpatterns = [
    path("api/v1/version", version),
    path(api + "public/salon", PublicSalonView.as_view()),
    path(api + "public/salons/<slug:slug>", PublicSalonView.as_view()),
    path(api + "public/manifest", PublicManifestView.as_view()),
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
    path(api + "platform/tenants", plat.TenantsView.as_view()),
    # phase 2: setup
    path(api + "org/branches", org.BranchesView.as_view()),
    path(api + "org/branches/<int:pk>", org.BranchDetailView.as_view()),
    path(api + "subscription", org.SubscriptionView.as_view()),
    path(api + "catalog/categories", cat.CategoriesView.as_view()),
    path(api + "catalog/services", cat.ServicesView.as_view()),
    path(api + "catalog/services/<int:pk>", cat.ServiceDetailView.as_view()),
    path(api + "catalog/services/<int:pk>/prices", cat.ServicePricesView.as_view()),
    path(api + "staff", stf.StaffListView.as_view()),
    path(api + "staff/<int:pk>", stf.StaffDetailView.as_view()),
    path(api + "customers", cust.CustomersView.as_view()),
    path(api + "customers/<int:pk>", cust.CustomerDetailView.as_view()),
    path(api + "customers/<int:pk>/beneficiaries", cust.BeneficiariesView.as_view()),
    path(api + "beneficiaries/<int:pk>", cust.BeneficiaryDetailView.as_view()),
    path(api + "platform/tenants/<int:pk>", plat.TenantAdminView.as_view()),
    path(api + "platform/tenants/<int:pk>/domains", plat.TenantDomainsView.as_view()),
    path(api + "platform/domains/<int:pk>", plat.DomainDetailView.as_view()),
    path(api + "platform/plans", plat.PlansView.as_view()),
    path(api + "platform/plans/<int:pk>", plat.PlanDetailView.as_view()),
    # phase 3: operations
    path(api + "booking/appointments", bk.AppointmentsView.as_view()),
    path(api + "booking/appointments/<int:pk>", bk.AppointmentDetailView.as_view()),
    path(api + "booking/appointments/<int:pk>/status", bk.AppointmentStatusView.as_view()),
    path(api + "pos/sessions", pos.SessionsView.as_view()),
    path(api + "pos/sessions/<int:pk>/close", pos.SessionCloseView.as_view()),
    path(api + "pos/sessions/<int:pk>/approve", pos.SessionApproveView.as_view()),
    path(api + "pos/checkout", pos.CheckoutView.as_view()),
    path(api + "pos/invoices", pos.InvoicesView.as_view()),
    path(api + "pos/invoices/<int:pk>", pos.InvoiceDetailView.as_view()),
    path(api + "pos/invoices/<int:pk>/payments", pos.InvoicePaymentsView.as_view()),
    path(api + "pos/invoices/<int:pk>/credit-notes", pos.InvoiceCreditNotesView.as_view()),
    path(api + "whatsapp", WhatsAppView.as_view()),
    path(api + "whatsapp/<str:action>", WhatsAppView.as_view()),
    # customer app
    path(api + "app/otp/request", capp.OtpRequestView.as_view()),
    path(api + "app/otp/verify", capp.OtpVerifyView.as_view()),
    path(api + "app/register", capp.RegisterView.as_view()),
    path(api + "app/me", capp.MeView.as_view()),
    path(api + "app/me/beneficiaries", capp.MyBeneficiariesView.as_view()),
    path(api + "app/catalog", capp.CatalogView.as_view()),
    path(api + "app/slots", capp.SlotsView.as_view()),
    path(api + "app/bookings", capp.MyBookingsView.as_view()),
    path(api + "app/bookings/<int:pk>/cancel", capp.MyBookingCancelView.as_view()),
]
