from __future__ import annotations
import uuid
from typing import Any
from ..schemas import EvidenceRecord, InvariantResult, ProposedCorrection, ReconciliationResult, SimulationResult, StepDifference

def reconcile(domain, sim: SimulationResult, trace: EvidenceRecord) -> ReconciliationResult:
    if trace.kind not in ("observed_transition", "successful_intervention"):
        return ReconciliationResult(
            reconciliation_id=f"rec-{uuid.uuid4().hex[:10]}",
            simulation_id=sim.simulation_id,
            trace_id=trace.id,
            classification="not_observable",
            predicted_total=sim.total_value,
            observed_total=0.0,
            total_delta=0.0,
            structural_delta=0.0,
            residual_delta=0.0,
        )

    predicted_total = sim.total_value
    observed_total = trace.total_value()
    total_delta = observed_total - predicted_total

    pred_map = {(step.from_state, step.to_state): step for step in sim.path}
    obs_map = {(t.from_state, t.to_state): t for t in trace.transitions}
    all_edges = sorted(set(pred_map.keys()) | set(obs_map.keys()))

    differences: list[StepDifference] = []
    proposed_corrections: list[ProposedCorrection] = []
    unmodeled_states: set[str] = set()

    for edge in all_edges:
        u, v = edge
        p_step = pred_map.get(edge)
        o_trans = obs_map.get(edge)

        if p_step and o_trans:
            p_val = p_step.value
            o_val = o_trans.value
            delta = o_val - p_val
            classification = "confirmed" if abs(delta) <= domain.deviation_tolerance else "deviated"
            differences.append(StepDifference(from_state=u, to_state=v, classification=classification, predicted=p_val, observed=o_val, delta=delta, rule_id=p_step.rule_id))
        elif p_step and not o_trans:
            differences.append(StepDifference(from_state=u, to_state=v, classification="missing", predicted=p_step.value, observed=None, delta=-p_step.value, rule_id=p_step.rule_id))
        elif o_trans and not p_step:
            unmodeled_states.add(u)
            unmodeled_states.add(v)
            differences.append(StepDifference(from_state=u, to_state=v, classification="unmodeled", predicted=None, observed=o_trans.value, delta=o_trans.value, rule_id=None))

    if any(d.classification in ("unmodeled", "missing") for d in differences):
        overall_class = "model_invalid"
    elif any(d.classification == "deviated" for d in differences):
        overall_class = "contradicted"
    elif all(d.classification == "confirmed" for d in differences) and differences:
        overall_class = "confirmed"
    else:
        overall_class = "partially_confirmed"

    return ReconciliationResult(
        reconciliation_id=f"rec-{uuid.uuid4().hex[:10]}",
        simulation_id=sim.simulation_id,
        trace_id=trace.id,
        classification=overall_class,
        predicted_total=round(predicted_total, 6),
        observed_total=round(observed_total, 6),
        total_delta=round(total_delta, 6),
        structural_delta=0.0,
        residual_delta=round(total_delta, 6),
        differences=differences,
        unmodeled_states=sorted(list(unmodeled_states)),
        invariant_results=[],
        proposed_corrections=proposed_corrections,
    )
