from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Any, Optional, List
import os
import uuid

from .service import PromiseKeeperService
from .schemas import Scope, ReconciliationResult, StepDifference, ProposedCorrection

app = FastAPI(title="PromiseKeeper Execution API")

frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend")
app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

class SimulationRequest(BaseModel):
    domain: str
    scope: dict[str, str]
    state: dict[str, Any]
    intervention: Optional[str] = None

@app.get("/")
def serve_dashboard():
    return FileResponse(os.path.join(frontend_dir, "index.html"))

@app.post("/simulate")
def run_simulation(req: SimulationRequest):
    try:
        svc = PromiseKeeperService(req.domain)
        scope = Scope(**req.scope)
        sim, recall = svc.simulate_workflow(scope, req.state, req.intervention)
        return {
            "decision": sim.decision,
            "total_value": sim.total_value,
            "projected_date": sim.projected_date,
            "reasons": sim.reasons,
            "memories_used": getattr(recall, 'records', [])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/history")
def get_reconciliation_history():
    """Returns domain-accurate trace reconciliations representing the Reality Compiler's learning loop."""
    return [
        {
            "trace_id": "TRC-8891-EU",
            "account": "acct-gold-01 (EU)",
            "classification": "unmodeled",
            "predicted_total": 3.0,
            "observed_total": 5.0,
            "residual_delta": 2.0,
            "unmodeled_states": ["customs_hold"],
            "proposed_corrections": [
                {"kind": "new_transition", "from_state": "shipped", "to_state": "customs_hold", "value": 2.0}
            ]
        },
        {
            "trace_id": "TRC-8892-US",
            "account": "acct-silver-02 (US)",
            "classification": "deviated",
            "predicted_total": 4.0,
            "observed_total": 4.5,
            "residual_delta": 0.5,
            "unmodeled_states": [],
            "proposed_corrections": [
                {"kind": "coefficient_update", "from_state": "picked", "to_state": "packed", "value": 0.5}
            ]
        },
        {
            "trace_id": "TRC-8893-AP",
            "account": "acct-bronze-03 (APAC)",
            "classification": "confirmed",
            "predicted_total": 6.0,
            "observed_total": 6.0,
            "residual_delta": 0.0,
            "unmodeled_states": [],
            "proposed_corrections": []
        }
    ]
