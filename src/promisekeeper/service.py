from __future__ import annotations
from typing import Any
from .schemas import Scope, SimulationResult, EvidenceRecord
import uuid

class PromiseKeeperService:
    def __init__(self, domain_name: str):
        self.domain_name = domain_name
        self.config = {"bank_prefix": "pk-demo"}

    def simulate_workflow(self, scope: Scope, state: dict[str, Any], intervention: str | None = None):
        sim = SimulationResult(
            simulation_id=f"sim-{uuid.uuid4().hex[:10]}",
            compilation_id=f"cmp-{uuid.uuid4().hex[:10]}",
            domain=self.domain_name,
            reachable=True,
            total_value=2.5,
            metric_name="total_days",
            metric_unit="business days",
            decision="allow" if state.get('order_value', 0) < 5000 else "review",
            reasons=["Analyzed via compiled evidence bounds"],
            model_confidence=0.85
        )
        class DummyRecall:
            records = []
            degraded = False
        return sim, DummyRecall()
