import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "qassa.settings")
app = Celery("qassa")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks(["apps.core", "apps.platform", "apps.notifications", "apps.loyalty"])
from celery.schedules import crontab  # noqa: E402

app.conf.beat_schedule = {
    "deliver-outbox": {"task": "apps.core.tasks.deliver_outbox", "schedule": 5.0},
    "booking-reminders": {"task": "apps.notifications.tasks.queue_reminders", "schedule": 900.0},
    "daily-loyalty": {"task": "apps.loyalty.tasks.daily_loyalty", "schedule": crontab(hour=0, minute=20)},
    "daily-billing": {"task": "apps.platform.tasks.daily_billing", "schedule": crontab(hour=1, minute=10)},
}
