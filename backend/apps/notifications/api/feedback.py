"""Visit ratings: the public page behind the WhatsApp link, and the salon's list of ratings."""
from django.db.models import Avg, Count, Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.errors import DomainError
from apps.core.throttling import AtomicScopedRateThrottle as ScopedRateThrottle
from apps.notifications.models import Feedback
from apps.tenancy.api.base import TenantAPIView
from apps.tenancy.context import tenant_context


class FeedbackNotFound(DomainError):
    status_code = 404
    code = "feedback_not_found"


class RateIn(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(max_length=500, required=False, allow_blank=True)


def _get(token):
    fb = Feedback.unscoped.select_related("tenant", "branch").filter(token=token).first()
    if fb is None or not fb.tenant.writable:
        raise FeedbackNotFound()
    return fb


def _payload(fb):
    from apps.notifications.auto import settings_for
    happy = fb.rating is not None and fb.rating >= 4
    return {"salon": fb.tenant.name, "branch_ar": fb.branch.name_ar, "branch_en": fb.branch.name_en, "rating": fb.rating,
            "review_url": settings_for(fb.tenant_id).google_review_url if happy else ""}


class PublicFeedbackView(APIView):
    """GET shows what is being rated; POST records the rating once. The token is the only key (no login)."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public"

    @extend_schema(responses=dict)
    def get(self, request, token):
        fb = _get(token)
        with tenant_context(fb.tenant_id):
            return Response(_payload(fb))

    @extend_schema(request=RateIn, responses=dict)
    def post(self, request, token):
        s = RateIn(data=request.data)
        s.is_valid(raise_exception=True)
        fb = _get(token)
        with tenant_context(fb.tenant_id):
            n = Feedback.objects.filter(id=fb.id, rating__isnull=True).update(
                rating=s.validated_data["rating"], comment=s.validated_data.get("comment", "").strip(), rated_at=timezone.now())
            if not n:
                raise DomainError(code="feedback_already_rated")
            fb.refresh_from_db()
            return Response(_payload(fb))


class FeedbackListView(TenantAPIView):
    """Ratings for the salon (or the current branch): averages, distribution and the latest answers, low ones first to act on."""
    required_permissions = {"GET": "customers.view"}

    @extend_schema(responses=dict)
    def get(self, request):
        from apps.tenancy.api.base import branch_for
        qs = Feedback.objects.all()
        if request.query_params.get("branch_id"):
            qs = qs.filter(branch_id=branch_for(request, request.query_params["branch_id"]).id)
        elif (allowed := request.membership.branch_ids()) is not None:
            qs = qs.filter(branch_id__in=allowed)
        rated = qs.filter(rating__isnull=False)
        agg = rated.aggregate(avg=Avg("rating"), n=Count("id"), low=Count("id", filter=Q(rating__lte=3)))
        rows = rated.select_related("customer", "branch", "invoice").order_by("-rated_at")[:100]
        return Response({
            "sent": qs.count(), "rated": agg["n"], "average": round(agg["avg"], 2) if agg["avg"] else None, "low": agg["low"],
            "distribution": {str(i): rated.filter(rating=i).count() for i in range(1, 6)},
            "items": [{"id": f.id, "rating": f.rating, "comment": f.comment, "rated_at": f.rated_at, "customer": f.customer.full_name,
                       "phone": f.customer.phone, "branch_ar": f.branch.name_ar, "branch_en": f.branch.name_en, "invoice": f.invoice.number}
                      for f in rows]})
