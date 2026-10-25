import hashlib
import json

from django.db import connection, transaction

from apps.audit.models import AuditLog

GENESIS = "0" * 64


def _digest(prev_hash, tenant_id, actor_id, action, object_type, object_id, data, reason):
    canon = json.dumps([prev_hash, tenant_id, actor_id, action, object_type, str(object_id), data, reason],
                       sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(canon.encode()).hexdigest()


def record(action, *, tenant_id=None, actor=None, obj=None, object_type="", object_id="", data=None,
           reason="", ip=None, acting_as_support=False):
    """Append an audit row. Serialised per tenant with an advisory lock so the chain stays linear."""
    data = data or {}
    if obj is not None:
        object_type = object_type or type(obj).__name__
        object_id = object_id or obj.pk
    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", [f"audit:{tenant_id}"])
        last = AuditLog.objects.filter(tenant_id=tenant_id).order_by("-id").values_list("hash", flat=True).first()
        prev = last or GENESIS
        actor_id = actor.pk if actor is not None and getattr(actor, "pk", None) else None
        h = _digest(prev, tenant_id, actor_id, action, object_type, object_id, data, reason)
        return AuditLog.objects.create(tenant_id=tenant_id, actor_id=actor_id, action=action,
                                       object_type=object_type, object_id=str(object_id), data=data,
                                       reason=reason, ip=ip, acting_as_support=acting_as_support,
                                       prev_hash=prev, hash=h)


def verify_chain(tenant_id) -> tuple[bool, int | None]:
    """Recompute the chain. Returns (ok, first_bad_id)."""
    prev = GENESIS
    for row in AuditLog.objects.filter(tenant_id=tenant_id).order_by("id"):
        expected = _digest(prev, row.tenant_id, row.actor_id, row.action, row.object_type, row.object_id,
                           row.data, row.reason)
        if row.prev_hash != prev or row.hash != expected:
            return False, row.id
        prev = row.hash
    return True, None
