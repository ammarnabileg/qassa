import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "qassa.settings")
app = Celery("qassa")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks(["apps.core"])
app.conf.beat_schedule = {"deliver-outbox": {"task": "apps.core.tasks.deliver_outbox", "schedule": 5.0}}
