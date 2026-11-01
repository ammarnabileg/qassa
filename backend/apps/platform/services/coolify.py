"""Keep the app's domain list in Coolify in step with the companies' addresses (D-016).

Off unless COOLIFY_API_URL, COOLIFY_API_TOKEN and COOLIFY_APP_UUID are set. Only ever ADDS names to this one
application's web service, then redeploys it so Traefik routes the name and issues its certificate. It never
removes a name and never touches another application."""
import json
import logging
import urllib.request

from django.conf import settings

from apps.core.services.infra import enqueue, outbox_handler

log = logging.getLogger("qassa.coolify")


def enabled() -> bool:
    c = settings.QASSA
    return bool(c["COOLIFY_API_URL"] and c["COOLIFY_API_TOKEN"] and c["COOLIFY_APP_UUID"])


def request_sync():
    """Call inside the transaction that created or activated a domain; runs after commit through the outbox."""
    if enabled():
        enqueue("coolify.domains", {})


def _call(method, path, body=None):
    c = settings.QASSA
    req = urllib.request.Request(f"{c['COOLIFY_API_URL'].rstrip('/')}/api/v1{path}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {c['COOLIFY_API_TOKEN']}", "Content-Type": "application/json",
                                          "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as res:
        return json.loads(res.read() or b"{}")


def wanted_hosts() -> list[str]:
    from apps.platform.models import TenantDomain
    hosts = [h.strip() for h in settings.PLATFORM_HOSTS if h.strip() and h not in {"localhost", "127.0.0.1", "testserver"}]
    hosts += list(TenantDomain.objects.filter(is_active=True).values_list("host", flat=True))
    return hosts


def sync() -> list[str]:
    """Add every missing host to the web service; redeploy only when something was added. Returns the added hosts."""
    uuid, svc = settings.QASSA["COOLIFY_APP_UUID"], settings.QASSA["COOLIFY_WEB_SERVICE"]
    app = _call("GET", f"/applications/{uuid}")
    domains = app.get("docker_compose_domains") or {}
    if isinstance(domains, str):
        domains = json.loads(domains or "{}")
    current = [d.strip() for d in (domains.get(svc, {}).get("domain") or "").split(",") if d.strip()]
    have = {d.split("://", 1)[-1].rstrip("/") for d in current}
    added = [h for h in dict.fromkeys(wanted_hosts()) if h not in have]
    if not added:
        return []
    body = [{"name": name, "domain": v.get("domain") or ""} for name, v in domains.items() if name != svc]
    body.append({"name": svc, "domain": ",".join(current + [f"https://{h}" for h in added])})
    _call("PATCH", f"/applications/{uuid}", {"docker_compose_domains": body})
    _call("POST", f"/deploy?uuid={uuid}&force=false")
    log.info("coolify: added %s and redeployed", ", ".join(added))
    return added


@outbox_handler("coolify.domains")
def handle(ev):
    if enabled():
        sync()   # an error (Coolify down, bad token) raises: the outbox retries with backoff and keeps the error
