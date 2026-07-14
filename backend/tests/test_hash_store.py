"""
Tests for app.ingestion.hash_store — the SQLite ingestion manifest that
makes ingestion idempotent and crash-safe.

Uses a temporary file-backed SQLite DB per test (not the real project path)
so tests never touch real ingestion state and can run in parallel safely.
"""
from __future__ import annotations

import pytest

from app.ingestion.hash_store import HashStore, content_hash


@pytest.fixture
def store(tmp_path):
    s = HashStore(path=str(tmp_path / "test_manifest.sqlite"))
    yield s
    s.close()


def test_content_hash_is_deterministic():
    assert content_hash("hello") == content_hash("hello")


def test_content_hash_differs_for_different_content():
    assert content_hash("hello") != content_hash("world")


def test_content_hash_accepts_bytes_and_str_identically():
    assert content_hash("hello") == content_hash(b"hello")


def test_decide_new_document_returns_new(store):
    assert store.decide("doc-1", "hash-a") == "new"


def test_decide_unchanged_hash_returns_unchanged(store):
    store.mark_pending("doc-1", "hash-a")
    store.mark_complete("doc-1", chunk_count=5)
    assert store.decide("doc-1", "hash-a") == "unchanged"


def test_decide_changed_hash_returns_changed(store):
    store.mark_pending("doc-1", "hash-a")
    store.mark_complete("doc-1", chunk_count=5)
    assert store.decide("doc-1", "hash-b") == "changed"


def test_decide_pending_status_returns_retry_pending(store):
    # mark_pending without a following mark_complete simulates a crash
    # mid-ingestion — the next run must detect and redo it.
    store.mark_pending("doc-1", "hash-a")
    assert store.decide("doc-1", "hash-a") == "retry_pending"


def test_mark_pending_increments_version_on_repeat(store):
    store.mark_pending("doc-1", "hash-a")
    store.mark_complete("doc-1", chunk_count=3)
    store.mark_pending("doc-1", "hash-b")  # re-ingest with changed content
    rows = {r[0]: r for r in store.summary()}
    assert rows["doc-1"][1] == 2  # version bumped from 1 to 2


def test_mark_complete_updates_status_and_chunk_count(store):
    store.mark_pending("doc-1", "hash-a")
    store.mark_complete("doc-1", chunk_count=42)
    rows = {r[0]: r for r in store.summary()}
    assert rows["doc-1"][2] == "complete"
    assert rows["doc-1"][3] == 42


def test_list_pending_only_returns_incomplete_documents(store):
    store.mark_pending("doc-1", "hash-a")
    store.mark_complete("doc-1", chunk_count=1)
    store.mark_pending("doc-2", "hash-b")  # left pending — simulated crash

    pending = store.list_pending()
    assert pending == ["doc-2"]


def test_summary_orders_by_document_id(store):
    store.mark_pending("doc-b", "hash-1")
    store.mark_pending("doc-a", "hash-2")
    ids = [r[0] for r in store.summary()]
    assert ids == ["doc-a", "doc-b"]


def test_store_survives_reopening_same_path(tmp_path):
    path = str(tmp_path / "reopen.sqlite")
    s1 = HashStore(path=path)
    s1.mark_pending("doc-1", "hash-a")
    s1.mark_complete("doc-1", chunk_count=7)
    s1.close()

    s2 = HashStore(path=path)
    assert s2.decide("doc-1", "hash-a") == "unchanged"
    s2.close()
