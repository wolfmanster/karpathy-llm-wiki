"""Local-only data paths."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


def local_data_root() -> Path:
    override = os.environ.get("ZOTERO_MINERU_DATA_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    # Keep the default state alongside this integration component. The plugin
    # always passes its explicitly configured project-local data root, while
    # this fallback makes direct CLI use safe as well.
    return Path(__file__).resolve().parents[1] / "runtime"


@dataclass(frozen=True)
class SyncPaths:
    root: Path

    @classmethod
    def from_root(cls, root: str | Path | None = None) -> "SyncPaths":
        return cls(Path(root) if root is not None else local_data_root())

    @property
    def requests(self) -> Path:
        return self.root / "requests"

    @property
    def results(self) -> Path:
        return self.root / "results"

    @property
    def archive(self) -> Path:
        return self.root / "archive"

    @property
    def state_db(self) -> Path:
        return self.root / "state.sqlite"

    @property
    def lock(self) -> Path:
        return self.root / "sync.lock"

    def prepare(self) -> None:
        for path in (self.root, self.requests, self.results, self.archive):
            path.mkdir(parents=True, exist_ok=True)

    def artifact_dir(self, library_id: str, parent_key: str, attachment_key: str) -> Path:
        if not all(_SAFE_ID.fullmatch(part) for part in (library_id, parent_key, attachment_key)):
            raise ValueError("unsafe Zotero identifier")
        return self.archive.joinpath(library_id, parent_key, attachment_key)
