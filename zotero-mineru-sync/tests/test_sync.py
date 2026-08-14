from __future__ import annotations

import json
import sqlite3
import importlib
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PACKAGE_ROOT = Path(__file__).parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(PACKAGE_ROOT))

from zotero_mineru_sync.models import ProtocolError, validate_request
from zotero_mineru_sync.paths import SyncPaths
from zotero_mineru_sync.runner import SyncRunner
from zotero_mineru_sync.lock import SyncLock
from zotero_mineru_sync.local_api import ZoteroApiError, ZoteroLocalApi


def request(**overrides):
    value = {
        "schema_version": 1,
        "protocol_version": "1",
        "request_id": "req-1",
        "generated_at": "2026-08-13T00:00:00Z",
        "library_id": "1",
        "plugin_generation": "3",
        "candidates": [{
            "parent_item_key": "P1", "parent_item_version": 2,
            "attachment_key": "A1", "attachment_version": 4,
            "eligible": True, "language": "zh-CN",
        }],
    }
    value.update(overrides)
    return value


class FakeAPI:
    def __init__(self, pdf: Path, parent_version=2, attachment_version=4, content_type="application/pdf", library_id=1):
        self.pdf = pdf
        self.parent_version = parent_version
        self.attachment_version = attachment_version
        self.content_type = content_type
        self.library_id = library_id

    def get_item(self, key):
        if key == "P1":
            return {"data": {"key": "P1", "version": self.parent_version, "libraryID": self.library_id, "language": "zh-CN"}}
        return {"data": {"key": "A1", "version": self.attachment_version, "libraryID": self.library_id, "parentItem": "P1",
                          "contentType": self.content_type, "path": str(self.pdf)}}

    def get_attachment(self, parent_key, attachment_key):
        return self.get_item(attachment_key)

    def resolve_pdf_path(self, attachment):
        return self.pdf


def write_request(path: Path, value=None):
    path.write_text(json.dumps(value or request()), encoding="utf-8")


def test_protocol_rejects_unknown_schema():
    with pytest.raises(ProtocolError, match="unsupported schema_version"):
        validate_request(request(schema_version=99))


def test_success_is_serialized_and_is_idempotent(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    paths = SyncPaths.from_root(tmp_path / "data")
    request_path = tmp_path / "request.json"
    write_request(request_path)
    calls = []

    def convert(path, **kwargs):
        calls.append((path, kwargs))
        out = Path(kwargs["output_dir"])
        md = out / "paper.md"
        md.write_text("# Paper", encoding="utf-8")
        return SimpleNamespace(success=True, output_md=md, log_lines=["done"], error=None)

    runner = SyncRunner(paths, FakeAPI(pdf), converter=convert)
    first = runner.run(request_path)
    second = runner.run(request_path)
    assert first["counts"] == {"SUCCESS": 1}
    assert second["counts"] == {"SKIPPED": 1}
    assert len(calls) == 1
    with sqlite3.connect(paths.state_db) as db:
        assert db.execute("SELECT status, successful_version FROM attachment_state").fetchone() == ("SKIPPED", 4)
    artifact = paths.archive / "1" / "P1" / "A1"
    assert (artifact / "manifest.json").is_file()
    assert (artifact / "mineru.log").read_text(encoding="utf-8").strip() == "done"


def test_force_resync_reprocesses_same_successful_version(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF")
    paths = SyncPaths.from_root(tmp_path / "data")
    request_path = tmp_path / "request.json"
    calls = []

    def convert(path, **kwargs):
        calls.append(1)
        out = Path(kwargs["output_dir"])
        out.mkdir(parents=True, exist_ok=True)
        md = out / "paper.md"
        md.write_text("# Paper", encoding="utf-8")
        return SimpleNamespace(success=True, output_md=md, log_lines=[], error=None)

    write_request(request_path)
    runner = SyncRunner(paths, FakeAPI(pdf), converter=convert)
    runner.run(request_path)
    forced = request(**{"request_id": "req-force", "candidates": [{**request()["candidates"][0], "force": True}]})
    write_request(request_path, forced)
    result = runner.run(request_path)
    assert result["counts"] == {"SUCCESS": 1}
    assert len(calls) == 2


def test_new_attachment_version_is_parsed_again(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF")
    paths = SyncPaths.from_root(tmp_path / "data")
    request_path = tmp_path / "request.json"
    calls = []

    def convert(path, **kwargs):
        calls.append(1)
        out = Path(kwargs["output_dir"])
        out.mkdir(parents=True, exist_ok=True)
        md = out / "paper.md"
        md.write_text("# Paper", encoding="utf-8")
        return SimpleNamespace(success=True, output_md=md, log_lines=[], error=None)

    write_request(request_path)
    runner = SyncRunner(paths, FakeAPI(pdf), converter=convert)
    runner.run(request_path)
    changed = request(**{"candidates": [{**request()["candidates"][0], "attachment_version": 5}], "request_id": "req-2"})
    write_request(request_path, changed)
    runner.api.attachment_version = 5
    runner.run(request_path)
    assert len(calls) == 2


def test_stale_snapshot_does_not_call_mineru(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF")
    request_path = tmp_path / "request.json"
    write_request(request_path)
    calls = []
    runner = SyncRunner(SyncPaths.from_root(tmp_path / "data"), FakeAPI(pdf, parent_version=3),
                        converter=lambda *_args, **_kwargs: calls.append(1))
    result = runner.run(request_path)
    assert result["status"] == "STALE"
    assert result["counts"] == {"STALE": 1}
    assert calls == []


def test_duplicate_candidate_is_blocked_without_local_api(tmp_path):
    request_path = tmp_path / "request.json"
    item = {**request()["candidates"][0]}
    value = request(candidates=[], blocked_duplicates=[item])
    write_request(request_path, value)
    runner = SyncRunner(SyncPaths.from_root(tmp_path / "data"), api=object(),
                        converter=lambda *_args, **_kwargs: pytest.fail("must not parse"))
    result = runner.run(request_path)
    assert result["counts"] == {"BLOCKED_DUPLICATE": 1}


def test_non_pdf_is_skipped_and_persisted(tmp_path):
    pdf = tmp_path / "paper.txt"
    pdf.write_text("not a pdf", encoding="utf-8")
    request_path = tmp_path / "request.json"
    write_request(request_path)
    runner = SyncRunner(SyncPaths.from_root(tmp_path / "data"), FakeAPI(pdf, content_type="text/plain"),
                        converter=lambda *_args, **_kwargs: pytest.fail("must not parse"))
    result = runner.run(request_path)
    assert result["counts"] == {"SKIPPED": 1}
    with sqlite3.connect(SyncPaths.from_root(tmp_path / "data").state_db) as db:
        assert db.execute("SELECT status FROM attachment_state").fetchone()[0] == "SKIPPED"


def test_deleted_parent_is_skipped_without_mineru(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF")
    request_path = tmp_path / "request.json"
    write_request(request_path)

    class DeletedAPI(FakeAPI):
        def get_item(self, key):
            return None if key == "P1" else super().get_item(key)

    runner = SyncRunner(SyncPaths.from_root(tmp_path / "data"), DeletedAPI(pdf),
                        converter=lambda *_args, **_kwargs: pytest.fail("must not parse"))
    result = runner.run(request_path)
    assert result["counts"] == {"SKIPPED": 1}


def test_detached_attachment_is_skipped_without_mineru(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF")
    request_path = tmp_path / "request.json"
    write_request(request_path)

    class DetachedAPI(FakeAPI):
        def get_attachment(self, parent_key, attachment_key):
            return {"data": {"key": "A1", "version": 4, "libraryID": 1,
                              "parentItem": "OTHER", "contentType": "application/pdf",
                              "path": str(self.pdf)}}

    runner = SyncRunner(SyncPaths.from_root(tmp_path / "data"), DetachedAPI(pdf),
                        converter=lambda *_args, **_kwargs: pytest.fail("must not parse"))
    result = runner.run(request_path)
    assert result["counts"] == {"SKIPPED": 1}


def test_dead_lock_is_recovered(tmp_path, monkeypatch):
    lock_path = tmp_path / "sync.lock"
    lock_path.write_text(json.dumps({"pid": 999999999, "request_id": "old"}), encoding="utf-8")
    monkeypatch.setattr("zotero_mineru_sync.lock.process_is_alive", lambda _pid: False)
    with SyncLock(lock_path, "new"):
        assert json.loads(lock_path.read_text(encoding="utf-8"))["request_id"] == "new"
    assert not lock_path.exists()


def test_library_mismatch_is_stale(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF")
    request_path = tmp_path / "request.json"
    write_request(request_path)
    runner = SyncRunner(SyncPaths.from_root(tmp_path / "data"), FakeAPI(pdf, library_id=2),
                        converter=lambda *_args, **_kwargs: pytest.fail("must not parse"))
    result = runner.run(request_path)
    assert result["status"] == "STALE"
    assert "library mismatch" in result["entries"][0]["reason"]


def test_storage_attachment_path_is_resolved_inside_zotero_storage(tmp_path):
    storage = tmp_path / "storage"
    attachment_dir = storage / "A1"
    attachment_dir.mkdir(parents=True)
    pdf = attachment_dir / "paper.pdf"
    pdf.write_bytes(b"%PDF")
    api = ZoteroLocalApi(storage_root=str(storage))
    attachment = {"key": "A1", "data": {"path": "storage:paper.pdf"}}
    assert api.resolve_pdf_path(attachment) == pdf.resolve()
    with pytest.raises(ZoteroApiError, match="escapes"):
        api.resolve_pdf_path({"key": "A1", "data": {"path": "storage:..\\outside.pdf"}})


def test_file_uri_windows_drive_path_is_decoded(tmp_path):
    api = ZoteroLocalApi()
    value = api.resolve_pdf_path({"key": "A1", "data": {"path": "file:///C:/Papers/paper.pdf"}})
    assert str(value).replace("/", "\\").endswith("C:\\Papers\\paper.pdf")


def test_local_api_file_url_fallback_is_used(tmp_path, monkeypatch):
    pdf = tmp_path / "fallback.pdf"
    pdf.write_bytes(b"%PDF")
    api = ZoteroLocalApi()
    monkeypatch.setattr(api, "get_text", lambda _path: pdf.as_uri())
    value = api.resolve_pdf_path({"key": "A1", "data": {"contentType": "application/pdf"}})
    assert value == pdf.resolve()


def test_conversion_failure_is_recorded_without_retry_in_same_process(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF")
    request_path = tmp_path / "request.json"
    write_request(request_path)
    calls = []

    def convert(*_args, **_kwargs):
        calls.append(1)
        return SimpleNamespace(success=False, output_md=None, log_lines=["failed"], error="engine error")

    runner = SyncRunner(SyncPaths.from_root(tmp_path / "data"), FakeAPI(pdf), converter=convert)
    result = runner.run(request_path)
    assert result["counts"] == {"FAILED": 1}
    assert len(calls) == 1
    with sqlite3.connect(SyncPaths.from_root(tmp_path / "data").state_db) as db:
        assert db.execute("SELECT status, error_summary FROM attachment_state").fetchone() == ("FAILED", "engine error")


def test_mineru_adapter_loads_upstream_from_any_working_directory(tmp_path, monkeypatch):
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    (upstream / "app.py").write_text("VALUE = 41\n", encoding="utf-8")
    (upstream / "mineru_api.py").write_text(
        "from dataclasses import dataclass\n"
        "from app import VALUE\n"
        "@dataclass\n"
        "class Result:\n"
        "    value: int\n"
        "def convert_document(*args, **kwargs): return Result(VALUE + 1).value\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ZOTERO_GUI_PATH", str(upstream))
    adapter = importlib.import_module("zotero_mineru_sync.mineru_adapter")
    assert adapter.convert_document("ignored.pdf") == 42
    assert not list(upstream.rglob("__pycache__"))


def test_cli_subprocess_processes_request_end_to_end(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.7")
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    (upstream / "app.py").write_text("", encoding="utf-8")
    (upstream / "mineru_api.py").write_text(
        "from pathlib import Path\n"
        "from types import SimpleNamespace\n"
        "def convert_document(file_path, **kwargs):\n"
        "    out = Path(kwargs['output_dir']); out.mkdir(parents=True, exist_ok=True)\n"
        "    md = out / 'paper.md'; md.write_text('# CLI paper', encoding='utf-8')\n"
        "    return SimpleNamespace(success=True, output_md=md, log_lines=['cli-ok'], error=None)\n",
        encoding="utf-8",
    )

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            key = self.path.rsplit("/", 1)[-1]
            if key == "P1":
                data = {"key": "P1", "version": 2, "libraryID": 1, "language": "en"}
            elif key == "A1":
                data = {"key": "A1", "version": 4, "libraryID": 1, "parentItem": "P1",
                        "contentType": "application/pdf", "path": str(pdf)}
            else:
                self.send_response(404)
                self.end_headers()
                return
            payload = json.dumps({"data": data}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        data_root = tmp_path / "data"
        request_path = data_root / "requests" / "cli-request.json"
        request_path.parent.mkdir(parents=True)
        write_request(request_path, request(request_id="cli-request"))
        import os
        environment = {**os.environ, "ZOTERO_GUI_PATH": str(upstream)}
        completed = subprocess.run(
            [sys.executable, "-m", "zotero_mineru_sync", str(request_path),
             "--data-root", str(data_root), "--api-url", f"http://127.0.0.1:{server.server_port}/api"],
            cwd=PACKAGE_ROOT, env=environment, capture_output=True, text=True, check=False,
        )
        assert completed.returncode == 0, completed.stderr
        result = json.loads((data_root / "results" / "cli-request.json").read_text(encoding="utf-8"))
        assert result["counts"] == {"SUCCESS": 1}
        artifact = data_root / "archive" / "1" / "P1" / "A1"
        assert (artifact / "paper.md").read_text(encoding="utf-8") == "# CLI paper"
        with sqlite3.connect(data_root / "state.sqlite") as db:
            assert db.execute("SELECT status FROM attachment_state").fetchone()[0] == "SUCCESS"
    finally:
        server.shutdown()
        thread.join(timeout=5)
