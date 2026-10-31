from drf_spectacular.utils import extend_schema
from rest_framework import serializers
from rest_framework.response import Response

from apps.notifications import whatsapp
from apps.notifications.models import WhatsAppChannel, WhatsAppMessage
from apps.tenancy.api.base import TenantAPIView


class MessageOut(serializers.ModelSerializer):
    class Meta:
        model = WhatsAppMessage
        fields = ["id", "to", "kind", "preview", "status", "error", "created_at"]


def status_payload(request, ch: WhatsAppChannel | None) -> dict:
    return {"gateway": whatsapp.adapter(), "state": ch.state if ch else "new", "phone": ch.phone if ch else "",
            "checked_at": ch.checked_at if ch else None, "connected_at": ch.connected_at if ch else None,
            "messages": MessageOut(WhatsAppMessage.objects.order_by("-id")[:30], many=True).data}


class WhatsAppView(TenantAPIView):
    """The company's own WhatsApp number (D-002): status, connect by QR, disconnect, recent messages."""
    required_permissions = {"GET": "org.manage"}

    @extend_schema(responses=dict)
    def get(self, request):
        ch = WhatsAppChannel.objects.first()
        if ch is not None:
            whatsapp.refresh(ch)
        return Response(status_payload(request, ch))



class WhatsAppActionView(TenantAPIView):
    required_permissions = {"POST": "org.manage"}

    @extend_schema(request=None, responses=dict)
    def post(self, request, action):
        from apps.audit.services.log import record as audit
        tenant = request.membership.tenant
        if action == "connect":
            out = whatsapp.connect(tenant)
            audit("whatsapp.connect_requested", tenant_id=tenant.id, actor=request.user)
            return Response({**status_payload(request, WhatsAppChannel.objects.first()), "qr": out["qr"],
                             "pairing_code": out["pairing_code"]})
        if action == "disconnect":
            whatsapp.disconnect(tenant)
            audit("whatsapp.disconnected", tenant_id=tenant.id, actor=request.user)
            return Response(status_payload(request, WhatsAppChannel.objects.first()))
        return Response(status=404)


class MessagingSettingsSerializer(serializers.Serializer):
    booking_confirmation = serializers.BooleanField(required=False)
    reminder = serializers.BooleanField(required=False)
    reminder_hours = serializers.IntegerField(min_value=1, max_value=48, required=False)
    receipt = serializers.BooleanField(required=False)
    feedback = serializers.BooleanField(required=False)
    google_review_url = serializers.URLField(required=False, allow_blank=True, max_length=200)
    winback = serializers.BooleanField(required=False)
    winback_days = serializers.IntegerField(min_value=14, max_value=365, required=False)
    winback_coupon = serializers.CharField(required=False, allow_blank=True, max_length=30)

    def validate_winback_coupon(self, v):
        return v.strip().upper()


class MessagingSettingsView(TenantAPIView):
    """Automatic service messages (D-012)."""
    required_permissions = {"GET": "org.manage", "PATCH": "org.manage"}

    @extend_schema(responses=MessagingSettingsSerializer)
    def get(self, request):
        from apps.notifications.auto import settings_for
        return Response(MessagingSettingsSerializer(settings_for(request.tenant_id)).data)

    @extend_schema(request=MessagingSettingsSerializer, responses=MessagingSettingsSerializer)
    def patch(self, request):
        from apps.audit.services.log import record as audit
        from apps.notifications.auto import settings_for
        s = MessagingSettingsSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        obj = settings_for(request.tenant_id)
        for k, v in s.validated_data.items():
            setattr(obj, k, v)
        obj.save()
        audit("whatsapp.auto_settings", tenant_id=request.tenant_id, actor=request.user, obj=obj, data=s.validated_data)
        return Response(MessagingSettingsSerializer(obj).data)
