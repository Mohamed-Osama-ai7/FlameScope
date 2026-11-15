"""Append-only, hash-chained audit log per research run (in-memory reference implementation).

Each entry stores the hash of the previous entry, so editing or dropping an entry breaks `verify()`. The log
offers no update or delete operation and returns frozen entries. It lives in process memory: it is lost on
restart and is NOT a durable audit store; production needs a persistent append-only store (docs/23).
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from app.orchestrator.contracts import canonical_sha256

GENESIS = "0" * 64


class AuditEntry(BaseModel):
    model_config = ConfigDict(frozen=True)
    run_id: str
    seq: int
    at: str  # UTC ISO-8601, set by the log
    event: str
    prev_hash: str
    entry_hash: str


def _hash(run_id: str, seq: int, at: str, event: str, prev_hash: str) -> str:
    return canonical_sha256({"run_id": run_id, "seq": seq, "at": at, "event": event, "prev": prev_hash})


class AuditSink(Protocol):
    def append(self, run_id: str, event: str) -> AuditEntry: ...

    def entries(self, run_id: str) -> tuple[AuditEntry, ...]: ...


class InMemoryAuditLog:
    def __init__(self) -> None:
        self._runs: dict[str, list[AuditEntry]] = {}
        self._lock = threading.Lock()

    def append(self, run_id: str, event: str) -> AuditEntry:
        with self._lock:
            chain = self._runs.setdefault(run_id, [])
            prev = chain[-1].entry_hash if chain else GENESIS
            seq, at = len(chain), datetime.now(UTC).isoformat()
            entry = AuditEntry(
                run_id=run_id,
                seq=seq,
                at=at,
                event=event,
                prev_hash=prev,
                entry_hash=_hash(run_id, seq, at, event, prev),
            )
            chain.append(entry)
            return entry

    def entries(self, run_id: str) -> tuple[AuditEntry, ...]:
        with self._lock:
            return tuple(self._runs.get(run_id, ()))


def verify(entries: tuple[AuditEntry, ...]) -> bool:
    """True when the chain is complete, ordered and unmodified."""
    prev = GENESIS
    for i, e in enumerate(entries):
        if (
            e.seq != i
            or e.prev_hash != prev
            or e.entry_hash != _hash(e.run_id, e.seq, e.at, e.event, e.prev_hash)
        ):
            return False
        prev = e.entry_hash
    return True
