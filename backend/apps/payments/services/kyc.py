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


def checklist():
    current = {d.doc_type_id: d for d in KycDocument.objects.filter(is_current=True)}
    return [(t, current.get(t.id)) for t in KycDocumentType.objects.filter(is_active=True).order_by("sort", "id")]


def upload(doc_type_id, f, user) -> KycDocument:
    acc = account()
    if acc.status in {GatewayAccount.Status.UNDER_REVIEW, GatewayAccount.Status.ACTIVE}:
        raise DomainError(code="kyc_locked")   # under review / active: nothing to change from the salon side
    t = KycDocumentType.objects.filter(id=doc_type_id, is_active=True).first()
    if t is None:
        raise DomainError(code="kyc_type_unknown")
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
    return doc


def submit(user) -> GatewayAccount:
    acc = account()
    if acc.status not in {GatewayAccount.Status.COLLECTING, GatewayAccount.Status.NEEDS_CHANGES}:
        raise DomainError(code="kyc_cannot_submit")
    missing = [t.code for t, d in checklist() if t.required and (d is None or d.status == KycDocument.Status.REJECTED)]
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
