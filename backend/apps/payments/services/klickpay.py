"""KlickPay API v3 client (docs v0.6). Per-salon credentials; the access token is cached per account.

Known gaps in KlickPay's own documentation (confirm with them before go-live): the production base URL, the
/webhooks/config body and secret rotation, and whether client_email may be the salon's address."""
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.core.cache import cache

from apps.core.errors import DomainError
from apps.core.secrets import decrypt

log = logging.getLogger("qassa.klickpay")
TOKEN_SECONDS = 45 * 60   # lifetime is not documented; refreshed early and again on a 401


class GatewayUnavailable(DomainError):
    status_code = 502
    code = "gateway_unavailable"


def base_url(acc) -> str:
    url = settings.QASSA["KLICKPAY_URLS"].get(acc.environment) or ""
    if not url:
        raise GatewayUnavailable(code="gateway_not_configured", message=f"No KlickPay URL for {acc.environment}")
    return url.rstrip("/")


def _http(method, url, headers, body=None):
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Accept": "application/json", "Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=20) as res:
            return res.status, json.loads(res.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise GatewayUnavailable(message=str(e)[:200])


def _find_token(data: dict) -> str:
    """The docs warn the token may be nested under data or top-level, under several names."""
    for src in (data.get("data") or {}, data):
        for k in ("access_token", "bearer_token", "token"):
            if isinstance(src, dict) and src.get(k):
                return str(src[k])
    return ""


def token(acc, fresh=False) -> str:
    key = f"klickpay-token:{acc.id}"
    if not fresh and (hit := cache.get(key)):
        return hit
    secret = decrypt(acc.client_secret_enc)
    if not acc.client_id or not secret:
        raise GatewayUnavailable(code="gateway_not_configured", message="KlickPay credentials are missing")
    status, data = _http("POST", f"{base_url(acc)}/auth/token", {"client-id": acc.client_id, "client-secret": secret})
    tok = _find_token(data)
    if status >= 400 or not tok:
        raise GatewayUnavailable(code="gateway_auth_failed", message=f"KlickPay auth failed ({status})")
    cache.set(key, tok, TOKEN_SECONDS)
    return tok


def call(acc, path, body):
    status, data = _http("POST", f"{base_url(acc)}{path}", {"Authorization": f"Bearer {token(acc)}"}, body)
    if status == 401:
        status, data = _http("POST", f"{base_url(acc)}{path}", {"Authorization": f"Bearer {token(acc, fresh=True)}"}, body)
    if status >= 500:
        raise GatewayUnavailable(message=f"KlickPay error {status}")
    return status, data


def create_link(acc, *, reference, amount, client_name, client_email, client_phone, success, error, items) -> dict:
    status, data = call(acc, "/payments/general-link", {
        "client_name": client_name, "client_email": client_email, "client_phone": client_phone,
        "transction_reference": reference,          # sic: KlickPay's field name
        "transction_amount": float(amount), "success_page": success, "error_page": error, "source": "web_app",
        "transaction_details": {"total_items": len(items), "sub_total": float(amount), "discount": 0, "tax": 0,
                                "total": float(amount), "items": items}})
    d = data.get("data") or {}
    if status >= 400 or not data.get("success") or not d.get("payment_url") or not d.get("payment_id"):
        raise DomainError(code="gateway_link_failed", message=str(data.get("message") or status)[:200])
    return d


def payment_status(acc, gateway_id) -> dict:
    status, data = call(acc, "/payments/status", {"payment_id": gateway_id})
    if status >= 400 or not data.get("success"):
        raise GatewayUnavailable(code="gateway_status_failed", message=str(data.get("message") or status)[:200])
    return data.get("data") or {}


def refund(acc, gateway_id, amount, full: bool) -> tuple[str, dict]:
    """Returns (code, fields): REFUND_SUCCESS / INSUFFICIENT_BALANCE (stored as pending at KlickPay) / REFUND_FAILED."""
    body = {"payment_id": gateway_id} if full else {"payment_id": gateway_id, "refund_amount": f"{amount:.3f}"}
    status, data = call(acc, "/refunds/full" if full else "/refunds/partial", body)
    code = str(data.get("code") or ("REFUND_SUCCESS" if data.get("success") else "REFUND_FAILED"))
    return code, (data.get("data") or data.get("details") or {})
