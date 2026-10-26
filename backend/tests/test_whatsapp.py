"""Per-company WhatsApp number on an Evolution API v2 gateway (fake gateway with the same request shapes)."""
import pytest
from rest_framework.test import APIClient

from apps.identity.models import User
from apps.notifications import whatsapp
from apps.notifications.models import WhatsAppChannel, WhatsAppMessage
from apps.platform.models import TenantDomain
from apps.tenancy.context import tenant_context
from tests.conftest import add_member, client_for

pytestmark = pytest.mark.django_db


class FakeEvolution:
    """Mimics Evolution API v2: instances start 'close', become 'connecting' after /connect, 'open' once scanned."""
    def __init__(self):
        self.instances, self.sent, self.fail_send = {}, [], False

    def __call__(self, method, path, body=None):
        parts = path.split("?")[0].strip("/").split("/")
        if (method, parts[:2]) == ("POST", ["instance", "create"]):
            self.instances[body["instanceName"]] = "close"
            return {"instance": {"instanceName": body["instanceName"], "status": "close"}, "hash": "X"}
        name = parts[-1]
        if parts[:2] == ["instance", "connect"]:
            self.instances[name] = "connecting"
            return {"pairingCode": None, "code": "2@abc", "base64": "data:image/png;base64,QR==", "count": 1}
        if parts[:2] == ["instance", "connectionState"]:
            return {"instance": {"instanceName": name, "state": self.instances.get(name, "close")}}
        if parts[:2] == ["instance", "fetchInstances"]:
            n = path.split("instanceName=")[1]
            return [{"name": n, "ownerJid": "96550001111@s.whatsapp.net"}]
        if parts[:2] == ["instance", "logout"]:
            self.instances[name] = "close"
            return {"status": "SUCCESS"}
        if parts[:2] == ["message", "sendText"]:
            if self.fail_send or self.instances.get(name) != "open":
                self.instances[name] = "close"
                raise whatsapp.GatewayError(message="gateway 400")
            self.sent.append((name, body["number"], body["text"]))
            return {"key": {"id": "1"}, "status": "PENDING"}
        raise AssertionError(f"unexpected {method} {path}")


@pytest.fixture
def gw(monkeypatch, settings):
    fake = FakeEvolution()
    settings.QASSA = {**settings.QASSA, "WHATSAPP_ADAPTER": "evolution", "OTP_ECHO": False}
    monkeypatch.setattr(whatsapp, "_call", fake)
    return fake


def owner(t):
    return User.objects.get(memberships__tenant=t, memberships__role__key="owner")


def test_connect_by_qr_then_otp_is_sent_from_the_companys_own_number(gw, company_a, settings):
    t, _, _ = company_a
    c = client_for(owner(t), t)
    assert c.get("/api/v1/whatsapp").json()["state"] == "new"
    r = c.post("/api/v1/whatsapp/connect").json()
    assert r["qr"].startswith("data:image/png") and r["state"] == "connecting"
    assert f"qassa-{t.slug}" in gw.instances
    # login codes are refused while the number is not connected — no fake success
    settings.PLATFORM_HOSTS = ["testserver"]
    TenantDomain.objects.filter(tenant=t).update(host="kids.test", is_active=True)
    app = APIClient(HTTP_HOST="kids.test")
    r = app.post("/api/v1/app/otp/request", {"phone": "55551234"}, format="json")
    assert r.status_code == 503 and r.json()["error"]["code"] == "whatsapp_unavailable"
    # the salon scans the QR
    gw.instances[f"qassa-{t.slug}"] = "open"
    st = c.get("/api/v1/whatsapp").json()
    assert st["state"] == "open" and st["phone"] == "96550001111"
    r = app.post("/api/v1/app/otp/request", {"phone": "55551234"}, format="json")
    assert r.status_code == 200 and "debug_code" not in r.json()
    inst, number, text = gw.sent[-1]
    assert inst == f"qassa-{t.slug}" and number == "96555551234" and any(ch.isdigit() for ch in text)
    log = c.get("/api/v1/whatsapp").json()["messages"]
    assert log[0]["kind"] == "otp" and log[0]["status"] == "sent" and log[0]["preview"] == ""  # code never stored


def test_each_company_has_its_own_instance(gw, company_a, company_b):
    ta, _, _ = company_a
    tb, _, _ = company_b
    client_for(owner(ta), ta).post("/api/v1/whatsapp/connect")
    client_for(owner(tb), tb).post("/api/v1/whatsapp/connect")
    assert {f"qassa-{ta.slug}", f"qassa-{tb.slug}"} <= set(gw.instances)
    with tenant_context(ta.id):
        assert WhatsAppChannel.objects.get().instance_name == f"qassa-{ta.slug}"


def test_send_failure_is_logged_and_state_refreshed(gw, company_a):
    t, _, _ = company_a
    c = client_for(owner(t), t)
    c.post("/api/v1/whatsapp/connect")
    gw.instances[f"qassa-{t.slug}"] = "open"
    c.get("/api/v1/whatsapp")
    gw.fail_send = True
    with tenant_context(t.id), pytest.raises(whatsapp.ChannelUnavailable):
        whatsapp.send_text("96555551234", "hello", kind="test", preview="hello")
    st = c.get("/api/v1/whatsapp").json()
    assert st["state"] == "close" and st["messages"][0]["status"] == "failed"


def test_disconnect_and_permissions(gw, company_a):
    t, _, b = company_a
    c = client_for(owner(t), t)
    c.post("/api/v1/whatsapp/connect")
    assert c.post("/api/v1/whatsapp/disconnect").json()["state"] == "close"
    cashier = add_member(t, "c@k.test", "cashier", branch=b["HAW"])
    assert client_for(cashier, t).get("/api/v1/whatsapp").status_code == 403
    assert client_for(cashier, t).post("/api/v1/whatsapp/connect").status_code == 403


def test_without_gateway_connect_is_a_clear_error(company_a, settings):
    settings.QASSA = {**settings.QASSA, "WHATSAPP_ADAPTER": "disabled"}
    t, _, _ = company_a
    r = client_for(owner(t), t).post("/api/v1/whatsapp/connect")
    assert r.status_code == 503 and r.json()["error"]["code"] == "whatsapp_unavailable"
