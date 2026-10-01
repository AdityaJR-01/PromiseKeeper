from __future__ import annotations
import re
from datetime import date
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION = "0.1"
EvidenceKind = Literal["observed_transition", "successful_intervention", "failed_intervention", "fact", "preference", "commitment", "rule_correction"]
Severity = Literal["blocking", "warning", "model_invalid", "info"]

# Scope parts become file names (local store) and Hindsight bank ids, so they are
# restricted to a conservative charset. This is what blocks "../../x" tenants.
_SCOPE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

class Scope(BaseModel):
    model_config = ConfigDict(extra="allow")
    tenant: str
    domain: str
    account: Optional[str] = None
    user: Optional[str] = None

    @field_validator("tenant", "domain", "account", "user")
    @classmethod
    def _safe_name(cls, v):
        if v is not None and not _SCOPE_NAME.match(v):
            raise ValueError("must be 1-64 chars of letters, digits, '_' or '-', starting with a letter or digit")
        return v
    def bank_key(self) -> str: return f"{self.tenant}-{self.domain}"

class ObservedTransition(BaseModel):
    from_state: str = Field(alias="from")
    to_state: str = Field(alias="to")
    # Durations are never negative; Dijkstra is only correct for non-negative weights.
    value: float = Field(ge=0.0, allow_inf_nan=False)
    model_config = ConfigDict(populate_by_name=True)

class Claim(BaseModel):
    subject: str
    predicate: str
    value: Any

class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    scope: Scope
    kind: EvidenceKind
    occurred_at: date
    source: str
    status: str = "observed"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    state: dict[str, Any] = Field(default_factory=dict)
    transitions: list[ObservedTransition] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    intervention: Optional[str] = None
    outcome: dict[str, Any] = Field(default_factory=dict)
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None
    evidence_refs: list[str] = Field(default_factory=list)
    note: Optional[str] = None
    def total_value(self) -> float: return round(sum(t.value for t in self.transitions), 6)
    def has_transition(self, a: str, b: str) -> bool: return any(t.from_state == a and t.to_state == b for t in self.transitions)
    def reaches(self, state: str) -> bool: return any(t.from_state == state or t.to_state == state for t in self.transitions)

class TransitionRule(BaseModel):
    id: str
    from_state: str
    to_state: str
    value: float
    scale_by: Optional[str] = None
    guard_id: str = "always"
    guard_expression: str = "true"
    confidence: float
    sample_size: int
    stdev: float = 0.0
    first_observed: Optional[date] = None
    status: str = "learned"
    derived_from: list[str] = Field(default_factory=list)
    intervention: Optional[str] = None

class Invariant(BaseModel):
    id: str
    description: str = ""
    applies_when: str = "true"
    expression: str
    severity: Severity = "blocking"

class InvariantResult(BaseModel):
    id: str
    severity: Severity
    applied: bool
    passed: bool
    detail: str = ""

class PathStep(BaseModel):
    rule_id: str
    from_state: str
    to_state: str
    value: float
    confidence: float
    guard_id: str
    derived_from: list[str] = Field(default_factory=list)
    status: str = "learned"

class SimulationResult(BaseModel):
    simulation_id: str
    compilation_id: str
    domain: str
    reachable: bool
    unreachable_reason: Optional[str] = None
    path: list[PathStep] = Field(default_factory=list)
    total_value: float = 0.0
    metric_name: str = "total"
    metric_unit: str = ""
    model_confidence: float = 0.0
    buffer_applied: float = 0.0
    projected_date: Optional[date] = None
    projected_date_buffered: Optional[date] = None
    invariants: list[InvariantResult] = Field(default_factory=list)
    decision: Literal["allow", "review", "block", "insufficient_evidence"] = "allow"
    reasons: list[str] = Field(default_factory=list)
    intervention: Optional[str] = None
    alternatives: list[dict[str, Any]] = Field(default_factory=list)
    evidence_used: list[str] = Field(default_factory=list)
    degraded_recall: bool = False
    def blocking(self) -> list[InvariantResult]:
        return [i for i in self.invariants if i.applied and not i.passed and i.severity == "blocking"]

class StepDifference(BaseModel):
    from_state: str
    to_state: str
    classification: Literal["confirmed", "deviated", "unmodeled", "missing"]
    predicted: Optional[float] = None
    observed: Optional[float] = None
    delta: Optional[float] = None
    rule_id: Optional[str] = None

class ProposedCorrection(BaseModel):
    kind: Literal["new_transition", "coefficient_update", "guard_narrowing"]
    from_state: str
    to_state: str
    value: float
    confidence: float
    rationale: str
    evidence_refs: list[str] = Field(default_factory=list)
    status: Literal["proposed", "confirmed", "rejected"] = "proposed"

class ReconciliationResult(BaseModel):
    reconciliation_id: str
    simulation_id: str
    trace_id: str
    classification: Literal["confirmed", "partially_confirmed", "contradicted", "model_invalid", "not_observable"]
    predicted_total: float
    observed_total: float
    total_delta: float
    structural_delta: float
    residual_delta: float
    differences: list[StepDifference] = Field(default_factory=list)
    unmodeled_states: list[str] = Field(default_factory=list)
    invariant_results: list[InvariantResult] = Field(default_factory=list)
    proposed_corrections: list[ProposedCorrection] = Field(default_factory=list)
