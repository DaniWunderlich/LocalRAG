"""Upload ingress, controller validation and deployment settings use one byte limit."""

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from api_client import BackendClient, BackendError
from configuration import upload_limit
from workspace import Session


@pytest.mark.parametrize("configured", [1024, 32 * 1024 * 1024])
def test_configured_limit_is_published_by_gradio_and_used_for_new_sessions(
    monkeypatch: pytest.MonkeyPatch, configured: int
) -> None:
    from app import create_app

    monkeypatch.setenv("MAX_UPLOAD_BYTES", str(configured))
    with TestClient(create_app()) as client:
        assert client.get("/config").json()["max_file_size"] == configured
        assert Session().max_upload_bytes == configured


def test_upload_route_accepts_the_exact_limit_and_rejects_one_extra_byte(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app import create_app

    monkeypatch.setenv("MAX_UPLOAD_BYTES", "1024")
    with TestClient(create_app()) as client:
        response = client.post(
            "/gradio_api/upload", files={"files": ("boundary.txt", b"x" * 1024, "text/plain")}
        )
        assert response.status_code == 200 and len(response.json()) == 1
        response = client.post(
            "/gradio_api/upload", files={"files": ("too-large.txt", b"x" * 1025, "text/plain")}
        )
        assert response.status_code == 413


@pytest.mark.parametrize("value", ["0", "-1", "not-a-number"])
def test_invalid_limits_fail_before_serving_uploads(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("MAX_UPLOAD_BYTES", value)
    with pytest.raises(ValueError, match="positive integer"):
        upload_limit()


@pytest.mark.parametrize("body", [b"not-json", b"[]", b"null", b'"private upstream text"'])
def test_python314_error_response_fallback_also_catches_attribute_error(
    monkeypatch: pytest.MonkeyPatch, body: bytes
) -> None:
    real_client = httpx.Client
    transport = httpx.MockTransport(lambda request: httpx.Response(502, content=body))

    def client(**options: Any) -> httpx.Client:
        return real_client(transport=transport, **options)

    monkeypatch.setattr("api_client.httpx.Client", client)
    with pytest.raises(BackendError, match="could not complete the request"):
        BackendClient().models()
