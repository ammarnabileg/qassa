"""Opening a salon's KlickPay merchant account through the platform (we act as KlickPay's agent): the salon uploads
the documents, the platform accepts or rejects each one with a note, then enters the credentials KlickPay issued."""
from django.db import transaction
from django.utils import timezone

from apps.core.errors import DomainError
from apps.payments.models import GatewayAccount, KycDocument, KycDocumentType

ALLOWED = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
MAX_BYTES = 8 * 1024 * 1024


def account() -> GatewayAccount:
    return GatewayAccount.objects.first() or GatewayAccount.objects.create()


def ensure_types():
    """The starting list (migration 0002) if the table is empty, e.g. after a data reset."""
    if not KycDocumentType.objects.filter(stage=KycDocumentType.Stage.KYC).exists():
        import importlib
        mig = importlib.import_module("apps.payments.migrations.0002_kyc_types_and_integrity")
        for i, (code, ar, en, har, hen) in enumerate(mig.DEFAULT_TYPES):
            KycDocumentType.objects.get_or_create(code=code, defaults=dict(name_ar=ar, name_en=en, help_ar=har, help_en=hen, sort=i,
                                                                           required=code != "signatory"))
    if not KycDocumentType.objects.filter(code="signed_contract").exists():
        KycDocumentType.objects.get_or_create(code="signed_contract", defaults=dict(
            stage="contract", name_ar="عقد KlickPay موقّع", name_en="Signed KlickPay contract", required=True, sort=100,
            help_ar="نزّل العقد، وقّعه واختمه، وارفعه هنا", help_en="Download the contract, sign and stamp it, upload it here"))


def checklist(acc=None):
    """KYC documents, plus the signed contract once the platform has sent the contract."""
    ensure_types()
    acc = acc or GatewayAccount.objects.first()
    current = {d.doc_type_id: d for d in KycDocument.objects.filter(is_current=True)}
    types = KycDocumentType.objects.filter(is_active=True).order_by("sort", "id")
    if not (acc and acc.contract_sent_at):
        types = types.filter(stage=KycDocumentType.Stage.KYC)
    return [(t, current.get(t.id)) for t in types]


def upload(doc_type_id, f, user) -> KycDocument:
    acc = account()
    t = KycDocumentType.objects.filter(id=doc_type_id, is_active=True).first()
    if t is None:
        raise DomainError(code="kyc_type_unknown")
    contract = t.stage == KycDocumentType.Stage.CONTRACT
    if contract and acc.status != GatewayAccount.Status.CONTRACT:
        raise DomainError(code="kyc_locked")   # the signed contract only after the platform sent the contract
    if not contract and acc.status in {GatewayAccount.Status.UNDER_REVIEW, GatewayAccount.Status.ACTIVE, GatewayAccount.Status.CONTRACT}:
        raise DomainError(code="kyc_locked")   # under review / active: nothing to change from the salon side
    name = (f.name or "").lower()
    if not any(name.endswith(x) for x in ALLOWED):
        raise DomainError(code="kyc_file_type")
    if f.size > MAX_BYTES:
        raise DomainError(code="kyc_file_too_big")
    with transaction.atomic():
        KycDocument.objects.filter(doc_type=t, is_current=True).update(is_current=False)
        doc = KycDocument.objects.create(doc_type=t, file=f, original_name=f.name[:200], uploaded_by=user)
        if acc.status == GatewayAccount.Status.NOT_STARTED:
            acc.status = GatewayAccount.Status.COLLECTING
            acc.save(update_fields=["status", "updated_at"])
        if contract:   # signed contract back: the platform reviews it
            acc.status = GatewayAccount.Status.UNDER_REVIEW
            acc.save(update_fields=["status", "updated_at"])
    return doc


def submit(user) -> GatewayAccount:
    acc = account()
    if acc.status not in {GatewayAccount.Status.COLLECTING, GatewayAccount.Status.NEEDS_CHANGES}:
        raise DomainError(code="kyc_cannot_submit")
    missing = [t.code for t, d in checklist(acc) if t.stage == KycDocumentType.Stage.KYC and t.required
               and (d is None or d.status == KycDocument.Status.REJECTED)]
    if missing:
        raise DomainError(code="kyc_missing_documents", details={"missing": missing})
    acc.status, acc.submitted_at, acc.review_note = GatewayAccount.Status.UNDER_REVIEW, timezone.now(), ""
    acc.save(update_fields=["status", "submitted_at", "review_note", "updated_at"])
    return acc


def review(doc: KycDocument, accept: bool, note: str):
    if not accept and not note.strip():
        raise DomainError(code="kyc_note_required")
    doc.status = KycDocument.Status.ACCEPTED if accept else KycDocument.Status.REJECTED
    doc.note, doc.reviewed_at = note.strip()[:500], timezone.now()
    doc.save(update_fields=["status", "note", "reviewed_at"])


def send_contract(acc, f, user):
    """The contract KlickPay issued, uploaded by the platform for the salon to download, sign and upload back."""
    name = (f.name or "").lower()
    if not any(name.endswith(x) for x in ALLOWED) or f.size > MAX_BYTES:
        raise DomainError(code="kyc_file_type")
    acc.contract_file, acc.contract_name, acc.contract_sent_at = f, f.name[:200], timezone.now()
    acc.status = GatewayAccount.Status.CONTRACT
    acc.save()
    KycDocument.objects.filter(doc_type__code="signed_contract", is_current=True).update(is_current=False)   # a new contract: sign again
    return acc


def contract_ok(acc) -> bool:
    if not acc.contract_sent_at:
        return True
    return KycDocument.objects.filter(doc_type__code="signed_contract", is_current=True, status=KycDocument.Status.ACCEPTED).exists()


def officer_message(acc, tenant, links) -> str:
    lines = [f"طلب فتح حساب KlickPay — {tenant.name} ({tenant.slug})", ""]
    lines += [f"• {name}: {url}" for name, url in links]
    lines += ["", "اللينكات صالحة 7 أيام."]
    return "\n".join(lines)
