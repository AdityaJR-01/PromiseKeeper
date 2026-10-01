from __future__ import annotations
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from .errors import InvalidScope, InvalidState, UnknownIntervention
from .schemas import EvidenceRecord, ReconciliationResult, Scope, SimulationResult
from .compiler.domain import Domain
from .compiler.graph import shortest_path
from .compiler.invariants import check_invariants
from .compiler.projection import add_business_days
from .compiler.rules import derive_rules
from .memory import MemoryBackend
from .memory import store as local_store
from .reconciliation.localize import reconcile

DOMAINS_DIR = Path(__file__).resolve().parents[2] / "domains"

class PromiseKeeperService:
    def __init__(self, domain_name: str, memory: MemoryBackend | None = None):
        self.domain_name = domain_name
        self.domain = Domain.load(DOMAINS_DIR, domain_name)   # raises UnknownDomain
        self.memory = memory or MemoryBackend()

    # ---- validation -------------------------------------------------------
    def _validate_scope(self, scope: Scope) -> None:
        if scope.domain != self.domain_name:
            raise InvalidScope(f"scope.domain '{scope.domain}' does not match domain '{self.domain_name}'")
        for key in self.domain.hard_keys:  # e.g. [tenant, account] from the domain YAML
            if not getattr(scope, key, None):
                raise InvalidScope(f"scope.{key} is required for domain '{self.domain_name}'")

    def _validate_state(self, state: dict[str, Any]) -> None:
        missing = sorted(f for f in self.domain.required_state_fields if f not in state)
        if missing:
            raise InvalidState(f"state is missing required field(s): {', '.join(missing)}")

    # ---- simulation -------------------------------------------------------
    def simulate_workflow(self, scope: Scope, state: dict[str, Any], intervention: str | None = None):
        self._validate_scope(scope)
        self._validate_state(state)
        if intervention is not None and intervention not in self.domain.interventions:
            raise UnknownIntervention(f"unknown intervention '{intervention}'; known: {sorted(self.domain.interventions)}")

        query = self.domain.render_recall_query(state, scope)
        recall = self.memory.recall(scope, query, limit=self.domain.recall_limit)
        rules = derive_rules(self.domain, recall.records)

        sim = self._compile(state, recall, rules, intervention)
        if intervention is None and sim.decision in ("block", "review"):
            sim.alternatives = self._alternatives(state, recall, rules)

        local_store.save_simulation(scope, state, sim)  # so /observe reconciles against THIS promise
        return sim, recall

    def _alternatives(self, state, recall, rules) -> list[dict]:
        alts = []
        for iv_id, iv in self.domain.interventions.items():
            alt = self._compile(state, recall, rules, iv_id)
            if alt.reachable:   # skip interventions we have no evidence about
                alts.append({"intervention": iv_id, "total_value": alt.total_value,
                             "lead_time_days": iv.get("lead_time_days", 0.0), "decision": alt.decision})
        return sorted(alts, key=lambda a: a["total_value"])

    def _compile(self, state, recall, rules, intervention: str | None) -> SimulationResult:
        d = self.domain
        base = [r for r in rules if r.intervention is None]
        iv_rules = [r for r in rules if intervention and r.intervention == intervention]
        lead_time = float(d.interventions[intervention].get("lead_time_days", 0.0)) if intervention else 0.0

        sim = SimulationResult(
            simulation_id=f"sim-{uuid.uuid4().hex[:10]}",
            compilation_id=f"cmp-{uuid.uuid4().hex[:10]}",
            domain=self.domain_name, reachable=False, intervention=intervention,
            metric_name=d.metric_name, metric_unit=d.metric_unit,
            degraded_recall=recall.degraded, evidence_used=[r.id for r in recall.records],
        )

        if intervention and not iv_rules:
            sim.unreachable_reason = f"No retained evidence of how '{intervention}' changes the path yet."
        else:
            path, total, min_conf = shortest_path(d, state, base + iv_rules)
            if path is None:
                sim.unreachable_reason = f"No evidence-backed path from '{d.initial_state}' to '{d.terminal_state}' yet."
            else:
                sim.reachable = True
                sim.path = path
                sim.total_value = round(total + lead_time, 4)
                sim.model_confidence = min_conf

        if not sim.reachable:
            sim.decision = "insufficient_evidence"
            sim.reasons = [sim.unreachable_reason]
            return sim

        buffered = sim.total_value
        if sim.model_confidence < d.confidence_buffer_threshold:
            sim.buffer_applied = d.conservative_buffer
            buffered = round(sim.total_value + sim.buffer_applied, 4)

        sim.invariants = check_invariants(d, state, d.metric_name, buffered)
        self._project_dates(sim, state, buffered)

        warnings = [i for i in sim.invariants if i.applied and not i.passed and i.severity == "warning"]
        if sim.blocking():
            sim.decision = "block"
            sim.reasons = [f"Blocked by invariant {r.id}: {r.detail}" for r in sim.blocking()]
        elif sim.buffer_applied > 0 or warnings:
            sim.decision = "review"
            sim.reasons = []
            if sim.buffer_applied > 0:
                sim.reasons.append(f"Model confidence {sim.model_confidence:.2f} is below the {d.confidence_buffer_threshold} threshold; added a {sim.buffer_applied}-unit conservative buffer.")
            sim.reasons += [f"Warning from invariant {w.id}: {w.detail}" for w in warnings]
        else:
            sim.decision = "allow"
            sim.reasons = [f"Compiled a {len(sim.path)}-step path from {len(recall.records)} retained evidence record(s) (confidence {sim.model_confidence:.2f})."]
        if intervention:
            sim.reasons.append(f"Assumes intervention '{intervention}' (+{lead_time} {d.metric_unit} lead time).")
        return sim

    def _project_dates(self, sim: SimulationResult, state: dict, buffered: float) -> None:
        d = self.domain
        if d.projection != "business_days" or not d.projection_start_field:
            return
        raw = state.get(d.projection_start_field)
        try:
            start = raw if isinstance(raw, date) else date.fromisoformat(str(raw))
        except (TypeError, ValueError):
            return  # no usable start date: omit projections rather than guess
        sim.projected_date = add_business_days(start, sim.total_value)
        sim.projected_date_buffered = add_business_days(start, buffered)

    # ---- reconciliation ---------------------------------------------------
    def record_outcome(self, scope: Scope, sim: SimulationResult, trace: EvidenceRecord) -> ReconciliationResult:
        """Reconcile an observed outcome against the simulation that made the promise,
        retain the trace and any proposed corrections, and log the reconciliation.

        Idempotent by trace id: replaying the same trace returns the stored result
        instead of retaining it (and its corrections) a second time."""
        self._validate_scope(scope)
        ts = trace.scope
        if (ts.tenant, ts.domain, ts.account) != (scope.tenant, scope.domain, scope.account):
            raise InvalidScope("trace.scope does not match the request scope")
        if sim.domain != self.domain_name:
            raise InvalidScope("simulation belongs to a different domain")

        prior = local_store.find_reconciliation(scope, trace.id)
        if prior is not None:
            return ReconciliationResult.model_validate(prior)

        existing = local_store.get_by_id(scope, trace.id)
        if existing is not None and existing != trace:
            raise InvalidState(f"evidence id '{trace.id}' already exists with different content")

        invariant_results = check_invariants(self.domain, trace.state, self.domain.metric_name, trace.total_value())
        result = reconcile(self.domain, sim, trace, invariant_results=invariant_results)

        self.memory.retain(scope, trace)
        for corr in result.proposed_corrections:
            # Deterministic id => a retry after a partial failure can't duplicate it.
            # evidence_refs points at the trace so derive_rules doesn't count both.
            self.memory.retain(scope, EvidenceRecord(
                id=f"corr-{trace.id}-{corr.from_state}-{corr.to_state}", scope=scope, kind="rule_correction",
                occurred_at=trace.occurred_at, source="reconciliation",
                state=trace.state,   # same state => same guard bucket as the original prediction
                transitions=[{"from": corr.from_state, "to": corr.to_state, "value": corr.value}],
                evidence_refs=[trace.id], note=corr.rationale,
            ))
        local_store.append_reconciliation(scope, result.model_dump(mode="json"))
        return result
