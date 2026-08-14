"""CLI implementation for the one-shot synchronizer."""

from __future__ import annotations

import argparse
import os
import sys

from .local_api import ZoteroLocalApi
from .paths import SyncPaths
from .runner import SyncRunner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Process one Zotero–MinerU request and exit")
    parser.add_argument("request")
    parser.add_argument("--data-root", default=None)
    parser.add_argument("--api-url", default=os.environ.get("ZOTERO_LOCAL_API_URL", "http://127.0.0.1:23119/api"))
    parser.add_argument("--storage-root", default=os.environ.get("ZOTERO_STORAGE_ROOT"))
    parser.add_argument("--cpu-threads", type=int, default=0,
                        help="set OMP/MinerU CPU render threads; 0 uses the upstream default")
    args = parser.parse_args(argv)
    if args.cpu_threads < 0:
        parser.error("--cpu-threads must be non-negative")
    if args.cpu_threads:
        os.environ["OMP_NUM_THREADS"] = str(args.cpu_threads)
        os.environ["MINERU_PDF_RENDER_THREADS"] = str(args.cpu_threads)
        os.environ["ZOTERO_MINERU_CPU_THREADS"] = str(args.cpu_threads)
    try:
        paths = SyncPaths.from_project_root(args.data_root)
    except ValueError as exc:
        parser.error(str(exc))
    runner = SyncRunner(paths, ZoteroLocalApi(args.api_url, args.storage_root))
    try:
        document = runner.run(args.request)
    except Exception as exc:  # CLI must always emit a readable result file
        runner.write_protocol_error(args.request, exc)
        print(f"zotero-mineru-sync: {exc}", file=sys.stderr)
        return 2
    print(document["status"])
    return 0 if document["status"] not in {"FAILED"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
