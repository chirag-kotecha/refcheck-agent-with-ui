"""
Minimal in-memory job store for the API's async submit/poll flow.

NOT durable (lost on process restart) and NOT shared across multiple
API worker processes -- fine for a single-process demo/dev deployment.
For production, back this with Redis, a database, or a proper task
queue (Celery/RQ/etc.) instead; the store's public interface (create /
get / mark_running / mark_completed / mark_failed) is small enough to
swap the implementation without touching refcheck/api/main.py or
runner.py.
"""

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class CheckStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class CheckRecord:
    check_id: str
    status: CheckStatus = CheckStatus.QUEUED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    result: Optional[dict] = None
    error: Optional[str] = None
    callback_url: Optional[str] = None


class InMemoryCheckStore:
    def __init__(self):
        self._records: dict[str, CheckRecord] = {}
        self._lock = threading.Lock()

    def create(self, callback_url: Optional[str] = None) -> CheckRecord:
        check_id = uuid.uuid4().hex
        record = CheckRecord(check_id=check_id, callback_url=callback_url)
        with self._lock:
            self._records[check_id] = record
        return record

    def get(self, check_id: str) -> Optional[CheckRecord]:
        with self._lock:
            return self._records.get(check_id)

    def mark_running(self, check_id: str) -> None:
        self._update(check_id, status=CheckStatus.RUNNING)

    def mark_completed(self, check_id: str, result: dict) -> None:
        self._update(check_id, status=CheckStatus.COMPLETED, result=result)

    def mark_failed(self, check_id: str, error: str) -> None:
        self._update(check_id, status=CheckStatus.FAILED, error=error)

    def _update(self, check_id: str, **kwargs) -> None:
        with self._lock:
            record = self._records.get(check_id)
            if record is None:
                return
            for k, v in kwargs.items():
                setattr(record, k, v)
            record.updated_at = datetime.now(timezone.utc)


# Module-level singleton -- fine for a single-process demo; see class
# docstring for the production caveat.
store = InMemoryCheckStore()
