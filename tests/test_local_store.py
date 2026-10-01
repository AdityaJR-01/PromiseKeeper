from datetime import date
from promisekeeper.schemas import EvidenceRecord, Scope
from promisekeeper.memory import store as local_store

def _rec(scope, rec_id="ev-1"):
    return EvidenceRecord(
        id=rec_id, scope=scope, kind="observed_transition", occurred_at=date.today(),
        source="test", transitions=[{"from": "shipped", "to": "delivered", "value": 3.0}],
    )

def test_retain_survives_a_fresh_read(tmp_path, monkeypatch):
    monkeypatch.setenv("PK_STORE_DIR", str(tmp_path))
    scope = Scope(tenant="pk-test", domain="fulfillment", account="acct-1")
    local_store.append(scope, _rec(scope))
    reloaded = local_store.all_for_scope(scope)
    assert len(reloaded) == 1
    assert reloaded[0].transitions[0].to_state == "delivered"

def test_account_scope_isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("PK_STORE_DIR", str(tmp_path))
    scope_a = Scope(tenant="pk-test", domain="fulfillment", account="acct-a")
    scope_b = Scope(tenant="pk-test", domain="fulfillment", account="acct-b")
    local_store.append(scope_a, _rec(scope_a, "ev-a"))
    assert len(local_store.all_for_scope(scope_a)) == 1
    assert local_store.all_for_scope(scope_b) == []

def test_reset_clears_only_that_scope_file(tmp_path, monkeypatch):
    monkeypatch.setenv("PK_STORE_DIR", str(tmp_path))
    scope = Scope(tenant="pk-test", domain="fulfillment", account="acct-1")
    local_store.append(scope, _rec(scope))
    assert local_store.reset_scope(scope) is True
    assert local_store.all_for_scope(scope) == []
    assert local_store.reset_scope(scope) is False
