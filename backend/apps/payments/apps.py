from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    name = "apps.payments"
    label = "payments"

    def ready(self):
        from apps.payments.services import deposits, links  # noqa: F401  registers the outbox handlers
