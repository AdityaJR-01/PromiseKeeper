from __future__ import annotations
from collections import defaultdict
from statistics import mean, pstdev

from ..schemas import EvidenceRecord, TransitionRule
from .domain import Domain
from .guard import evaluate_guard

_LEARNABLE_KINDS = {"observed_transition", "successful_intervention", "failed_intervention", "rule_correction"}

def _best_matching_guard(domain: Domain, state: dict) -> str:
    best_id, best_spec = "always", -1
    for gid, g in domain.guard_hypotheses.items():
        try:
            if evaluate_guard(g["expression"], state) and g.get("specificity", 0) > best_spec:
                best_id, best_spec = gid, g.get("specificity", 0)
        except Exception:
            continue
    return best_id

def _confidence(values: list[float]) -> float:
    """Support-based confidence, penalised by spread.

    n=1 -> 0.50, n=2 -> 0.67, n=3 -> 0.75 ... (1 - 1/(n+1)), then divided by
    (1 + coefficient of variation) and capped at 0.95. The old `0.5 + 0.1n`
    started at exactly the 0.6 buffer threshold, so the buffer could never fire,
    and it ignored stdev entirely."""
    n = len(values)
    base = 1.0 - 1.0 / (n + 1)
    m = mean(values)
    cv = (pstdev(values) / m) if n > 1 and m > 0 else 0.0
    return round(min(0.95, base / (1.0 + cv)), 3)

def derive_rules(domain: Domain, evidence: list[EvidenceRecord]) -> list[TransitionRule]:
    """Turn retained evidence into weighted TransitionRules, one per
    (from_state, to_state, guard, intervention) bucket.

    * Superseded records (supersedes / superseded_by) are excluded.
    * A rule_correction that points at a trace we also have is skipped: the trace
      already contributes that sample, counting both double-weighted the edge and
      inflated confidence.
    * Records carrying an `intervention` only train that intervention's rules, so
      they never pollute the baseline.
    * Samples are recency-weighted (half-life from the domain YAML), which is what
      "the most recent confirmed claim wins" in docs/memory-design.md requires.
    """
    superseded = {r.supersedes for r in evidence if r.supersedes} | {r.id for r in evidence if r.superseded_by}
    present = {r.id for r in evidence}

    buckets: dict[tuple, list[tuple]] = defaultdict(list)
    for rec in evidence:
        if rec.kind not in _LEARNABLE_KINDS or rec.id in superseded:
            continue
        if rec.kind == "rule_correction" and any(ref in present for ref in rec.evidence_refs):
            continue
        guard_id = _best_matching_guard(domain, rec.state)
        for t in rec.transitions:
            buckets[(t.from_state, t.to_state, guard_id, rec.intervention)].append((t.value, rec.id, rec.occurred_at))

    half_life = domain.recency_half_life_days
    rules: list[TransitionRule] = []
    for (u, v, guard_id, iv), samples in buckets.items():
        if len(samples) < domain.min_support:
            continue
        values = [s[0] for s in samples]
        ids = [s[1] for s in samples]
        dates = [s[2] for s in samples]
        newest = max(dates)
        if half_life > 0:
            weights = [0.5 ** ((newest - d).days / half_life) for d in dates]
        else:
            weights = [1.0] * len(values)
        avg = sum(w * x for w, x in zip(weights, values)) / sum(weights)
        sd = pstdev(values) if len(values) > 1 else 0.0
        rules.append(TransitionRule(
            id=f"rule-{u}-{v}-{guard_id}" + (f"-{iv}" if iv else ""),
            from_state=u, to_state=v, value=round(avg, 4),
            guard_id=guard_id, guard_expression=domain.guard_expression(guard_id),
            confidence=_confidence(values), sample_size=len(values),
            stdev=round(sd, 4), first_observed=min(dates),
            status="learned", derived_from=ids, intervention=iv,
        ))
    return rules
