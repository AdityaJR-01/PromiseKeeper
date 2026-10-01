from datetime import date, timedelta
from promisekeeper.memory import MemoryBackend
from promisekeeper.memory import store as st
from promisekeeper.schemas import EvidenceRecord, Scope
import pytest
from promisekeeper.errors import InvalidScope, UnknownSimulation

def scope(acct="acct-1", tenant="pk-test"):
    return Scope(tenant=tenant, domain="fulfillment", account=acct)

def rec(rid, s, v=1.0, when=date(2026, 9, 1)):
    return EvidenceRecord(id=rid, scope=s, kind="observed_transition", occurred_at=when, source="t",
                          transitions=[{"from": "a", "to": "b", "value": v}])

def test_append_is_idempotent_by_id():
    s = scope()
    assert st.append(s, rec("x", s)) is True
    assert st.append(s, rec("x", s)) is False
    assert len(st.all_for_scope(s)) == 1

def test_same_id_in_different_accounts_is_allowed():
    a, b = scope("acct-a"), scope("acct-b")
    st.append(a, rec("x", a)); st.append(b, rec("x", b))
    assert len(st.all_for_scope(a)) == 1 and len(st.all_for_scope(b)) == 1

def test_corrupt_line_is_skipped_not_fatal():
    s = scope()
    st.append(s, rec("ok", s))
    with st._scope_file(s).open("a") as f:
        f.write("{not json}\n")
    assert [r.id for r in st.all_for_scope(s)] == ["ok"]

def test_reset_one_account_keeps_other_accounts():
    a, b = scope("acct-a"), scope("acct-b")
    st.append(a, rec("a1", a)); st.append(b, rec("b1", b))
    assert st.reset_scope(a) is True
    assert st.all_for_scope(a) == [] and len(st.all_for_scope(b)) == 1
    assert st.reset_scope(a, all_accounts=True) is True
    assert st.all_for_scope(b) == []

def test_local_recall_returns_newest_records_not_oldest():
    s = scope(); m = MemoryBackend(); m.local_cap = 5
    for i in range(10):
        st.append(s, rec(f"r{i}", s, when=date(2026, 9, 1) + timedelta(days=i)))
    ids = [r.id for r in m.recall(s, "q").records]
    assert ids == ["r9", "r8", "r7", "r6", "r5"]

def test_retain_rejects_record_for_another_account():
    a, b = scope("acct-a"), scope("acct-b")
    with pytest.raises(InvalidScope):
        MemoryBackend().retain(a, rec("evil", b))
    assert st.all_for_scope(b) == []

def test_simulation_id_is_validated_and_scoped():
    with pytest.raises(UnknownSimulation):
        st.load_simulation(scope(), "../../etc/passwd")
    with pytest.raises(UnknownSimulation):
        st.load_simulation(scope(), "sim-0123456789")

# ---- hindsight backend with a fake client ----
class _Hit:
    def __init__(self, eid): self.metadata = {"evidence_id": eid}
class _Resp:
    def __init__(self, ids): self.results = [_Hit(i) for i in ids]
class FakeClient:
    def __init__(self, hits=(), fail=False): self.hits, self.fail, self.calls = list(hits), fail, []
    def create_bank(self, **k): self.calls.append(("bank", k))
    def retain(self, **k): self.calls.append(("retain", k))
    def recall(self, **k):
        self.calls.append(("recall", k))
        if self.fail: raise RuntimeError("down")
        return _Resp(self.hits)
    def get_version(self): return "x"

def hs(client, monkeypatch, **env):
    monkeypatch.setenv("PK_MEMORY_BACKEND", "hindsight")
    for k, v in env.items(): monkeypatch.setenv(k, v)
    m = MemoryBackend(); m._client = client
    return m

def test_hindsight_hits_ranked_first_then_local_topup(monkeypatch):
    s = scope()
    for i in range(4): st.append(s, rec(f"r{i}", s, when=date(2026, 9, 1) + timedelta(days=i)))
    m = hs(FakeClient(hits=["r0"]), monkeypatch)
    out = m.recall(s, "q")
    assert out.records[0].id == "r0" and len(out.records) == 4
    assert not out.degraded and out.local_topup == 3

def test_pure_semantic_mode_when_topup_disabled(monkeypatch):
    s = scope()
    for i in range(3): st.append(s, rec(f"r{i}", s))
    m = hs(FakeClient(hits=["r1"]), monkeypatch, PK_RECALL_TOPUP="false")
    assert [r.id for r in m.recall(s, "q").records] == ["r1"]

def test_zero_hits_with_local_data_is_flagged_degraded(monkeypatch):
    s = scope(); st.append(s, rec("r0", s))
    out = hs(FakeClient(hits=[]), monkeypatch, PK_RECALL_TOPUP="false").recall(s, "q")
    assert out.degraded is True

def test_hindsight_error_falls_back_to_local_and_is_degraded(monkeypatch):
    s = scope(); st.append(s, rec("r0", s))
    out = hs(FakeClient(fail=True), monkeypatch).recall(s, "q")
    assert [r.id for r in out.records] == ["r0"] and out.degraded and not out.hindsight_reachable

def test_hit_for_another_account_never_hydrates(monkeypatch):
    a, b = scope("acct-a"), scope("acct-b")
    st.append(b, rec("secret", b))
    out = hs(FakeClient(hits=["secret"]), monkeypatch, PK_RECALL_TOPUP="false").recall(a, "q")
    assert out.records == []

def test_recall_uses_strict_tag_match_and_retain_is_async_with_document_id(monkeypatch):
    s = scope(); c = FakeClient(); m = hs(c, monkeypatch)
    m.retain(s, rec("r0", s)); m.recall(s, "q")
    kinds = dict((k, v) for k, v in c.calls if k in ("retain", "recall"))
    assert kinds["recall"]["tags_match"] == "all_strict" and "acct-1" in kinds["recall"]["tags"]
    assert kinds["retain"]["retain_async"] is True and kinds["retain"]["document_id"] == "r0"

def test_duplicate_retain_is_not_sent_to_hindsight_twice(monkeypatch):
    s = scope(); c = FakeClient(); m = hs(c, monkeypatch)
    m.retain(s, rec("r0", s)); m.retain(s, rec("r0", s))
    assert sum(1 for k, _ in c.calls if k == "retain") == 1
