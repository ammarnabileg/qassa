"""Plan limits enforced on the server when branches or staff are added."""
from apps.core.errors import DomainError
from apps.platform.models import Subscription


def check_limit(tenant_id: int, kind: str, current: int):
    sub = Subscription.objects.select_related("plan").filter(tenant_id=tenant_id).first()
    if sub is None:
        raise DomainError(code="no_subscription", message="Tenant has no subscription plan")
    limit = {"branches": sub.plan.max_branches, "staff": sub.plan.max_staff}[kind]
    if current >= limit:
        raise DomainError(code=f"plan_limit_{kind}", message=f"Plan allows {limit} {kind}",
                          details={"limit": limit, "plan": sub.plan.code})
