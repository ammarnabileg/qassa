"""Offline selling (D-013).

The browser keeps a snapshot of prices, products, packages, coupons, loyalty settings and customers, and sells
from it while the internet is down. Each receipt gets the device's next sequence number and an HMAC-SHA256
signature made with the device's secret. When the connection returns the receipts are posted here in order:

* a receipt is posted at most once (unique uuid, unique device+seq) — resending is safe;
* the signature proves the receipt came unchanged from that registered device;
* the invoice keeps what the customer actually paid: if a coupon, points or a package session were no longer
  valid when the receipt arrived (e.g. used meanwhile on another device), the same amount is kept as a discount
  and the receipt goes to REVIEW for a manager — it is never silently changed or dropped;
* what cannot be posted (stock missing, closed period…) stays in CONFLICT and can be retried after fixing;
* a missing sequence number means a receipt was lost or deleted from that browser — shown to managers.
"""
import hashlib
import hmac
import json
import secrets
import uuid as uuidlib
from datetime import datetime, timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.services.log import record as audit
from apps.core.errors import DomainError
from apps.core.money import allocate, money
from apps.pos.models import OfflineSale, PosDevice
from apps.pos.services import sales

PROMO_ERRORS = {"coupon_invalid", "coupon_used_up", "coupon_min_total", "points_insufficient", "points_below_minimum",
                "loyalty_disabled", "points_need_customer", "package_used_up", "package_expired", "package_unknown"}
MAX_AGE = timedelta(days=7)        # an offline receipt older than this is refused (clock tampering / forgotten tablet)


class _Mismatch(Exception):
    def __init__(self, total):
        self.total = total


def canonical(payload: dict) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sign(secret: str, payload: dict) -> str:
    return hmac.new(secret.encode(), canonical(payload), hashlib.sha256).hexdigest()


def register_device(*, branch, name: str, user) -> PosDevice:
    d = PosDevice.objects.create(branch=branch, name=name.strip()[:60] or "POS", secret=secrets.token_hex(32), registered_by=user)
    audit("pos.device_registered", tenant_id=d.tenant_id, actor=user, obj=d, data={"branch": branch.id, "name": d.name})
    return d


def bundle(branch, membership) -> dict:
    """Everything the till needs to sell without internet, priced for today's business day."""
    from apps.catalog.models import Service
    from apps.catalog.services.pricing import price_on
    from apps.core.dates import business_date
    from apps.customers.models import Customer
    from apps.inventory.models import Product, StockLevel
    from apps.loyalty.models import Coupon, CustomerPackage, LoyaltySettings, PackagePlan
    from apps.loyalty.services import points
    from apps.staff.models import StaffMember
    today = business_date()
    services = []
    for s in Service.objects.select_related("category").filter(is_active=True, category__business_type=branch.business_type):
        p = price_on(s, branch.id, today)
        if p is not None:
            services.append({"id": s.id, "name_ar": s.name_ar, "name_en": s.name_en, "price": str(p), "category": s.category.name_ar})
    stock = dict(StockLevel.objects.filter(branch=branch).values_list("product_id", "qty"))
    products = [{"id": p.id, "name_ar": p.name_ar, "name_en": p.name_en, "price": str(p.sale_price), "qty": str(stock.get(p.id, 0))}
                for p in Product.objects.filter(is_active=True, kind="retail", sale_price__isnull=False)]
    plans = [{"id": p.id, "name_ar": p.name_ar, "name_en": p.name_en, "price": str(p.price), "sessions": p.sessions, "service_id": p.service_id}
             for p in PackagePlan.objects.select_related("service__category").filter(is_active=True, service__category__business_type=branch.business_type)]
    coupons = [{"code": c.code, "kind": c.kind, "value": str(c.value), "min_total": str(c.min_total),
                "left": None if c.max_uses is None else max(0, c.max_uses - c.used_count)}
               for c in Coupon.objects.filter(is_active=True, valid_from__lte=today, valid_to__gte=today)]
    cfg = LoyaltySettings.objects.first()
    pkgs = {}
    for k in CustomerPackage.objects.filter(voided=False, sessions_left__gt=0, expires_on__gte=today):
        pkgs.setdefault(k.customer_id, []).append({"id": k.id, "service_id": k.service_id, "sessions_left": k.sessions_left,
                                                   "session_value": str(k.session_value), "name_ar": k.plan.name_ar if k.plan_id else ""})
    customers = [{"id": c.id, "full_name": c.full_name, "phone": c.phone, "points": points.balance(c) if cfg and cfg.enabled else 0,
                  "packages": pkgs.get(c.id, []), "beneficiaries": [{"id": b.id, "full_name": b.full_name} for b in c.beneficiaries.all()]}
                 for c in Customer.objects.prefetch_related("beneficiaries").filter(is_active=True).order_by("-id")[:5000]]
    staff = [{"id": s.id, "name_ar": s.full_name_ar, "name_en": s.full_name_en}
             for s in StaffMember.objects.filter(is_active=True, branch_links__branch=branch).distinct()]
    return {"generated_at": timezone.now().isoformat(), "business_date": today.isoformat(), "branch_id": branch.id,
            "services": services, "products": products, "plans": plans, "coupons": coupons, "staff": staff, "customers": customers,
            "loyalty": {"enabled": bool(cfg and cfg.enabled), "point_value": str(cfg.point_value) if cfg else "0",
                        "min_redeem": cfg.min_redeem if cfg else 0},
            "discount_limit_percent": str(membership.discount_limit_percent)}


def _checkout_in(device, p):
    return sales.CheckoutIn(
        branch=device.branch, lines=[sales.LineIn(**{k: v for k, v in x.items() if k in sales.LineIn.__dataclass_fields__}) for x in p["lines"]],
        payments=[sales.PaymentIn(**x) for x in p["payments"]], customer_id=p.get("customer_id"), beneficiary_id=p.get("beneficiary_id"),
        coupon_code=p.get("coupon_code", ""), redeem_points=int(p.get("redeem_points") or 0),
        tip=Decimal(str(p.get("tip") or 0)), tip_staff_id=p.get("tip_staff_id"))


def _post(device, sale_payload, at, ref, user, membership):
    """Post the receipt; if a promotion is no longer valid, keep the paid amount as a discount and flag it."""
    expected = money(sale_payload["total"])
    ctx = sales.OfflineCtx(at=at, ref=ref)
    try:
        with transaction.atomic():
            inv = sales.checkout(_checkout_in(device, sale_payload), user=user, membership=membership, offline=ctx)
            if inv.total != expected:
                raise _Mismatch(inv.total)
            return inv, ctx.flags
    except (DomainError, _Mismatch) as e:
        code = getattr(e, "code", None)
        if isinstance(e, DomainError) and code not in PROMO_ERRORS:
            raise
        reason = code or f"total_differs:{e.total}"
    # fallback: same lines and prices, no coupon / points — the promotion amount becomes a reviewed discount
    p = dict(sale_payload)
    p["coupon_code"], p["redeem_points"] = "", 0
    lines = [dict(x) for x in p["lines"]]
    from apps.core.dates import business_date
    from apps.loyalty.models import CustomerPackage
    day = business_date(at)
    for x in lines:
        if not x.get("redeem_package_id"):
            continue
        pkg = CustomerPackage.objects.filter(id=x["redeem_package_id"], customer_id=p.get("customer_id"), voided=False).first()
        still_ok = pkg is not None and pkg.sessions_left >= int(x.get("qty", 1)) and pkg.expires_on >= day
        if not still_ok:
            # the session was used up meanwhile (e.g. on another device): the visit stays free, as charged, for review
            x.pop("redeem_package_id")
            x["discount"] = str(money(Decimal(str(x["unit_price"])) * int(x.get("qty", 1))))
    def net(x):
        return money(Decimal(str(x["unit_price"])) * int(x.get("qty", 1))) - money(Decimal(str(x.get("discount") or 0)))
    payable = [x for x in lines if not x.get("redeem_package_id") and net(x) > 0]
    gross = [net(x) for x in payable]
    extra = money(sum(gross, Decimal("0")) - expected)
    if extra < 0 or (extra > 0 and not payable):
        raise DomainError(code="offline_total_invalid")
    if extra > 0:
        for x, share in zip(payable, allocate(extra, gross)):
            x["discount"] = str(money(Decimal(str(x.get("discount") or 0)) + share))
    p["lines"] = lines
    ctx = sales.OfflineCtx(at=at, ref=ref, flags=[f"promotion_not_honoured:{reason}"])
    with transaction.atomic():
        inv = sales.checkout(_checkout_in(device, p), user=user, membership=membership, offline=ctx)
        if inv.total != expected:
            raise DomainError(code="offline_total_invalid", details={"server": str(inv.total), "paid": str(expected)})
    return inv, ctx.flags


def receive(device: PosDevice, item: dict, *, user, membership) -> OfflineSale:
    """Store and post one offline receipt. Idempotent on uuid."""
    payload = item["payload"]
    if not hmac.compare_digest(sign(device.secret, payload), str(item.get("signature", ""))):
        raise DomainError(code="offline_signature_invalid")
    sale_uuid = uuidlib.UUID(str(payload["uuid"]))
    existing = OfflineSale.objects.filter(uuid=sale_uuid).first()
    if existing:
        return existing
    at = datetime.fromisoformat(payload["created_at"])
    if timezone.is_naive(at):
        raise DomainError(code="offline_time_invalid")
    now = timezone.now()
    if at > now + timedelta(minutes=5) or at < now - MAX_AGE:
        raise DomainError(code="offline_time_invalid")
    ref = f"OFF-{device.id}-{int(payload['seq'])}"
    status, flags, error, inv = OfflineSale.Status.SYNCED, [], "", None
    try:
        inv, flags = _post(device, payload, at, ref, user, membership)
        if flags:
            status = OfflineSale.Status.REVIEW
    except DomainError as e:
        status, error = OfflineSale.Status.CONFLICT, (e.code or "error")[:60]
    try:
        with transaction.atomic():
            sale = OfflineSale.objects.create(device=device, uuid=sale_uuid, seq=int(payload["seq"]), created_at_client=at,
                                              payload=payload, signature=item["signature"], status=status, flags=flags,
                                              error=error, invoice=inv, cashier=user)
    except IntegrityError:
        raise DomainError(code="offline_seq_reused")
    audit("pos.offline_sale", tenant_id=sale.tenant_id, actor=user, obj=sale,
          data={"ref": ref, "status": status, "flags": flags, "error": error, "invoice": inv.number if inv else None})
    return sale


def retry(sale: OfflineSale, *, user, membership) -> OfflineSale:
    if sale.status != OfflineSale.Status.CONFLICT:
        raise DomainError(code="offline_not_conflict")
    try:
        inv, flags = _post(sale.device, sale.payload, sale.created_at_client, f"OFF-{sale.device_id}-{sale.seq}", user, membership)
    except DomainError as e:
        OfflineSale.objects.filter(id=sale.id).update(error=(e.code or "error")[:60])
        sale.refresh_from_db()
        return sale
    OfflineSale.objects.filter(id=sale.id).update(invoice=inv, flags=flags, error="",
                                                  status=OfflineSale.Status.REVIEW if flags else OfflineSale.Status.SYNCED)
    sale.refresh_from_db()
    audit("pos.offline_sale_retried", tenant_id=sale.tenant_id, actor=user, obj=sale, data={"status": sale.status})
    return sale


def acknowledge(sale: OfflineSale, *, user) -> OfflineSale:
    if sale.status != OfflineSale.Status.REVIEW:
        raise DomainError(code="offline_not_review")
    OfflineSale.objects.filter(id=sale.id).update(status=OfflineSale.Status.SYNCED, reviewed_by=user, reviewed_at=timezone.now())
    audit("pos.offline_sale_reviewed", tenant_id=sale.tenant_id, actor=user, obj=sale, data={"flags": sale.flags})
    sale.refresh_from_db()
    return sale


def gaps(device: PosDevice) -> list[int]:
    """Sequence numbers never received: receipts lost or deleted from that browser."""
    seqs = sorted(OfflineSale.objects.filter(device=device).values_list("seq", flat=True))
    if not seqs:
        return []
    have = set(seqs)
    return [n for n in range(1, seqs[-1] + 1) if n not in have][:100]
