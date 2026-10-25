from django.db import models


class IdempotencyRecord(models.Model):
    """One row per (tenant, Idempotency-Key). Replays return the stored response; a different body is rejected."""
    class State(models.TextChoices):
        IN_PROGRESS = "in_progress"
        DONE = "done"

    tenant = models.ForeignKey("tenancy.Tenant", on_delete=models.PROTECT, null=True)
    key = models.CharField(max_length=128)
    user = models.ForeignKey("identity.User", on_delete=models.PROTECT, null=True)
    method = models.CharField(max_length=8)
    path = models.CharField(max_length=255)
    request_hash = models.CharField(max_length=64)
    state = models.CharField(max_length=16, choices=State.choices, default=State.IN_PROGRESS)
    status_code = models.PositiveSmallIntegerField(null=True)
    response_body = models.JSONField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "key"], name="uniq_idempotency_tenant_key",
                                               nulls_distinct=False)]


class OutboxEvent(models.Model):
    """Side effects written in the same transaction as the business change, delivered later with retries."""
    class Status(models.TextChoices):
        PENDING = "pending"
        DONE = "done"
        FAILED = "failed"  # gave up after max attempts — visible on the failed-operations screen

    tenant = models.ForeignKey("tenancy.Tenant", on_delete=models.PROTECT, null=True)
    topic = models.CharField(max_length=100)
    payload = models.JSONField(default=dict)
    dedupe_key = models.CharField(max_length=200, null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    available_at = models.DateTimeField(db_index=True)
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["topic", "dedupe_key"], name="uniq_outbox_dedupe",
                                               condition=models.Q(dedupe_key__isnull=False))]


class NumberSequence(models.Model):
    """Gap-free document numbering. The row is locked with SELECT ... FOR UPDATE when a number is taken."""
    tenant = models.ForeignKey("tenancy.Tenant", on_delete=models.PROTECT)
    scope = models.CharField(max_length=100)  # e.g. "je:<legal_entity_id>:2026"
    next_value = models.PositiveBigIntegerField(default=1)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["tenant", "scope"], name="uniq_sequence_scope")]
