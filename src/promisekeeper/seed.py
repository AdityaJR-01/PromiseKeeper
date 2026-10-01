"""Deterministic demo evidence, so `pk demo` and the audit exercise the real
pipeline instead of reporting `insufficient_evidence` on an empty store.

Story: gold-tier EU orders historically take ~4.5 business days (customs), which
breaches the 3-day gold SLA -> the promise is blocked. A retained
`risk_pre_clearance` intervention shortens the last leg, so it is offered as the
alternative. US orders are fast. Ids are fixed, so seeding is idempotent."""
from __future__ import annotations
from datetime import date

from .memory import MemoryBackend
from .schemas import EvidenceRecord, Scope

_STAGES = ["payment_authorized", "picked", "shipped", "delivered"]

def _trace(rid, scope, when, state, legs, kind="observed_transition", intervention=None, stages=None):
    st = stages or _STAGES
    return EvidenceRecord(
        id=rid, scope=scope, kind=kind, occurred_at=when, source="seed", state=state,
        intervention=intervention,
        transitions=[{"from": a, "to": b, "value": v} for (a, b), v in zip(zip(st, st[1:]), legs)],
    )

def seed_demo(scope: Scope, memory: MemoryBackend | None = None) -> int:
    memory = memory or MemoryBackend()
    eu = {"destination_region": "EU", "tier": "gold", "order_value": 6000}
    us = {"destination_region": "US", "tier": "gold", "order_value": 4000}
    records = [
        _trace("seed-eu-1", scope, date(2026, 9, 2), eu, [0.5, 0.5, 3.5]),
        _trace("seed-eu-2", scope, date(2026, 9, 9), eu, [0.5, 0.5, 3.0]),
        _trace("seed-eu-3", scope, date(2026, 9, 16), eu, [0.5, 0.5, 4.0]),
        _trace("seed-us-1", scope, date(2026, 9, 4), us, [0.5, 0.5, 1.5]),
        _trace("seed-us-2", scope, date(2026, 9, 11), us, [0.5, 0.5, 1.5]),
        _trace("seed-eu-iv-1", scope, date(2026, 9, 18), eu, [1.4], "successful_intervention",
               "risk_pre_clearance", ["shipped", "delivered"]),
        _trace("seed-eu-iv-2", scope, date(2026, 9, 19), eu, [1.4], "successful_intervention",
               "risk_pre_clearance", ["shipped", "delivered"]),
    ]
    for r in records:
        memory.retain(scope, r)
    return len(records)
