"""Seed only the project-local Zotero E2E database while Zotero is stopped."""

from __future__ import annotations

import argparse
import json
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
        parent_id, attachment_id = 1, 2
        parent_key, attachment_key = "E2EPAPER", "E2EATTCH"
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
            (attachment_id, parent_id, 2, "application/pdf", fixture.as_uri()),
        )
        values = [(1, "Zotero MinerU actual E2E paper"), (15, "en"), (1, "E2E PDF")]
        for field_id, value in values:
            db.execute("INSERT INTO itemDataValues(value) VALUES(?)", (value,))
            value_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            item_id = parent_id if field_id != 1 or value != "E2E PDF" else attachment_id
            db.execute("INSERT INTO itemData(itemID,fieldID,valueID) VALUES(?,?,?)", (item_id, field_id, value_id))
        db.execute("UPDATE libraries SET version=version+1 WHERE libraryID=1")
        db.commit()
    finally:
        db.close()

    document = {
        "status": "seeded",
        "library_id": "0",
        "parent_item_key": parent_key,
        "parent_item_version": 1,
        "attachment_key": attachment_key,
        "attachment_version": 1,
        "fixture": str(fixture),
    }
    args.marker.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(document))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
