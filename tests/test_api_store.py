"""
Unit tests for the in-memory job store. No network, no LLM calls.

Run with: pytest tests/test_api_store.py -v
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from refcheck.api.store import InMemoryCheckStore, CheckStatus


def test_create_returns_queued_record_with_unique_id():
    store = InMemoryCheckStore()
    r1 = store.create()
    r2 = store.create()
    assert r1.check_id != r2.check_id
    assert r1.status == CheckStatus.QUEUED


def test_get_unknown_id_returns_none():
    store = InMemoryCheckStore()
    assert store.get("does-not-exist") is None


def test_mark_running_updates_status():
    store = InMemoryCheckStore()
    record = store.create()
    store.mark_running(record.check_id)
    assert store.get(record.check_id).status == CheckStatus.RUNNING


def test_mark_completed_stores_result():
    store = InMemoryCheckStore()
    record = store.create()
    store.mark_completed(record.check_id, {"overall_confidence": 90.0})
    updated = store.get(record.check_id)
    assert updated.status == CheckStatus.COMPLETED
    assert updated.result == {"overall_confidence": 90.0}


def test_mark_failed_stores_error():
    store = InMemoryCheckStore()
    record = store.create()
    store.mark_failed(record.check_id, "something broke")
    updated = store.get(record.check_id)
    assert updated.status == CheckStatus.FAILED
    assert updated.error == "something broke"


def test_callback_url_preserved():
    store = InMemoryCheckStore()
    record = store.create(callback_url="https://example.com/webhook")
    assert store.get(record.check_id).callback_url == "https://example.com/webhook"


def test_update_on_unknown_id_is_a_noop():
    store = InMemoryCheckStore()
    store.mark_running("does-not-exist")  # should not raise
    assert store.get("does-not-exist") is None
