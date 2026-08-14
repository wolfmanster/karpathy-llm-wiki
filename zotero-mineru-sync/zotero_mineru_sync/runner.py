"""Process exactly one request, then exit."""

from __future__ import annotations

import json
import os
import traceback
from pathlib import Path
from typing import Any, Callable

from .lock import SyncLock
from .local_api import ZoteroApiError, ZoteroRelationError
from .mineru_adapter import convert_document
from .models import ProtocolError, result_document, utc_now, validate_request
from .paths import SyncPaths
from .state import StateStore


class CandidateDecisionError(ValueError):
    """A candidate is safely classifiable without invoking MinerU."""

    def __init__(self, status: str, reason: str):
        super().__init__(reason)
        self.status = status


class SyncRunner:
    def __init__(self, paths: SyncPaths, api: Any, converter: Callable[..., Any] = convert_document):
        self.paths = paths
        self.api = api
        self.converter = converter

    @staticmethod
    def _entry(item: dict[str, Any], **values: Any) -> dict[str, Any]:
        return {"parent_item_key": item["parent_item_key"], "attachment_key": item["attachment_key"], **values}

    def _atomic_json(self, path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, path)

    def _request(self, path: Path) -> dict[str, Any]:
        try:
            return validate_request(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ProtocolError(f"cannot read request JSON: {exc}") from exc

    @staticmethod
    def _library_id(payload: dict[str, Any], data: dict[str, Any]) -> Any:
        if data.get("libraryID") is not None:
            return data["libraryID"]
        library = payload.get("library")
        return library.get("id") if isinstance(library, dict) else None

    def _current(self, item: dict[str, Any], library_id: str) -> tuple[Path, dict[str, Any]]:
        try:
            parent = self.api.get_item(item["parent_item_key"])
            attachment = self.api.get_attachment(item["parent_item_key"], item["attachment_key"])
        except ZoteroRelationError as exc:
            raise CandidateDecisionError("SKIPPED", str(exc)) from exc
        except ZoteroApiError as exc:
            if exc.status_code == 404:
                raise CandidateDecisionError("SKIPPED", "Zotero item or attachment was deleted") from exc
            raise
        if parent is None or attachment is None:
            raise CandidateDecisionError("SKIPPED", "Zotero item or attachment was deleted")
        parent_data = parent.get("data")
        attachment_data = attachment.get("data")
        if not isinstance(parent_data, dict) or not isinstance(attachment_data, dict):
            raise ValueError("malformed Zotero Local API response")
        parent_library = self._library_id(parent, parent_data)
        attachment_library = self._library_id(attachment, attachment_data)
        if str(parent_library) != str(library_id):
            raise CandidateDecisionError("STALE", "parent library mismatch")
        if str(attachment_library) != str(library_id):
            raise CandidateDecisionError("STALE", "attachment library mismatch")
        if parent_data.get("key") != item["parent_item_key"] or parent_data.get("version") != item["parent_item_version"]:
            raise CandidateDecisionError("STALE", "parent item snapshot is stale")
        if attachment_data.get("key") != item["attachment_key"] or attachment_data.get("version") != item["attachment_version"]:
            raise CandidateDecisionError("STALE", "attachment snapshot is stale")
        if attachment_data.get("parentItem") != item["parent_item_key"]:
            raise CandidateDecisionError("SKIPPED", "attachment parent mismatch")
        if str(attachment_data.get("contentType", "")).casefold() != "application/pdf":
            raise CandidateDecisionError("SKIPPED", "attachment is not a PDF")
        path = self.api.resolve_pdf_path(attachment)
        if path is None or not path.is_file() or path.suffix.casefold() != ".pdf":
            raise CandidateDecisionError("SKIPPED", "local PDF does not exist or is not a PDF")
        return path, parent_data

    def _record(self, state: StateStore, request: dict[str, Any], item: dict[str, Any], status: str,
                *, reason: str | None = None, artifact_path: str | None = None,
                markdown: str | None = None, successful_version: int | None = None) -> dict[str, Any]:
        state.record(library_id=request["library_id"], parent_item_key=item["parent_item_key"],
                     attachment_key=item["attachment_key"], attachment_version=item["attachment_version"],
                     status=status, request_id=request["request_id"], updated_at=utc_now(),
                     artifact_path=artifact_path, error_summary=reason,
                     successful_version=successful_version)
        entry = self._entry(item, status=status)
        if reason is not None:
            entry["reason"] = reason
        if artifact_path is not None:
            entry["artifact_path"] = artifact_path
        if markdown is not None:
            entry["markdown"] = markdown
        return entry

    def run(self, request_path: str | Path) -> dict[str, Any]:
        self.paths.prepare()
        request_file = Path(request_path)
        request = self._request(request_file)
        result_file = self.paths.results / f"{request['request_id']}.json"
        entries: list[dict[str, Any]] = []
        with SyncLock(self.paths.lock, request["request_id"]):
            with StateStore(self.paths.state_db) as state:
                ready: list[tuple[dict[str, Any], Path, dict[str, Any]]] = []
                for item in request.get("blocked_duplicates", []):
                    entries.append(self._record(state, request, item, "BLOCKED_DUPLICATE",
                                                reason="plugin marked duplicate"))
                for item in request["candidates"]:
                    try:
                        path, parent_data = self._current(item, request["library_id"])
                    except CandidateDecisionError as exc:
                        reason = str(exc)
                        entries.append(self._record(state, request, item, exc.status, reason=reason))
                        if exc.status == "STALE":
                            document = result_document(request, entries, "STALE")
                            self._atomic_json(result_file, document)
                            return document
                        continue
                    except Exception as exc:
                        entries.append(self._record(state, request, item, "FAILED", reason=str(exc)))
                        continue
                    prior = state.get(request["library_id"], item["attachment_key"])
                    successful_version = prior["successful_version"] if prior else None
                    if (prior and (prior["status"] == "SUCCESS" or successful_version is not None)
                            and (successful_version if successful_version is not None else prior["attachment_version"]) == item["attachment_version"]
                            and not item.get("force", False)):
                        artifact_path = prior["artifact_path"]
                        entries.append(self._record(
                            state, request, item, "SKIPPED", reason="attachment version already succeeded",
                            artifact_path=artifact_path, successful_version=item["attachment_version"],
                        ))
                        continue
                    ready.append((item, path, parent_data))

                for item, pdf_path, parent_data in ready:
                    artifact_dir = self.paths.artifact_dir(request["library_id"], item["parent_item_key"], item["attachment_key"])
                    artifact_dir.mkdir(parents=True, exist_ok=True)
                    raw_language = str(parent_data.get("language") or item.get("language") or "").casefold()
                    lang = "ch" if raw_language == "ch" or raw_language.startswith(("zh", "chi", "chinese")) else "en"
                    try:
                        conversion = self.converter(pdf_path, backend="pipeline", lang=lang, method="auto",
                                                    device="cpu", output_dir=artifact_dir)
                        logs = getattr(conversion, "log_lines", []) or []
                        (artifact_dir / "mineru.log").write_text("\n".join(map(str, logs)) + "\n", encoding="utf-8")
                        if not getattr(conversion, "success", False):
                            raise RuntimeError(getattr(conversion, "error", None) or "MinerU conversion failed")
                        output_md = Path(getattr(conversion, "output_md", artifact_dir / f"{pdf_path.stem}.md"))
                        if not output_md.is_file():
                            raise RuntimeError("MinerU reported success but Markdown output is missing")
                        artifact_root = artifact_dir.resolve()
                        if not output_md.resolve().is_relative_to(artifact_root):
                            raise RuntimeError("MinerU Markdown output is outside the archive directory")
                        manifest = {"schema_version": 1, "library_id": request["library_id"],
                                    "parent_item_key": item["parent_item_key"], "parent_item_version": item["parent_item_version"],
                                    "attachment_key": item["attachment_key"], "attachment_version": item["attachment_version"],
                                    "markdown": str(output_md), "language": lang, "backend": "pipeline", "device": "cpu"}
                        self._atomic_json(artifact_dir / "manifest.json", manifest)
                        entries.append(self._record(
                            state, request, item, "SUCCESS", artifact_path=str(artifact_dir),
                            markdown=str(output_md), successful_version=item["attachment_version"],
                        ))
                    except Exception as exc:
                        if not (artifact_dir / "mineru.log").exists():
                            (artifact_dir / "mineru.log").write_text(traceback.format_exc(), encoding="utf-8")
                        reason = str(exc)
                        entries.append(self._record(
                            state, request, item, "FAILED", reason=reason, artifact_path=str(artifact_dir),
                        ))
                document = result_document(request, entries)
                self._atomic_json(result_file, document)
                return document

    def write_protocol_error(self, request_path: str | Path, error: Exception) -> Path:
        self.paths.prepare()
        path = self.paths.results / f"{Path(request_path).stem}.json"
        self._atomic_json(path, {"schema_version": 1, "protocol_version": "1", "request_id": path.stem,
                                 "generated_at": utc_now(), "status": "FAILED", "counts": {"FAILED": 1},
                                 "entries": [{"status": "FAILED", "reason": str(error)}]})
        return path
