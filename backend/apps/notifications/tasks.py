from celery import shared_task


@shared_task
def queue_reminders():
    from apps.notifications.auto import queue_reminders as run
    return run()


@shared_task
def queue_winback():
    from apps.notifications.auto import queue_winback as run
    return run()


@shared_task
def queue_rebook():
    from apps.notifications.auto import queue_rebook as run
    return run()
