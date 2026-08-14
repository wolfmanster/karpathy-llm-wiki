"""The only version-sensitive Zotero Local API boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen


class ZoteroApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ZoteroRelationError(ZoteroApiError):
    """The requested attachment is no longer a child of the parent."""


class ZoteroLocalApi:
    def __init__(self, base_url: str = "http://127.0.0.1:23119/api", storage_root: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.storage_root = Path(storage_root).expanduser() if storage_root else None

    def get_json(self, path: str) -> Any:
        request = Request(f"{self.base_url}/{path.lstrip('/')}", headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise ZoteroApiError(f"Local API request failed for {path}: {exc}", status_code=exc.code) from exc
        except (URLError, TimeoutError, ValueError) as exc:
            raise ZoteroApiError(f"Local API request failed for {path}: {exc}") from exc

    def get_text(self, path: str) -> str:
        request = Request(f"{self.base_url}/{path.lstrip('/')}", headers={"Accept": "text/plain"})
        try:
            with urlopen(request, timeout=10) as response:
                return response.read().decode("utf-8").strip()
        except HTTPError as exc:
            raise ZoteroApiError(f"Local API request failed for {path}: {exc}", status_code=exc.code) from exc
        except (URLError, TimeoutError, UnicodeError) as exc:
            raise ZoteroApiError(f"Local API request failed for {path}: {exc}") from exc

    def get_item(self, key: str) -> dict[str, Any]:
        value = self.get_json(f"users/0/items/{quote(key, safe='')}")
        if not isinstance(value, dict):
            raise ZoteroApiError(f"invalid item response for {key}")
        return value

    def get_attachment(self, parent_key: str, attachment_key: str) -> dict[str, Any]:
        value = self.get_item(attachment_key)
        data = value.get("data")
        if not isinstance(data, dict) or data.get("parentItem") != parent_key:
            raise ZoteroRelationError(f"attachment {attachment_key} is not a child of {parent_key}")
        return value

    def resolve_pdf_path(self, attachment: dict[str, Any]) -> Path | None:
        data = attachment.get("data")
        if not isinstance(data, dict):
            return None
        raw = data.get("path")
        if not isinstance(raw, str) or not raw:
            key = data.get("key") or attachment.get("key")
            if not isinstance(key, str) or not key:
                return None
            try:
                raw = self.get_text(f"users/0/items/{quote(key, safe='')}/file/view/url")
            except ZoteroApiError:
                return None
        if not raw:
            return None
        if raw.startswith("attachments:") or (raw.startswith("storage:") and self.storage_root is None):
            key = data.get("key") or attachment.get("key")
            if not isinstance(key, str) or not key:
                return None
            try:
                raw = self.get_text(f"users/0/items/{quote(key, safe='')}/file/view/url")
            except ZoteroApiError:
                return None
        if raw.startswith("file://"):
            parsed = urlparse(raw)
            path_text = unquote(parsed.path)
            if parsed.netloc:
                path_text = f"//{parsed.netloc}{path_text}"
            elif len(path_text) >= 3 and path_text[0] == "/" and path_text[2] == ":":
                path_text = path_text[1:]
            return Path(path_text).expanduser().resolve()
        if raw.startswith("storage:") and self.storage_root is not None:
            key = data.get("key") or attachment.get("key")
            if not isinstance(key, str) or not key:
                return None
            attachment_root = (self.storage_root / key).resolve()
            relative_path = raw.removeprefix("storage:").replace("\\", "/")
            candidate = (attachment_root / relative_path).resolve()
            if not candidate.is_relative_to(attachment_root):
                raise ZoteroApiError("attachment path escapes Zotero storage")
            return candidate
        return Path(raw).expanduser().resolve()
