"""Build a Zotero XPI without changing either upstream submodule."""

from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def build(source: Path, output: Path) -> Path:
    required = ("manifest.json", "bootstrap.js", "runtime.js", "prefs.js")
    missing = [name for name in required if not (source / name).is_file()]
    if missing:
        raise FileNotFoundError(f"plugin source missing: {', '.join(missing)}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file() and "node_modules" not in path.parts:
                archive.write(path, path.relative_to(source).as_posix())
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Zotero–MinerU XPI")
    parser.add_argument("--source", type=Path, default=Path(__file__).parent / "zotero-plugin")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "dist" / "zotero-mineru-sync.xpi")
    args = parser.parse_args()
    print(build(args.source, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
