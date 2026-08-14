"""Seed only the project-local Zotero E2E database while Zotero is stopped."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--marker", type=Path, required=True)
    args = parser.parse_args()

    fixture = args.fixture.resolve()
    if not fixture.is_file() or fixture.suffix.casefold() != ".pdf":
        raise SystemExit(f"fixture is not a PDF: {fixture}")

    db = sqlite3.connect(args.db)
    try:
        if db.execute("SELECT COUNT(*) FROM items").fetchone()[0] != 0:
            raise SystemExit("refusing to seed a non-empty E2E database")
        parents = ((1, "E2EPAPER", 2, "E2EATTCH"), (3, "E2EDUPE1", 4, "E2EDATT1"))
        storage_root = args.db.resolve().parent / "storage"
        for parent_id, parent_key, attachment_id, attachment_key in parents:
            db.execute(
                "INSERT INTO items(itemID,itemTypeID,libraryID,key,version,synced) VALUES(?,?,?,?,?,0)",
                (parent_id, 22, 1, parent_key, 1),
            )
            db.execute(
                "INSERT INTO items(itemID,itemTypeID,libraryID,key,version,synced) VALUES(?,?,?,?,?,0)",
                (attachment_id, 3, 1, attachment_key, 1),
            )
            db.execute(
                "INSERT INTO itemAttachments(itemID,parentItemID,linkMode,contentType,path) VALUES(?,?,?,?,?)",
                (attachment_id, parent_id, 0, "application/pdf", "storage:paper.pdf"),
            )
            attachment_dir = storage_root / attachment_key
            attachment_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(fixture, attachment_dir / "paper.pdf")
            for field_id, value, item_id in (
                (1, "Zotero MinerU actual E2E paper", parent_id),
                (15, "en", parent_id),
                (1, "E2E PDF", attachment_id),
            ):
                db.execute("INSERT OR IGNORE INTO itemDataValues(value) VALUES(?)", (value,))
                value_id = db.execute("SELECT valueID FROM itemDataValues WHERE value=?", (value,)).fetchone()[0]
                db.execute("INSERT INTO itemData(itemID,fieldID,valueID) VALUES(?,?,?)", (item_id, field_id, value_id))
        db.execute("UPDATE libraries SET version=version+1 WHERE libraryID=1")
        db.commit()
    finally:
        db.close()

    document = {
        "status": "seeded",
        "library_id": "0",
        "master_parent_item_key": "E2EPAPER",
        "parent_item_version": 1,
        "master_attachment_key": "E2EATTCH",
        "attachment_version": 1,
        "duplicate_parent_item_key": "E2EDUPE1",
        "duplicate_attachment_key": "E2EDATT1",
        "fixture": str(fixture),
    }
    args.marker.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(document))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
