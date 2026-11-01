"""Service photos for the customer app: any common image in, one resized JPEG out (keeps the PWA light)."""
import io
import uuid

from django.core.files.base import ContentFile

from apps.core.errors import DomainError

MAX_IN = 8 * 1024 * 1024
SIDE = 900


def store(service, f):
    if f.size > MAX_IN:
        raise DomainError(code="image_too_big")
    from PIL import Image, ImageOps, UnidentifiedImageError
    try:
        img = Image.open(f)
        img = ImageOps.exif_transpose(img).convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise DomainError(code="image_invalid")
    img.thumbnail((SIDE, SIDE))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=82, optimize=True)
    if service.image:
        service.image.delete(save=False)
    service.image.save(f"{service.tenant_id}-{service.id}-{uuid.uuid4().hex[:8]}.jpg", ContentFile(out.getvalue()), save=False)
    service.image_version += 1
    service.save(update_fields=["image", "image_version"])
    return service


def remove(service):
    if service.image:
        service.image.delete(save=False)
    service.image = ""
    service.image_version += 1
    service.save(update_fields=["image", "image_version"])


def url(service) -> str:
    return f"/api/v1/public/services/{service.id}/image?v={service.image_version}" if service.image else ""
