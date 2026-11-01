from django.apps import AppConfig


class PlatformConfig(AppConfig):
    name = "apps.platform"
    label = "platform"

    def ready(self):
        from apps.platform.services import coolify  # noqa: F401  registers the outbox handler
