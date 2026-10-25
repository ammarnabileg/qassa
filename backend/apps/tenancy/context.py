"""Request/task-local tenant context. Set only by trusted server code after membership verification."""
from contextlib import contextmanager
from contextvars import ContextVar

_tenant_id: ContextVar[int | None] = ContextVar("tenant_id", default=None)
_membership = ContextVar("membership", default=None)


def get_tenant_id() -> int | None:
    return _tenant_id.get()


def get_membership():
    return _membership.get()


def set_context(tenant_id, membership=None):
    return _tenant_id.set(tenant_id), _membership.set(membership)


def reset_context(tokens):
    t1, t2 = tokens
    _tenant_id.reset(t1)
    _membership.reset(t2)


def clear_context():
    _tenant_id.set(None)
    _membership.set(None)


@contextmanager
def tenant_context(tenant_id, membership=None):
    """Use in services, Celery tasks and tests: `with tenant_context(t.id): ...`"""
    tokens = set_context(tenant_id, membership)
    try:
        yield
    finally:
        reset_context(tokens)
