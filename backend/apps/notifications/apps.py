from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    name = "apps.notifications"
    label = "notifications"

    def ready(self):
        from apps.notifications import auto  # noqa: F401  registers the outbox handlers
