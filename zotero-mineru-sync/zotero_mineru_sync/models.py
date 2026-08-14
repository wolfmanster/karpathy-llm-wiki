"""Strict versioned request/result protocol."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = 1
PROTOCOL_VERSION = "1"
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ProtocolError(ValueError):
    """The request cannot be safely interpreted by this version."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProtocolError(f"{field} must be a non-empty string")
    return value


def _version(value: Any, field: str) -> int:
    if type(value) is not int or value < 0:
        raise ProtocolError(f"{field} must be a non-negative integer")
    return value


def _identifier(value: Any, field: str) -> str:
    value = _text(value, field)
    if not _SAFE_IDENTIFIER.fullmatch(value):
        raise ProtocolError(f"{field} contains unsafe characters")
    return value


def validate_request(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict):
        raise ProtocolError("request must be a JSON object")
    if document.get("schema_version") != SCHEMA_VERSION:
        raise ProtocolError(f"unsupported schema_version: {document.get('schema_version')!r}")
    if document.get("protocol_version") != PROTOCOL_VERSION:
        raise ProtocolError(f"unsupported protocol_version: {document.get('protocol_version')!r}")
    _identifier(document.get("request_id"), "request_id")
    _identifier(document.get("library_id"), "library_id")
    for field in ("generated_at", "plugin_generation"):
        _text(document.get(field), field)
    candidates = document.get("candidates")
    if not isinstance(candidates, list):
        raise ProtocolError("candidates must be a list")
    _validate_items(candidates, "candidates", require_eligible=True)
    blocked = document.get("blocked_duplicates", [])
    if not isinstance(blocked, list):
        raise ProtocolError("blocked_duplicates must be a list")
    _validate_items(blocked, "blocked_duplicates", require_eligible=False)
    removed = document.get("removed_attachments", [])
    if not isinstance(removed, list):
        raise ProtocolError("removed_attachments must be a list")
    _validate_removed_attachments(removed)
    return document


def _validate_items(items: list[Any], name: str, *, require_eligible: bool) -> None:
    for index, item in enumerate(items):
        prefix = f"{name}[{index}]"
        if not isinstance(item, dict):
            raise ProtocolError(f"{prefix} must be an object")
        _identifier(item.get("parent_item_key"), f"{prefix}.parent_item_key")
        _version(item.get("parent_item_version"), f"{prefix}.parent_item_version")
        _identifier(item.get("attachment_key"), f"{prefix}.attachment_key")
        _version(item.get("attachment_version"), f"{prefix}.attachment_version")
        if require_eligible and item.get("eligible") is not True:
            raise ProtocolError(f"{prefix}.eligible must be true")
        if not require_eligible and "eligible" in item and type(item["eligible"]) is not bool:
            raise ProtocolError(f"{prefix}.eligible must be boolean")
        if "force" in item and type(item["force"]) is not bool:
            raise ProtocolError(f"{prefix}.force must be boolean")
        if "language" in item and not isinstance(item["language"], str):
            raise ProtocolError(f"{prefix}.language must be a string")


def _validate_removed_attachments(items: list[Any]) -> None:
    for index, item in enumerate(items):
        prefix = f"removed_attachments[{index}]"
        if not isinstance(item, dict):
            raise ProtocolError(f"{prefix} must be an object")
        _identifier(item.get("parent_item_key"), f"{prefix}.parent_item_key")
        _identifier(item.get("attachment_key"), f"{prefix}.attachment_key")


def result_document(request: dict[str, Any], entries: list[dict[str, Any]], status: str | None = None) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for entry in entries:
        key = str(entry.get("status", "FAILED"))
        counts[key] = counts.get(key, 0) + 1
    if status is None:
        status = "FAILED" if counts.get("FAILED", 0) else "COMPLETED"
    return {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "request_id": request.get("request_id", "unknown"),
        "generated_at": utc_now(),
        "library_id": request.get("library_id", "unknown"),
        "plugin_generation": request.get("plugin_generation", "unknown"),
        "status": status,
        "counts": counts,
        "entries": entries,
    }
