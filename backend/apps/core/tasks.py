from celery import shared_task

from apps.core.services.infra import process_outbox


@shared_task
def deliver_outbox():
    return process_outbox()
