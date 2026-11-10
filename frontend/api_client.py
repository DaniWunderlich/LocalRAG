"""HTTP transport for the Streamlit UI; all RAG logic belongs to the backend."""

import os
from typing import Any

import httpx


class BackendError(Exception):
    """An actionable error that may be displayed in the browser."""


class BackendClient:
    """Make bounded requests without keeping business data in the frontend."""

    def __init__(self) -> None:
        self.base_url = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")
        self.timeout = float(os.environ.get("BACKEND_TIMEOUT_SECONDS", "600"))

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Translate network and API failures into messages safe for display."""
        try:
            with httpx.Client(
                base_url=self.base_url, timeout=self.timeout, trust_env=False
            ) as client:
                response = client.request(method, path, **kwargs)
                if response.is_error:
                    try:
                        detail = response.json().get("detail")
                    except ValueError, AttributeError:
                        detail = None
                    raise BackendError(
                        detail
                        if isinstance(detail, str)
                        else "The backend could not complete the request."
                    )
                return response.json() if response.content else None
        except httpx.HTTPError as exc:
            raise BackendError(
                "The backend is unavailable or the operation timed out. "
                "Check Documents before retrying an upload."
            ) from exc

    def models(self) -> dict[str, Any]:
        """Return available chat models together with backend defaults."""
        result: dict[str, Any] = self.request("GET", "/api/v1/models")
        return result

    def documents(self) -> list[dict[str, Any]]:
        """Retrieve the current register, including unsuccessful uploads."""
        result: list[dict[str, Any]] = self.request("GET", "/api/v1/documents")
        return result

    def upload(self, filename: str, data: bytes, content_type: str) -> dict[str, Any]:
        """Wait for synchronous indexing of an original document."""
        result: dict[str, Any] = self.request(
            "POST",
            "/api/v1/documents",
            files={"file": (filename, data, content_type)},
        )
        return result

    def delete(self, document_id: str) -> None:
        """Remove an original and its complete vector index."""
        self.request("DELETE", f"/api/v1/documents/{document_id}")

    def search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        """Inspect retrieval independently of the chat model."""
        result: list[dict[str, Any]] = self.request(
            "POST",
            "/api/v1/search",
            json={"query": query, "top_k": top_k},
        )
        return result

    def chat(self, message: str, model: str, top_k: int, temperature: float) -> dict[str, Any]:
        """Ask a stateless document question using the session preferences."""
        result: dict[str, Any] = self.request(
            "POST",
            "/api/v1/chat",
            json={
                "message": message,
                "model": model,
                "top_k": top_k,
                "temperature": temperature,
            },
        )
        return result

    def conversations(self) -> list[dict[str, Any]]:
        """List saved threads without transferring their transcripts."""
        result: list[dict[str, Any]] = self.request("GET", "/api/v1/conversations")
        return result

    def conversation(self, conversation_id: str) -> dict[str, Any]:
        """Restore one conversation and its independently saved preferences."""
        result: dict[str, Any] = self.request("GET", f"/api/v1/conversations/{conversation_id}")
        return result

    def create_conversation(self, model: str, top_k: int, temperature: float) -> dict[str, Any]:
        """Create a new durable conversation with explicit initial defaults."""
        result: dict[str, Any] = self.request(
            "POST",
            "/api/v1/conversations",
            json={
                "model": model,
                "top_k": top_k,
                "temperature": temperature,
            },
        )
        return result

    def update_conversation(self, conversation_id: str, **fields: Any) -> dict[str, Any]:
        """Change only the selected conversation's supplied fields."""
        result: dict[str, Any] = self.request(
            "PATCH",
            f"/api/v1/conversations/{conversation_id}",
            json=fields,
        )
        return result

    def delete_conversation(self, conversation_id: str) -> None:
        """Remove one thread and its unshared private attachments."""
        self.request("DELETE", f"/api/v1/conversations/{conversation_id}")

    def attachments(self, conversation_id: str) -> list[dict[str, Any]]:
        """Return the saved attachments of the selected conversation."""
        result: list[dict[str, Any]] = self.request(
            "GET",
            f"/api/v1/conversations/{conversation_id}/documents",
        )
        return result

    def upload_attachment(
        self,
        conversation_id: str,
        filename: str,
        data: bytes,
        content_type: str,
    ) -> dict[str, Any]:
        """Index or reuse a file within this chat's private evidence scope."""
        result: dict[str, Any] = self.request(
            "POST",
            f"/api/v1/conversations/{conversation_id}/documents",
            files={"file": (filename, data, content_type)},
        )
        return result

    def detach(self, conversation_id: str, document_id: str) -> None:
        """Remove an attachment link and any unshared private original."""
        self.request(
            "DELETE",
            f"/api/v1/conversations/{conversation_id}/documents/{document_id}",
        )

    def send_message(
        self,
        conversation_id: str,
        message: str,
        request_id: str,
    ) -> dict[str, Any]:
        """Idempotently submit one question using the saved chat settings."""
        result: dict[str, Any] = self.request(
            "POST",
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"message": message, "request_id": request_id},
        )
        return result

    def import_conversation(
        self,
        conversation_id: str,
        messages: list[dict[str, Any]],
        model: str,
        top_k: int,
        temperature: float,
    ) -> dict[str, Any]:
        """Preserve a session-only transcript without regenerating its answers."""
        result: dict[str, Any] = self.request(
            "POST",
            "/api/v1/conversations/import",
            json={
                "conversation_id": conversation_id,
                "messages": messages,
                "model": model,
                "top_k": top_k,
                "temperature": temperature,
            },
        )
        return result
