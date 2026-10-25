"""Módulo de S3 sin red: se reemplaza el cliente de boto3 por uno fake.

El fixture fake_storage de conftest.py reemplaza upload_image/delete_image en el módulo; acá se
importan las funciones originales antes de que lo haga.
"""

import pytest
from botocore.exceptions import ClientError

from app.exceptions import StorageUnavailableError
from app.services import storage

upload_image = storage.upload_image
delete_image = storage.delete_image


class FakeS3:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.put = []
        self.deleted = []

    def put_object(self, **kwargs):
        if self.fail:
            raise ClientError({"Error": {"Code": "AccessDenied", "Message": "no"}}, "PutObject")
        self.put.append(kwargs)

    def delete_object(self, **kwargs):
        if self.fail:
            raise ClientError({"Error": {"Code": "AccessDenied", "Message": "no"}}, "DeleteObject")
        self.deleted.append(kwargs)


@pytest.fixture
def s3(monkeypatch):
    fake = FakeS3()
    monkeypatch.setattr(storage, "_client", lambda: fake)
    monkeypatch.setattr(storage.settings, "s3_bucket", "media")
    monkeypatch.setattr(storage.settings, "aws_region", "us-east-1")
    monkeypatch.setattr(storage.settings, "s3_public_base_url", "")
    monkeypatch.setattr(storage.settings, "aws_access_key_id", "test-key")
    monkeypatch.setattr(storage.settings, "aws_secret_access_key", "test-secret")
    return fake


def test_upload_uses_unique_key_and_returns_public_url(s3):
    first = upload_image(b"img", "server-icons")
    second = upload_image(b"img", "server-icons")

    assert first != second
    assert first.startswith("https://media.s3.us-east-1.amazonaws.com/server-icons/")
    assert first.endswith(".webp")
    assert s3.put[0]["Bucket"] == "media"
    assert s3.put[0]["ContentType"] == "image/webp"
    assert first.endswith(s3.put[0]["Key"])


def test_upload_uses_custom_public_base_url(s3, monkeypatch):
    monkeypatch.setattr(storage.settings, "s3_public_base_url", "https://media.discordia.lol/")

    url = upload_image(b"img", "server-icons")

    assert url.startswith("https://media.discordia.lol/server-icons/")


@pytest.mark.parametrize("missing", ["s3_bucket", "aws_access_key_id", "aws_secret_access_key"])
def test_upload_without_config_fails_and_does_not_call_s3(s3, monkeypatch, missing):
    """Sin bucket o sin claves no se intenta subir (boto3 no sale a buscar credenciales a la EC2)."""
    monkeypatch.setattr(storage.settings, missing, "")

    with pytest.raises(StorageUnavailableError):
        upload_image(b"img", "server-icons")
    assert s3.put == []


def test_upload_s3_error_becomes_storage_unavailable(s3):
    s3.fail = True

    with pytest.raises(StorageUnavailableError):
        upload_image(b"img", "server-icons")


def test_delete_removes_own_image(s3):
    url = upload_image(b"img", "server-icons")

    delete_image(url)

    assert s3.deleted == [{"Bucket": "media", "Key": s3.put[0]["Key"]}]


@pytest.mark.parametrize("url", [None, "", "https://s.gravatar.com/avatar/abc.png", "https://evil.com/server-icons/x"])
def test_delete_ignores_foreign_urls(s3, url):
    delete_image(url)

    assert s3.deleted == []


def test_delete_never_raises(s3):
    url = upload_image(b"img", "server-icons")
    s3.fail = True

    delete_image(url)  # no lanza
