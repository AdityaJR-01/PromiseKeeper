from datetime import date
from promisekeeper.schemas import EvidenceRecord, Scope
from promisekeeper.service import PromiseKeeperService

def _scope(account="acct-gold-01"):
    return Scope(tenant="pk-demo", domain="fulfillment", account=account)

def _seed(svc, scope):
    for i, (frm, to, val) in enumerate([("payment_authorized", "picked", 0.5), ("picked", "shipped", 0.5), ("shipped", "delivered", 3.5)]):
        svc.memory.retain(scope, EvidenceRecord(id=f"ev-seed-{i}", scope=scope, kind="observed_transition",
            occurred_at=date(2026, 9, 10), source="seed", state={"destination_region": "EU"},
            transitions=[{"from": frm, "to": to, "value": val}]))

def test_cold_start(tmp_path, monkeypatch):
    monkeypatch.setenv("PK_STORE_DIR", str(tmp_path)); monkeypatch.setenv("PK_MEMORY_BACKEND", "local")
    svc = PromiseKeeperService("fulfillment")
    sim, recall = svc.simulate_workflow(_scope(), {"tier": "gold", "destination_region": "EU", "order_value": 6000})
    assert sim.decision == "insufficient_evidence" and sim.total_value == 0.0

def test_seeded_blocked(tmp_path, monkeypatch):
    monkeypatch.setenv("PK_STORE_DIR", str(tmp_path)); monkeypatch.setenv("PK_MEMORY_BACKEND", "local")
    svc = PromiseKeeperService("fulfillment"); scope = _scope(); _seed(svc, scope)
    sim, recall = svc.simulate_workflow(scope, {"tier": "gold", "destination_region": "EU", "order_value": 6000})
    assert sim.total_value == 4.5 and sim.decision == "block" and len(recall.records) == 3

def test_feedback(tmp_path, monkeypatch):
    monkeypatch.setenv("PK_STORE_DIR", str(tmp_path)); monkeypatch.setenv("PK_MEMORY_BACKEND", "local")
    svc = PromiseKeeperService("fulfillment"); scope = _scope(); _seed(svc, scope)
    state = {"tier": "gold", "destination_region": "EU", "order_value": 6000}
    sim1, _ = svc.simulate_workflow(scope, state)
    trace = EvidenceRecord(id="ev-trace-1", scope=scope, kind="observed_transition", occurred_at=date(2026, 9, 25),
        source="ops-system", state=state,
        transitions=[{"from": "payment_authorized", "to": "picked", "value": 0.5}, {"from": "picked", "to": "shipped", "value": 0.5}, {"from": "shipped", "to": "delivered", "value": 5.0}])
    result = svc.record_outcome(scope, sim1, trace)
    assert result.classification == "contradicted" and result.proposed_corrections
    sim2, _ = svc.simulate_workflow(scope, state)
    assert sim2.total_value > sim1.total_value

def test_isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("PK_STORE_DIR", str(tmp_path)); monkeypatch.setenv("PK_MEMORY_BACKEND", "local")
    svc = PromiseKeeperService("fulfillment"); _seed(svc, _scope("acct-gold-01"))
    sim, recall = svc.simulate_workflow(_scope("acct-other"), {"tier": "gold", "destination_region": "EU"})
    assert len(recall.records) == 0
