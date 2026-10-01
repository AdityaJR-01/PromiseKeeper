"""Regression tests for the engine-level bugs found in review of the first patch."""
from datetime import date, timedelta
import pytest
from pydantic import ValidationError

from promisekeeper.compiler.domain import Domain
from promisekeeper.compiler.guard import GuardExpressionError, evaluate_guard, referenced_names
from promisekeeper.compiler.invariants import check_invariants
from promisekeeper.compiler.projection import add_business_days
from promisekeeper.compiler.rules import derive_rules
from promisekeeper.errors import UnknownDomain
from promisekeeper.schemas import EvidenceRecord, ObservedTransition, Scope

D = Domain.load("domains", "fulfillment")
S = Scope(tenant="pk-test", domain="fulfillment", account="acct-1")

def ev(rid, frm, to, v, when=date(2026, 9, 1), state=None, kind="observed_transition", **kw):
    return EvidenceRecord(id=rid, scope=S, kind=kind, occurred_at=when, source="t", state=state or {},
                          transitions=[{"from": frm, "to": to, "value": v}], **kw)

# --- guard -------------------------------------------------------------
def test_and_or_short_circuit_like_python():
    assert evaluate_guard("destination_region == 'US' and order_value > 5", {"destination_region": "EU"}) is False
    assert evaluate_guard("destination_region == 'EU' or order_value > 5", {"destination_region": "EU"}) is True

def test_type_errors_surface_as_guard_errors():
    with pytest.raises(GuardExpressionError):
        evaluate_guard("order_value < 5000", {"order_value": "abc"})

def test_referenced_names_ignores_literals():
    assert referenced_names("tier == 'gold' and true") == {"tier"}

# --- invariants fail closed ---------------------------------------------
def test_invariant_fails_closed_when_applicability_unknown():
    res = check_invariants(D, {"destination_region": "EU"}, "total_days", 4.5)  # no 'tier'
    sla = [r for r in res if r.id == "GOLD_TIER_SLA"][0]
    assert sla.applied and not sla.passed

def test_invariant_with_bad_metric_type_does_not_raise():
    res = check_invariants(D, {"tier": "gold"}, "total_days", "x")
    assert any(r.applied and not r.passed for r in res)

# --- confidence / buffer --------------------------------------------------
def test_single_sample_is_below_buffer_threshold_so_buffer_is_reachable():
    r = derive_rules(D, [ev("a", "shipped", "delivered", 3.0)])[0]
    assert r.confidence < D.confidence_buffer_threshold

def test_more_samples_raise_confidence_and_spread_lowers_it():
    tight = derive_rules(D, [ev(f"t{i}", "shipped", "delivered", 3.0) for i in range(4)])[0]
    loose = derive_rules(D, [ev(f"l{i}", "shipped", "delivered", v) for i, v in enumerate([1.0, 6.0, 1.0, 6.0])])[0]
    assert tight.confidence >= D.confidence_buffer_threshold
    assert loose.confidence < tight.confidence

# --- recency / supersession ------------------------------------------------
def test_recent_evidence_outweighs_stale_evidence():
    old = [ev(f"o{i}", "a", "b", 3.0, when=date(2026, 1, 1)) for i in range(10)]
    new = [ev(f"n{i}", "a", "b", 6.0, when=date(2026, 9, 25)) for i in range(3)]
    assert derive_rules(D, old + new)[0].value > 5.9   # was 3.69 with a plain mean

def test_superseded_records_are_excluded():
    a = ev("a", "x", "y", 9.0)
    b = ev("b", "x", "y", 2.0, supersedes="a")
    assert derive_rules(D, [a, b])[0].value == 2.0

def test_rule_correction_not_double_counted_when_trace_present():
    trace = ev("t1", "x", "y", 5.0)
    corr = ev("c1", "x", "y", 5.0, kind="rule_correction", evidence_refs=["t1"])
    r = derive_rules(D, [trace, corr])[0]
    assert r.sample_size == 1
    # but if the trace itself wasn't recalled, the correction still counts
    assert derive_rules(D, [corr])[0].sample_size == 1

def test_intervention_evidence_does_not_pollute_baseline():
    base = ev("b", "shipped", "delivered", 4.0)
    iv = ev("i", "shipped", "delivered", 1.0, kind="successful_intervention", intervention="risk_pre_clearance")
    rules = derive_rules(D, [base, iv])
    plain = [r for r in rules if r.intervention is None][0]
    assert plain.value == 4.0 and len(rules) == 2

# --- schema hardening ----------------------------------------------------
@pytest.mark.parametrize("bad", ["../../tmp/x", "a/b", "", "x y", "-lead"])
def test_scope_rejects_unsafe_names(bad):
    with pytest.raises(ValidationError):
        Scope(tenant=bad, domain="fulfillment", account="a")

def test_negative_or_nan_durations_rejected():
    for v in (-1.0, float("nan"), float("inf")):
        with pytest.raises(ValidationError):
            ObservedTransition(**{"from": "a", "to": "b", "value": v})

def test_domain_name_cannot_escape_domains_dir():
    for bad in ("../project-state", "../../etc/passwd", "nope"):
        with pytest.raises(UnknownDomain):
            Domain.load("domains", bad)

def test_recall_query_is_filled_from_scope_and_state():
    q = D.render_recall_query({"order_value": 6000, "destination_region": "EU", "tier": "gold"}, S)
    assert "{" not in q and "acct-1" in q and "EU" in q

def test_recall_query_missing_fields_do_not_leave_braces():
    assert "{" not in D.render_recall_query({}, S)

# --- projection ---------------------------------------------------------------
def test_business_days_skip_weekends_and_round_up():
    fri = date(2026, 9, 25)
    assert fri.weekday() == 4
    assert add_business_days(fri, 1) == date(2026, 9, 28)      # Monday
    assert add_business_days(fri, 4.5) == date(2026, 10, 2)    # 5 business days
