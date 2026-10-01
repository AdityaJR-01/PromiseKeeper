"""Local canonical store (JSONL on disk). Hindsight, when enabled, is only an
index over these records -- this file is the source of truth.

Layout under $PK_STORE_DIR (default .pk_store):
  <tenant>-<domain>.jsonl                  evidence records (all accounts of the bank)
  <tenant>-<domain>.reconciliations.jsonl  reconciliation history (account-tagged)
  simulations/<sim-id>.json                simulations awaiting an observed outcome
"""
from __future__ import annotations
import json
import logging
import os
import re
import threading
from pathlib import Path

from pydantic import ValidationError

from ..errors import UnknownSimulation
from ..schemas import EvidenceRecord, Scope, SimulationResult

log = logging.getLogger(__name__)
_lock = threading.RLock()
_SIM_ID = re.compile(r"^sim-[0-9a-f]{10}$")


def _store_dir() -> Path:
    return Path(os.environ.get("PK_STORE_DIR", ".pk_store"))

def _scope_file(scope: Scope) -> Path:
    d = _store_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{scope.bank_key()}.jsonl"

def _recon_file(scope: Scope) -> Path:
    d = _store_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{scope.bank_key()}.reconciliations.jsonl"

def _sim_dir() -> Path:
    d = _store_dir() / "simulations"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _parse_lines(path: Path):
    """Yield (raw_line, record_or_None). A corrupt line is skipped with a warning
    instead of taking down every simulation for the tenant."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield line, EvidenceRecord.model_validate_json(line)
        except ValidationError:
            log.warning("skipping unreadable evidence line in %s", path)
            yield line, None

def _matches(scope: Scope, rec: EvidenceRecord) -> bool:
    return scope.account is None or rec.scope.account == scope.account


def append(scope: Scope, record: EvidenceRecord) -> bool:
    """Append unless a record with this id already exists for the same account.
    Returns True if written. Idempotent so retries/replays can't double-count."""
    with _lock:
        path = _scope_file(scope)
        for _, rec in _parse_lines(path):
            if rec is not None and rec.id == record.id and rec.scope.account == record.scope.account:
                return False
        with path.open("a") as f:
            f.write(record.model_dump_json() + "\n")
        return True

def all_for_scope(scope: Scope) -> list[EvidenceRecord]:
    """Records for this scope, filtered to scope.account when set (bank_key()
    alone only isolates tenant+domain)."""
    return [rec for _, rec in _parse_lines(_scope_file(scope)) if rec is not None and _matches(scope, rec)]

def get_by_id(scope: Scope, evidence_id: str | None) -> EvidenceRecord | None:
    if not evidence_id:
        return None
    for rec in all_for_scope(scope):
        if rec.id == evidence_id:
            return rec
    return None

def reset_scope(scope: Scope, all_accounts: bool = False) -> bool:
    """Delete this account's evidence, reconciliation history and pending
    simulations -- and ONLY this account's, unless all_accounts=True (or the scope
    has no account). The old version unlinked the shared tenant+domain file, so
    resetting one account wiped every account. Returns True if evidence was removed."""
    wipe_all = all_accounts or scope.account is None
    removed = False
    with _lock:
        path = _scope_file(scope)
        if path.exists():
            if wipe_all:
                removed = any(rec is not None for _, rec in _parse_lines(path))
                path.unlink()
            else:
                keep = []
                for raw, rec in _parse_lines(path):
                    if rec is not None and rec.scope.account == scope.account:
                        removed = True
                    else:
                        keep.append(raw)
                path.write_text("".join(l + "\n" for l in keep))

        rpath = _recon_file(scope)
        if rpath.exists():
            if wipe_all:
                rpath.unlink()
            else:
                kept = [l for l in rpath.read_text().splitlines()
                        if l.strip() and json.loads(l).get("account") != scope.account]
                rpath.write_text("".join(l + "\n" for l in kept))

        for f in _sim_dir().glob("sim-*.json"):
            try:
                s = json.loads(f.read_text())["scope"]
            except (ValueError, KeyError, OSError):
                continue
            same_bank = s.get("tenant") == scope.tenant and s.get("domain") == scope.domain
            if same_bank and (wipe_all or s.get("account") == scope.account):
                f.unlink()
    return removed


# ---- simulations (so /observe can reconcile against the promise actually made) ----

def save_simulation(scope: Scope, state: dict, sim: SimulationResult) -> None:
    payload = {"scope": scope.model_dump(), "state": state, "sim": sim.model_dump(mode="json")}
    with _lock:
        (_sim_dir() / f"{sim.simulation_id}.json").write_text(json.dumps(payload, default=str))

def load_simulation(scope: Scope, simulation_id: str) -> SimulationResult:
    if not isinstance(simulation_id, str) or not _SIM_ID.match(simulation_id):
        raise UnknownSimulation(f"unknown simulation_id {simulation_id!r}")
    path = _sim_dir() / f"{simulation_id}.json"
    if not path.exists():
        raise UnknownSimulation(f"unknown simulation_id {simulation_id!r}; call /simulate first")
    payload = json.loads(path.read_text())
    s = payload["scope"]
    if (s.get("tenant"), s.get("domain"), s.get("account")) != (scope.tenant, scope.domain, scope.account):
        # same message as "missing": don't reveal that another scope owns this id
        raise UnknownSimulation(f"unknown simulation_id {simulation_id!r}; call /simulate first")
    return SimulationResult.model_validate(payload["sim"])


# ---- reconciliation history, scoped per account ----

def append_reconciliation(scope: Scope, payload: dict) -> None:
    with _lock, _recon_file(scope).open("a") as f:
        f.write(json.dumps({"account": scope.account, **payload}, default=str) + "\n")

def list_reconciliations(scope: Scope) -> list[dict]:
    path = _recon_file(scope)
    if not path.exists():
        return []
    rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    return [r for r in rows if scope.account is None or r.get("account") == scope.account]

def find_reconciliation(scope: Scope, trace_id: str) -> dict | None:
    for r in list_reconciliations(scope):
        if r.get("trace_id") == trace_id:
            return r
    return None
