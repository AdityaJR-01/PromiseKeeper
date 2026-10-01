from datetime import date
from promisekeeper.compiler.domain import Domain
from promisekeeper.compiler.graph import shortest_path
from promisekeeper.compiler.invariants import check_invariants
from promisekeeper.compiler.rules import derive_rules
from promisekeeper.schemas import EvidenceRecord, Scope

DOMAINS_DIR = "domains"  # tests run from repo root

def _evidence(scope, frm, to, value, state=None, kind="observed_transition", rec_id=None):
    return EvidenceRecord(
        id=rec_id or f"ev-{frm}-{to}-{value}", scope=scope, kind=kind,
        occurred_at=date.today(), source="test", state=state or {},
        transitions=[{"from": frm, "to": to, "value": value}],
    )

def test_insufficient_evidence_on_cold_start():
    domain = Domain.load(DOMAINS_DIR, "fulfillment")
    path, total, conf = shortest_path(domain, {"tier": "gold", "destination_region": "EU"}, [])
    assert path is None

def test_learns_a_real_path_from_retained_evidence():
    domain = Domain.load(DOMAINS_DIR, "fulfillment")
    scope = Scope(tenant="pk-test", domain="fulfillment", account="acct-1")
    evidence = [
        _evidence(scope, "payment_authorized", "picked", 1.0),
        _evidence(scope, "picked", "shipped", 1.0),
        _evidence(scope, "shipped", "delivered", 1.0),
    ]
    rules = derive_rules(domain, evidence)
    path, total, conf = shortest_path(domain, {"tier": "gold", "destination_region": "EU"}, rules)
    assert path is not None
    assert total == 3.0

def test_guard_scopes_evidence_to_matching_states_only():
    domain = Domain.load(DOMAINS_DIR, "fulfillment")
    scope = Scope(tenant="pk-test", domain="fulfillment", account="acct-1")
    evidence = [_evidence(scope, "shipped", "delivered", 3.5, state={"destination_region": "EU"})]
    rules = derive_rules(domain, evidence)
    path_us, _, _ = shortest_path(domain, {"destination_region": "US"}, rules)
    assert path_us is None

def test_gold_tier_invariant_blocks_when_sla_exceeded():
    domain = Domain.load(DOMAINS_DIR, "fulfillment")
    results = check_invariants(domain, {"tier": "gold"}, "total_days", 5.0)
    blocking = [r for r in results if r.applied and not r.passed and r.severity == "blocking"]
    assert blocking and blocking[0].id == "GOLD_TIER_SLA"

def test_gold_tier_invariant_passes_within_sla():
    domain = Domain.load(DOMAINS_DIR, "fulfillment")
    results = check_invariants(domain, {"tier": "gold"}, "total_days", 2.0)
    blocking = [r for r in results if r.applied and not r.passed and r.severity == "blocking"]
    assert not blocking

def test_invariant_not_applied_to_non_gold_tier():
    domain = Domain.load(DOMAINS_DIR, "fulfillment")
    results = check_invariants(domain, {"tier": "silver"}, "total_days", 9.0)
    sla = [r for r in results if r.id == "GOLD_TIER_SLA"][0]
    assert sla.applied is False
