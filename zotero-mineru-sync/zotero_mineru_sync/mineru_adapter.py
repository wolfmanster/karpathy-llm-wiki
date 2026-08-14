"""Load the unmodified upstream MinerU API through a path adapter."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any


def _api_module() -> Any:
    # The adapter must not leave bytecode caches in the read-only upstream
    # checkout. The synchronizer is a one-shot process, so this process-wide
    # setting is both sufficient and safer than trying to clean up upstream
    # paths after imports have completed.
    sys.dont_write_bytecode = True
    configured = os.environ.get("ZOTERO_GUI_PATH")
    roots: list[Path] = []
    if configured:
        roots.append(Path(configured).expanduser())
    roots.append(Path(__file__).resolve().parents[2] / "MinerU-GUI")
    executable = Path(sys.executable).resolve()
    roots.extend(parent for parent in executable.parents if (parent / "mineru_api.py").is_file())
    roots.extend(parent / "MinerU-GUI" for parent in executable.parents
                 if (parent / "MinerU-GUI" / "mineru_api.py").is_file())
    root = next((candidate for candidate in roots if (candidate / "mineru_api.py").is_file()), None)
    if root is None:
        raise RuntimeError("MinerU API not found; set ZOTERO_GUI_PATH to the MinerU-GUI directory")
    source = root / "mineru_api.py"
    # Zotero launches the command with an arbitrary working directory. The
    # unmodified upstream module imports ``app`` and ``gui`` by name, so its
    # own directory must be on sys.path before executing the module.
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    spec = importlib.util.spec_from_file_location("zotero_mineru_upstream_api", source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load MinerU API: {source}")
    module = importlib.util.module_from_spec(spec)
    # Dataclasses and other standard-library introspection use the module's
    # registered name while the upstream module is being executed.
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise
    return module


def convert_document(*args: Any, **kwargs: Any) -> Any:
    return _api_module().convert_document(*args, **kwargs)
