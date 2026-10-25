"""Numbering, outbox and idempotency services."""
import hashlib
import json
import logging
from datetime import timedelta
from functools import wraps

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.response import Response

from apps.core.errors import ConflictError, DomainError
from apps.core.models import IdempotencyRecord, NumberSequence, OutboxEvent

log = logging.getLogger(__name__)


# ---------- numbering ----------
def next_number(tenant_id: int, scope: str) -> int:
    """Must be called inside transaction.atomic(); concurrent callers serialise on the sequence row."""
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("next_number must run inside a transaction")
    NumberSequence.objects.get_or_create(tenant_id=tenant_id, scope=scope)
    seq = NumberSequence.objects.select_for_update().get(tenant_id=tenant_id, scope=scope)
    value = seq.next_value
    seq.next_value = value + 1
    seq.save(update_fields=["next_value"])
    return value


# ---------- outbox ----------
HANDLERS = {}
MAX_ATTEMPTS = 8


def outbox_handler(topic):
    def deco(fn):
        HANDLERS[topic] = fn
        return fn
    return deco


def enqueue(topic: str, payload: dict, tenant_id=None, dedupe_key=None, delay_seconds=0):
    """Write an outbox event in the caller's transaction. Duplicate dedupe_key for the same topic is ignored."""
    try:
        with transaction.atomic():
            return OutboxEvent.objects.create(
                tenant_id=tenant_id, topic=topic, payload=payload, dedupe_key=dedupe_key,
                available_at=timezone.now() + timedelta(seconds=delay_seconds))
    except IntegrityError:
        if dedupe_key is None:
            raise
        return OutboxEvent.objects.get(topic=topic, dedupe_key=dedupe_key)


def process_outbox(batch_size=50) -> int:
    """Deliver due events. Safe to run from several workers (SKIP LOCKED). Returns number processed."""
    done = 0
    with transaction.atomic():
        events = list(OutboxEvent.objects.select_for_update(skip_locked=True)
                      .filter(status=OutboxEvent.Status.PENDING, available_at__lte=timezone.now())
                      .order_by("id")[:batch_size])
        for ev in events:
            handler = HANDLERS.get(ev.topic)
            ev.attempts += 1
            try:
                if handler is None:
                    raise LookupError(f"No outbox handler for topic {ev.topic}")
                with transaction.atomic():  # savepoint: a failing handler doesn't poison the batch
                    handler(ev)
                ev.status, ev.processed_at, ev.last_error = OutboxEvent.Status.DONE, timezone.now(), ""
                done += 1
            except Exception as exc:  # noqa: BLE001 — recorded and retried
                log.warning("outbox event %s failed: %s", ev.id, exc)
                ev.last_error = repr(exc)[:2000]
                if ev.attempts >= MAX_ATTEMPTS:
                    ev.status = OutboxEvent.Status.FAILED
                else:
                    ev.available_at = timezone.now() + timedelta(seconds=min(3600, 2 ** ev.attempts * 5))
            ev.save()
    return done


# ---------- idempotency ----------
def _hash_request(request) -> str:
    body = request.data if hasattr(request, "data") else {}
    canon = json.dumps(body, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(f"{request.method}|{request.path}|{canon}".encode()).hexdigest()


def idempotent(view_method):
    """DRF view decorator: requires `Idempotency-Key`; replays the stored response for identical retries."""
    @wraps(view_method)
    def wrapper(self, request, *args, **kwargs):
        key = request.headers.get("Idempotency-Key")
        if not key or len(key) > 128:
            raise DomainError("Idempotency-Key header is required", code="idempotency_key_required")
        tenant_id = getattr(request, "tenant_id", None)
        req_hash = _hash_request(request)
        try:
            with transaction.atomic():
                rec = IdempotencyRecord.objects.create(tenant_id=tenant_id, key=key, user=request.user,
                                                       method=request.method, path=request.path,
                                                       request_hash=req_hash)
        except IntegrityError:
            rec = IdempotencyRecord.objects.get(tenant_id=tenant_id, key=key)
            if rec.request_hash != req_hash:
                raise DomainError("Idempotency-Key reused with a different request", code="idempotency_key_mismatch")
            if rec.state == IdempotencyRecord.State.IN_PROGRESS:
                raise ConflictError("Request with this Idempotency-Key is still in progress", code="idempotency_in_progress")
            resp = Response(rec.response_body, status=rec.status_code)
            resp["Idempotent-Replay"] = "true"
            return resp
        try:
            response = view_method(self, request, *args, **kwargs)
        except Exception:
            rec.delete()  # allow a clean retry after a failure
            raise
        if 200 <= response.status_code < 300:
            rec.state, rec.status_code, rec.response_body = IdempotencyRecord.State.DONE, response.status_code, response.data
            rec.save(update_fields=["state", "status_code", "response_body"])
        else:
            rec.delete()
        return response
    return wrapper
