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
    required_permissions = {"GET": "org.manage", "POST": "org.manage"}

    @extend_schema(responses=dict)
    def get(self, request):
        ch = WhatsAppChannel.objects.first()
        if ch is not None:
            whatsapp.refresh(ch)
        return Response(status_payload(request, ch))

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
