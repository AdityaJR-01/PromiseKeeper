from datetime import date
import pytest
from fastapi.testclient import TestClient

from promisekeeper import api
from promisekeeper.cli import main as cli_main
from promisekeeper.errors import InvalidScope, InvalidState, UnknownIntervention
from promisekeeper.memory import store as st
from promisekeeper.schemas import EvidenceRecord, Scope
from promisekeeper.seed import seed_demo
from promisekeeper.service import PromiseKeeperService

EU = {"tier": "gold", "destination_region": "EU", "order_value": 6000}

def sc(acct="acct-gold-01"):
    return Scope(tenant="pk-demo", domain="fulfillment", account=acct)

def trace(tid, s, legs=(0.5, 0.5, 5.0), state=None, when=date(2026, 9, 25)):
    stages = ["payment_authorized", "picked", "shipped", "delivered"]
    return EvidenceRecord(id=tid, scope=s, kind="observed_transition", occurred_at=when, source="ops",
                          state=state or EU,
                          transitions=[{"from": a, "to": b, "value": v} for (a, b), v in zip(zip(stages, stages[1:]), legs)])

@pytest.fixture
def seeded():
    svc = PromiseKeeperService("fulfillment"); s = sc(); seed_demo(s, svc.memory)
    return svc, s

# ---- service ----
def test_seeded_demo_blocks_and_offers_an_evidence_backed_alternative(seeded):
    svc, s = seeded
    sim, _ = svc.simulate_workflow(s, EU)
    assert sim.decision == "block" and sim.total_value > 3
    alt = sim.alternatives[0]
    assert alt["intervention"] == "risk_pre_clearance" and alt["decision"] == "allow"
    sim2, _ = svc.simulate_workflow(s, EU, "risk_pre_clearance")
    assert sim2.decision == "allow" and sim2.total_value <= 3 and sim2.intervention == "risk_pre_clearance"

def test_intervention_without_evidence_is_insufficient_not_a_silent_noop():
    svc = PromiseKeeperService("fulfillment"); s = sc("acct-x")
    for i, (a, b, v) in enumerate([("payment_authorized", "picked", .5), ("picked", "shipped", .5), ("shipped", "delivered", 3.5)]):
        svc.memory.retain(s, EvidenceRecord(id=f"e{i}", scope=s, kind="observed_transition", occurred_at=date(2026, 9, 1),
                                            source="t", state={"destination_region": "EU"}, transitions=[{"from": a, "to": b, "value": v}]))
    sim, _ = svc.simulate_workflow(s, EU, "risk_pre_clearance")
    assert sim.decision == "insufficient_evidence"

def test_unknown_intervention_rejected():
    with pytest.raises(UnknownIntervention):
        PromiseKeeperService("fulfillment").simulate_workflow(sc(), EU, "nope")

def test_missing_state_field_is_rejected_not_allowed():
    svc = PromiseKeeperService("fulfillment")
    with pytest.raises(InvalidState):
        svc.simulate_workflow(sc(), {"destination_region": "EU"})   # no tier

def test_account_is_a_hard_key():
    with pytest.raises(InvalidScope):
        PromiseKeeperService("fulfillment").simulate_workflow(Scope(tenant="pk-demo", domain="fulfillment"), EU)

def test_single_sample_path_gets_buffer_and_review():
    svc = PromiseKeeperService("fulfillment"); s = sc("acct-y")
    for i, (a, b, v) in enumerate([("payment_authorized", "picked", .5), ("picked", "shipped", .5), ("shipped", "delivered", 1.0)]):
        svc.memory.retain(s, EvidenceRecord(id=f"e{i}", scope=s, kind="observed_transition", occurred_at=date(2026, 9, 1),
                                            source="t", state={"destination_region": "EU"}, transitions=[{"from": a, "to": b, "value": v}]))
    sim, _ = svc.simulate_workflow(s, {"tier": "silver", "destination_region": "EU", "placed_at": "2026-09-25"})
    assert sim.buffer_applied == 1.0 and sim.decision == "review"
    assert sim.projected_date_buffered > sim.projected_date

def test_learning_continues_past_the_old_25_record_window():
    svc = PromiseKeeperService("fulfillment"); s = sc("acct-z")
    mk = lambda rid, v, d: EvidenceRecord(id=rid, scope=s, kind="observed_transition", occurred_at=d, source="t",
                                          state={"destination_region": "EU"}, transitions=[{"from": "payment_authorized", "to": "delivered", "value": v}])
    for i in range(30): svc.memory.retain(s, mk(f"old{i}", 2.0, date(2026, 8, 1)))
    before, _ = svc.simulate_workflow(s, {"tier": "silver", "destination_region": "EU"})
    for i in range(5): svc.memory.retain(s, mk(f"new{i}", 9.0, date(2026, 9, 28)))
    after, _ = svc.simulate_workflow(s, {"tier": "silver", "destination_region": "EU"})
    assert after.total_value > before.total_value + 2   # frozen window would stay at 2.0

def test_outcome_moves_next_prediction_and_is_not_double_counted(seeded):
    svc, s = seeded
    sim1, _ = svc.simulate_workflow(s, EU)
    res = svc.record_outcome(s, sim1, trace("t1", s))
    assert res.classification == "contradicted" and res.proposed_corrections
    rules_ids = [r.id for r in st.all_for_scope(s)]
    assert "corr-t1-shipped-delivered" in rules_ids
    sim2, _ = svc.simulate_workflow(s, EU)
    assert sim2.total_value > sim1.total_value
    leg = [p for p in sim2.path if p.to_state == "delivered"][0]
    assert leg.derived_from.count("t1") == 1 and "corr-t1-shipped-delivered" not in leg.derived_from

def test_record_outcome_is_idempotent_by_trace_id(seeded):
    svc, s = seeded
    sim, _ = svc.simulate_workflow(s, EU)
    n0 = len(st.all_for_scope(s))
    r1 = svc.record_outcome(s, sim, trace("t1", s))
    n1 = len(st.all_for_scope(s))
    r2 = svc.record_outcome(s, sim, trace("t1", s))
    assert r2.reconciliation_id == r1.reconciliation_id
    assert len(st.all_for_scope(s)) == n1 > n0
    assert len(st.list_reconciliations(s)) == 1

def test_trace_id_collision_with_different_content_is_rejected(seeded):
    svc, s = seeded
    sim, _ = svc.simulate_workflow(s, EU)
    with pytest.raises(InvalidState):
        svc.record_outcome(s, sim, trace("seed-eu-1", s))

def test_trace_for_another_account_is_rejected(seeded):
    svc, s = seeded
    sim, _ = svc.simulate_workflow(s, EU)
    with pytest.raises(InvalidScope):
        svc.record_outcome(s, sim, trace("evil", sc("victim")))

# ---- API ----
@pytest.fixture
def client():
    return TestClient(api.app, raise_server_exceptions=False)

def body(s=None, **kw):
    s = s or sc()
    return {"domain": "fulfillment", "scope": s.model_dump(exclude_none=True), "state": EU, **kw}

def test_api_end_to_end_simulate_observe_history(client, seeded):
    _, s = seeded
    r = client.post("/simulate", json=body(state={**EU, "placed_at": "2026-09-25"}))
    assert r.status_code == 200
    sim = r.json()
    assert sim["decision"] == "block" and sim["projected_date"] and sim["alternatives"]
    obs = {"domain": "fulfillment", "scope": s.model_dump(exclude_none=True), "simulation_id": sim["simulation_id"],
           "trace": trace("api-t1", s).model_dump(mode="json", by_alias=True)}
    r = client.post("/observe", json=obs)
    assert r.status_code == 200 and r.json()["predicted_total"] == sim["total_value"]
    h = client.get("/history", params={"tenant": "pk-demo", "domain": "fulfillment", "account": "acct-gold-01"}).json()
    assert len(h) == 1 and h[0]["account"] == "acct-gold-01" and h[0]["trace_id"] == "api-t1"
    # replay -> same result, still one history row
    assert client.post("/observe", json=obs).json()["reconciliation_id"] == r.json()["reconciliation_id"]
    assert len(client.get("/history", params={"tenant": "pk-demo", "domain": "fulfillment", "account": "acct-gold-01"}).json()) == 1

def test_history_is_scoped_per_account(client, seeded):
    _, s = seeded
    sim = client.post("/simulate", json=body()).json()
    client.post("/observe", json={"domain": "fulfillment", "scope": s.model_dump(exclude_none=True), "simulation_id": sim["simulation_id"],
                                  "trace": trace("t9", s).model_dump(mode="json", by_alias=True)})
    other = client.get("/history", params={"tenant": "pk-demo", "domain": "fulfillment", "account": "someone-else"})
    assert other.status_code == 200 and other.json() == []

def test_observe_requires_a_real_simulation_id(client, seeded):
    _, s = seeded
    r = client.post("/observe", json={"domain": "fulfillment", "scope": s.model_dump(exclude_none=True), "simulation_id": "sim-doesnotexist",
                                      "trace": trace("t", s).model_dump(mode="json", by_alias=True)})
    assert r.status_code == 404

def test_observe_cannot_use_another_accounts_simulation(client, seeded):
    _, s = seeded
    sim = client.post("/simulate", json=body()).json()
    other = sc("acct-other")
    r = client.post("/observe", json={"domain": "fulfillment", "scope": other.model_dump(exclude_none=True), "simulation_id": sim["simulation_id"],
                                      "trace": trace("t", other).model_dump(mode="json", by_alias=True)})
    assert r.status_code == 404

def test_observe_rejects_trace_scoped_to_someone_else(client, seeded):
    _, s = seeded
    sim = client.post("/simulate", json=body()).json()
    r = client.post("/observe", json={"domain": "fulfillment", "scope": s.model_dump(exclude_none=True), "simulation_id": sim["simulation_id"],
                                      "trace": trace("evil", sc("victim")).model_dump(mode="json", by_alias=True)})
    assert r.status_code == 422
    assert st.all_for_scope(sc("victim")) == []

@pytest.mark.parametrize("payload,code", [
    ({"domain": "../project-state"}, 404),
    ({"domain": "deployment"}, 404),
    ({"scope": {"tenant": "../../tmp/x", "domain": "fulfillment", "account": "a"}}, 422),
    ({"state": {"destination_region": "EU"}}, 422),          # missing tier
    ({"intervention": "nope"}, 422),
    ({"domain": "fulfillment", "scope": {"tenant": "t", "domain": "other", "account": "a"}}, 422),  # domain mismatch
])
def test_simulate_bad_input_gets_4xx_not_500(client, payload, code):
    assert client.post("/simulate", json={**body(), **payload}).status_code == code

def test_cold_start_is_honest_over_api(client):
    j = client.post("/simulate", json=body(sc("brand-new"))).json()
    assert j["decision"] == "insufficient_evidence" and j["total_value"] == 0.0 and j["memories_used"] == 0

def test_health_reports_local_backend(client):
    assert client.get("/health").json() == {"memory_backend": "local", "hindsight_reachable": None}

# ---- CLI ----
def test_cli_seed_then_demo_blocks(capsys):
    assert cli_main(["demo", "--json"]) == 0
    import json
    assert json.loads(capsys.readouterr().out)["decision"] == "insufficient_evidence"
    assert cli_main(["seed"]) == 0; capsys.readouterr()
    assert cli_main(["demo", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["decision"] == "block" and out["memories_used"] == 7 and out["alternatives"]

def test_cli_reset_requires_yes_and_only_clears_that_account(capsys):
    cli_main(["seed"]); cli_main(["seed", "--account", "acct-2"]); capsys.readouterr()
    assert cli_main(["reset", "--domain", "fulfillment"]) == 1          # no --yes
    assert cli_main(["reset", "--domain", "fulfillment", "--yes"]) == 0
    assert st.all_for_scope(sc("acct-gold-01")) == []
    assert len(st.all_for_scope(sc("acct-2"))) == 7

def test_cli_rejects_bad_scope_cleanly(capsys):
    with pytest.raises(Exception):
        cli_main(["seed", "--account", "../x"])   # pydantic ValidationError, not a silent traversal
