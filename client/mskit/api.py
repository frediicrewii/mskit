"""Synchronous REST client for mskit server."""
import os
import ssl
from pathlib import Path
from typing import Optional
import httpx

from .config import Config


class ApiError(Exception):
    pass


def _build_verify():
    """Decide how to verify TLS.
    MSKIT_INSECURE=1         -> no verification (for corporate MITM firewalls)
    MSKIT_CA_BUNDLE=/path    -> use custom CA bundle (corporate root cert)
    default               -> use system / certifi
    """
    if os.environ.get("MSKIT_INSECURE", "").lower() in ("1", "true", "yes"):
        return False
    ca = os.environ.get("MSKIT_CA_BUNDLE")
    if ca:
        return ca
    return True


class Api:
    def __init__(self, config: Config):
        self.config = config
        self._client: Optional[httpx.Client] = None

    @property
    def client(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                base_url=self.config.server,
                timeout=15,
                verify=_build_verify(),
            )
        return self._client

    def _headers(self) -> dict:
        if self.config.token:
            return {"Authorization": f"Bearer {self.config.token}"}
        return {}

    def _handle(self, r: httpx.Response):
        if r.status_code == 401:
            raise ApiError("Unauthorized — run `mskit login` again")
        if not r.is_success:
            try:
                detail = r.json().get("detail", r.text)
            except Exception:
                detail = r.text or f"HTTP {r.status_code}"
            raise ApiError(str(detail))
        return r.json()

    # ---------- auth ----------
    def register(self, username: str, display_name: str, password: str) -> dict:
        r = self.client.post("/api/auth/register", json={
            "username": username, "display_name": display_name, "password": password,
        })
        return self._handle(r)

    def login(self, username: str, password: str) -> dict:
        r = self.client.post("/api/auth/login", json={
            "username": username, "password": password,
        })
        return self._handle(r)

    def me(self) -> dict:
        r = self.client.get("/api/auth/me", headers=self._headers())
        return self._handle(r)

    # ---------- users ----------
    def list_users(self) -> list:
        r = self.client.get("/api/users/", headers=self._headers())
        return self._handle(r)

    def get_user(self, username: str) -> dict:
        r = self.client.get(f"/api/users/by-username/{username}", headers=self._headers())
        return self._handle(r)

    # ---------- chats ----------
    def list_chats(self) -> list:
        r = self.client.get("/api/chats/", headers=self._headers())
        return self._handle(r)

    def open_personal(self, username: str) -> dict:
        r = self.client.post("/api/chats/personal", json={"username": username},
                             headers=self._headers())
        return self._handle(r)

    def create_group(self, name: str, usernames: list) -> dict:
        r = self.client.post("/api/chats/group",
                             json={"name": name, "usernames": usernames},
                             headers=self._headers())
        return self._handle(r)

    def find_group(self, name: str) -> dict:
        r = self.client.get("/api/chats/find-group", params={"name": name},
                            headers=self._headers())
        return self._handle(r)

    # ---------- messages ----------
    def get_messages(self, chat_id: int, limit: int = 50) -> list:
        r = self.client.get(f"/api/messages/{chat_id}", params={"limit": limit},
                            headers=self._headers())
        return self._handle(r)

    def get_messages_since(self, chat_id: int, after_id: int) -> list:
        r = self.client.get(f"/api/messages/{chat_id}/since/{after_id}",
                            headers=self._headers())
        return self._handle(r)

    def send_message(self, chat_id: int, content: Optional[str] = None,
                     file_url: Optional[str] = None,
                     file_name: Optional[str] = None,
                     file_type: Optional[str] = None) -> dict:
        payload = {"chat_id": chat_id}
        if content:
            payload["content"] = content
        if file_url:
            payload["file_url"] = file_url
            payload["file_name"] = file_name
            payload["file_type"] = file_type
        r = self.client.post("/api/messages/", json=payload, headers=self._headers())
        return self._handle(r)

    # ---------- files ----------
    def upload_file(self, path: Path) -> dict:
        if not path.exists():
            raise ApiError(f"File not found: {path}")
        size = path.stat().st_size
        if size > 50 * 1024 * 1024:
            raise ApiError("File too large (max 50 MB)")
        with path.open("rb") as f:
            files = {"file": (path.name, f, "application/octet-stream")}
            r = self.client.post("/api/upload", files=files, headers=self._headers())
        return self._handle(r)

    def resolve_file_url(self, url: str) -> str:
        """Convert /uploads/xxx to absolute URL pointing at server."""
        if url.startswith("http"):
            return url
        return self.config.server.rstrip("/") + url
