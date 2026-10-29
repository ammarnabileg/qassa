from celery import shared_task


@shared_task
def queue_reminders():
    from apps.notifications.auto import queue_reminders as run
    return run()
