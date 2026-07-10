"""
hash_store.py — the persistent ingestion manifest (SQLite).

Records, per source document:  content hash, version, status, timestamp.
This is what makes ingestion IDEMPOTENT and CRASH-SAFE:

  * unchanged hash            -> document skipped entirely      (edge case: re-run)
  * duplicate/renamed upload  -> same hash -> skipped           (edge case 2)
  * changed hash              -> old entries replaced cleanly   (edge case 3)
  * status left 'pending'     -> crash detected; cleaned + redone on next run
                                                                 (edge case 4)
"""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import get_settings


def content_hash(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class HashStore:
    def __init__(self, path: str | None = None):
        self.path = Path(path or get_settings().hash_store_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("""CREATE TABLE IF NOT EXISTS documents (
                   document_id TEXT PRIMARY KEY,
                   doc_hash    TEXT NOT NULL,
                   version     INTEGER NOT NULL DEFAULT 1,
                   status      TEXT NOT NULL,          -- pending | complete
                   chunk_count INTEGER DEFAULT 0,
                   updated_at  TEXT NOT NULL
               )""")
        self.conn.commit()

    # ---- decisions ---------------------------------------------------------

    def decide(self, document_id: str, doc_hash: str) -> str:
        """-> 'new' | 'changed' | 'unchanged' | 'retry_pending'"""
        row = self.conn.execute(
            "SELECT doc_hash, status FROM documents WHERE document_id=?",
            (document_id,),
        ).fetchone()
        if row is None:
            return "new"
        old_hash, status = row
        if status == "pending":
            return "retry_pending"
        return "unchanged" if old_hash == doc_hash else "changed"

    # ---- state transitions -------------------------------------------------

    def mark_pending(self, document_id: str, doc_hash: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            """INSERT INTO documents (document_id, doc_hash, version, status, updated_at)
               VALUES (?, ?, 1, 'pending', ?)
               ON CONFLICT(document_id) DO UPDATE SET
                   doc_hash=excluded.doc_hash,
                   version=documents.version + 1,
                   status='pending',
                   updated_at=excluded.updated_at""",
            (document_id, doc_hash, now),
        )
        self.conn.commit()

    def mark_complete(self, document_id: str, chunk_count: int) -> None:
        self.conn.execute(
            "UPDATE documents SET status='complete', chunk_count=?, updated_at=? "
            "WHERE document_id=?",
            (chunk_count, datetime.now(timezone.utc).isoformat(), document_id),
        )
        self.conn.commit()

    def list_pending(self) -> list[str]:
        return [
            r[0]
            for r in self.conn.execute(
                "SELECT document_id FROM documents WHERE status='pending'"
            )
        ]

    def summary(self) -> list[tuple]:
        return list(
            self.conn.execute(
                "SELECT document_id, version, status, chunk_count, updated_at "
                "FROM documents ORDER BY document_id"
            )
        )

    def close(self) -> None:
        self.conn.close()
