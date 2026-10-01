from __future__ import annotations
from ..schemas import InvariantResult
from .domain import Domain
from .guard import evaluate_guard, GuardExpressionError

def check_invariants(domain: Domain, state: dict, metric_name: str, metric_value: float) -> list[InvariantResult]:
    """Evaluate every domain invariant. Fails CLOSED: if we cannot tell whether an
    invariant applies (e.g. `tier` missing from the state), it is reported as
    applied-and-failed rather than silently skipped -- skipping is how a gold-tier
    order used to come back `allow` with no SLA check at all."""
    ctx = {**state, metric_name: metric_value}
    results = []
    for inv in domain.invariants:
        try:
            applies = evaluate_guard(inv.applies_when, state)
        except GuardExpressionError as e:
            results.append(InvariantResult(id=inv.id, severity=inv.severity, applied=True, passed=False,
                                           detail=f"cannot determine whether this invariant applies: {e}"))
            continue
        if not applies:
            results.append(InvariantResult(id=inv.id, severity=inv.severity, applied=False, passed=True, detail="not applicable to this state"))
            continue
        try:
            passed = evaluate_guard(inv.expression, ctx)
            detail = "" if passed else f"violated: {inv.expression} (given {metric_name}={metric_value})"
        except GuardExpressionError as e:
            passed, detail = False, f"invariant expression error: {e}"
        results.append(InvariantResult(id=inv.id, severity=inv.severity, applied=True, passed=passed, detail=detail))
    return results
