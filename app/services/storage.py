"""Imágenes públicas en S3 (mismo módulo que Auth-User-Service, ver ADR-003)."""

import logging
import uuid
from functools import lru_cache

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings
from app.exceptions import StorageUnavailableError

logger = logging.getLogger(__name__)

# Cada subida usa una clave nueva, así que el archivo nunca cambia y se puede cachear para siempre
_CACHE_CONTROL = "public, max-age=31536000, immutable"


@lru_cache
def _client():
    return boto3.client("s3", region_name=settings.aws_region)


def _public_base_url() -> str:
    base = settings.s3_public_base_url or f"https://{settings.s3_bucket}.s3.{settings.aws_region}.amazonaws.com"
    return base.rstrip("/")


def upload_image(contents: bytes, prefix: str, content_type: str = "image/webp") -> str:
    """Sube la imagen con una clave única dentro de `prefix` y devuelve su URL pública."""
    if not settings.s3_bucket:
        raise StorageUnavailableError("Image storage is not configured.")

    key = f"{prefix}/{uuid.uuid4().hex}.webp"
    try:
        _client().put_object(
            Bucket=settings.s3_bucket,
            Key=key,
            Body=contents,
            ContentType=content_type,
            CacheControl=_CACHE_CONTROL,
        )
    except (BotoCoreError, ClientError) as exc:
        logger.exception("S3 upload failed for key %s", key)
        raise StorageUnavailableError() from exc

    return f"{_public_base_url()}/{key}"


def delete_image(url: str | None) -> None:
    """Borra una imagen subida por este módulo. Ignora URLs ajenas (Auth0, Gravatar) y no falla nunca:
    si el borrado no sale, el objeto queda huérfano pero el usuario no ve un error."""
    base = _public_base_url() + "/"
    if not url or not settings.s3_bucket or not url.startswith(base):
        return

    key = url[len(base):]
    try:
        _client().delete_object(Bucket=settings.s3_bucket, Key=key)
    except (BotoCoreError, ClientError):
        logger.warning("S3 delete failed for key %s", key, exc_info=True)
