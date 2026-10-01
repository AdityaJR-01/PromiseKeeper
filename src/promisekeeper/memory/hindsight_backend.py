from __future__ import annotations
import logging
import os
from dataclasses import dataclass

from ..errors import InvalidScope
from ..schemas import EvidenceRecord, Scope
from . import store as local_store

log = logging.getLogger(__name__)

def _flag(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")

@dataclass
class RecallOutcome:
    records: list            # list[EvidenceRecord]
    degraded: bool           # hindsight was requested but gave us nothing usable
    hindsight_reachable: bool
    local_topup: int = 0     # records added from the local store beyond Hindsight's hits

class MemoryBackend:
    """Facade over Hindsight with the local JSONL store as the canonical copy.

    PK_MEMORY_BACKEND=hindsight -> use a Hindsight server (PK_HINDSIGHT_BASE_URL).
    PK_MEMORY_BACKEND=local (default) -> local store only, no network.

    Recall semantics:
      * Hindsight hits are hydrated from the local store by metadata `evidence_id`
        (exact round-trip; no prose parsing) and ranked first.
      * Rule derivation needs *complete* edge coverage, and a semantic top-k can
        miss an edge entirely, which reads as "unreachable". So by default the
        result is topped up with the newest local records (PK_RECALL_TOPUP=false
        gives pure-semantic selection).
      * If Hindsight is down, errors, or returns no usable hits while the local
        store has data, we fall back to local and report degraded=True.
      * Local selection is NEWEST-first, capped at PK_LOCAL_RECALL_CAP (default
        500). The old `[:limit]` slice kept the OLDEST 25 records and silently
        stopped learning once the store grew past that.
    """

    def __init__(self):
        self.mode = os.environ.get("PK_MEMORY_BACKEND", "local")
        self.topup = _flag("PK_RECALL_TOPUP", True)
        self.retain_async = _flag("PK_RETAIN_ASYNC", True)
        self.local_cap = int(os.environ.get("PK_LOCAL_RECALL_CAP", 500))
        self._client = None
        self._banks: set[str] = set()
        if self.mode == "hindsight":
            try:
                from hindsight_client import Hindsight
                self._client = Hindsight(
                    base_url=os.environ.get("PK_HINDSIGHT_BASE_URL", "http://localhost:8888"),
                    api_key=os.environ.get("PK_HINDSIGHT_API_KEY"),
                    timeout=float(os.environ.get("PK_HINDSIGHT_TIMEOUT_S", 15)),
                    max_attempts=2,
                )
            except Exception:
                log.warning("hindsight-client unavailable; running degraded on local store")
                self._client = None

    def ping(self) -> bool | None:
        """None when Hindsight isn't the configured backend."""
        if self.mode != "hindsight":
            return None
        if self._client is None:
            return False
        try:
            self._client.get_version()
            return True
        except Exception:
            return False

    def _ensure_bank(self, scope: Scope) -> None:
        key = scope.bank_key()
        if key in self._banks:
            return
        try:
            self._client.create_bank(bank_id=key)
        except Exception:
            pass  # already exists, or a transient error that retain/recall will surface
        self._banks.add(key)

    @staticmethod
    def _check_scope(scope: Scope, record: EvidenceRecord) -> None:
        rs = record.scope
        if (rs.tenant, rs.domain, rs.account) != (scope.tenant, scope.domain, scope.account):
            raise InvalidScope("record.scope does not match the scope it is being retained under")

    def retain(self, scope: Scope, record: EvidenceRecord) -> bool:
        """Local write first (idempotent by evidence id). Returns True if the
        record was also sent to Hindsight."""
        self._check_scope(scope, record)
        written = local_store.append(scope, record)
        if self._client is None or not written:
            return False
        try:
            self._ensure_bank(scope)
            tags = [record.kind, scope.domain] + ([scope.account] if scope.account else [])
            self._client.retain(
                bank_id=scope.bank_key(),
                content=_prose(record),
                document_id=record.id,          # stable id -> upsert, not duplicate
                metadata={"evidence_id": record.id, "kind": record.kind},
                tags=tags,
                retain_async=self.retain_async,  # don't block /observe on LLM extraction
            )
            return True
        except Exception:
            log.warning("hindsight retain failed for %s; local copy is safe", record.id)
            return False

    def recall(self, scope: Scope, query: str, limit: int = 25) -> RecallOutcome:
        local = local_store.all_for_scope(scope)        # read the file once
        newest = sorted(local, key=lambda r: r.occurred_at, reverse=True)

        if self._client is not None:
            try:
                tags = [scope.domain] + ([scope.account] if scope.account else [])
                # all_strict: a memory must carry BOTH the domain and account tag.
                # (default "any" matched every record via the domain tag alone.)
                resp = self._client.recall(bank_id=scope.bank_key(), query=query,
                                           max_tokens=4096, tags=tags, tags_match="all_strict")
                by_id = {r.id: r for r in local}  # also enforces scope.account
                hits, seen = [], set()
                for r in resp.results:
                    rec = by_id.get((r.metadata or {}).get("evidence_id"))
                    if rec is not None and rec.id not in seen:
                        hits.append(rec)
                        seen.add(rec.id)
                    if len(hits) >= limit:
                        break
                topped = []
                if self.topup:
                    for rec in newest:
                        if len(hits) + len(topped) >= self.local_cap:
                            break
                        if rec.id not in seen:
                            topped.append(rec)
                return RecallOutcome(records=hits + topped,
                                     degraded=(not hits and bool(local)),
                                     hindsight_reachable=True, local_topup=len(topped))
            except Exception:
                log.warning("hindsight recall failed; falling back to local store")

        return RecallOutcome(
            records=newest[: self.local_cap],
            degraded=(self.mode == "hindsight"),
            hindsight_reachable=False,
        )

def _prose(record: EvidenceRecord) -> str:
    parts = [f"[{record.kind}] account={record.scope.account or 'unknown'} on {record.occurred_at.isoformat()}"]
    if record.intervention:
        parts.append(f"intervention={record.intervention}")
    for t in record.transitions:
        parts.append(f"{t.from_state} -> {t.to_state}: {t.value} {record.state.get('unit', '')}".strip())
    if record.note:
        parts.append(record.note)
    return " | ".join(parts)
