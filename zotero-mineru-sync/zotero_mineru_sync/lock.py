"""Recoverable single-process lock."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


def process_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return pid > 0


class SyncLock:
    def __init__(self, path: Path, request_id: str):
        self.path = path
        self.request_id = request_id
        self.acquired = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"pid": os.getpid(), "request_id": self.request_id, "started_at": time.time()}
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    old = json.loads(self.path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    old = {}
                if isinstance(old.get("pid"), int) and process_is_alive(old["pid"]):
                    raise RuntimeError(f"sync already running (pid={old['pid']})")
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    pass
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, sort_keys=True)
            self.acquired = True
            return
        raise RuntimeError("could not acquire sync lock")

    def release(self) -> None:
        if not self.acquired:
            return
        try:
            old = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            old = {}
        if old.get("pid") == os.getpid() and old.get("request_id") == self.request_id:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
        self.acquired = False

    def __enter__(self) -> "SyncLock":
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()
