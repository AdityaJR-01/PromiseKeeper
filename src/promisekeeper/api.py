from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError
from typing import Any, Optional
from pathlib import Path

from .errors import InvalidScope, PromiseKeeperError, UnknownDomain, UnknownSimulation
from .memory import MemoryBackend
from .memory import store as local_store
from .schemas import EvidenceRecord, Scope
from .service import PromiseKeeperService

app = FastAPI(title="PromiseKeeper Execution API")

ROOT_DIR = Path(__file__).resolve().parents[2]
frontend_dir = ROOT_DIR / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")


# Domain errors become real HTTP statuses instead of 500s.
@app.exception_handler(UnknownDomain)
@app.exception_handler(UnknownSimulation)
async def _not_found(_, exc):
    return JSONResponse(status_code=404, content={"detail": str(exc)})

@app.exception_handler(PromiseKeeperError)
async def _unprocessable(_, exc):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


class SimulationRequest(BaseModel):
    domain: str
    scope: Scope               # validated: charset-restricted tenant/domain/account
    state: dict[str, Any]
    intervention: Optional[str] = None

class ObserveRequest(BaseModel):
    domain: str
    scope: Scope
    simulation_id: str         # must be an id returned by /simulate for this scope
    trace: EvidenceRecord      # trace.scope must equal `scope`


@app.get("/")
def serve_dashboard():
    return FileResponse(frontend_dir / "index.html")

@app.get("/health")
def health():
    mem = MemoryBackend()
    return {"memory_backend": mem.mode, "hindsight_reachable": mem.ping()}

@app.post("/simulate")
def run_simulation(req: SimulationRequest):
    svc = PromiseKeeperService(req.domain)
    sim, recall = svc.simulate_workflow(req.scope, req.state, req.intervention)
    return {
        "simulation_id": sim.simulation_id,
        "decision": sim.decision,
        "reachable": sim.reachable,
        "total_value": sim.total_value,
        "metric_unit": sim.metric_unit,
        "projected_date": sim.projected_date,
        "projected_date_buffered": sim.projected_date_buffered,
        "model_confidence": sim.model_confidence,
        "buffer_applied": sim.buffer_applied,
        "intervention": sim.intervention,
        "reasons": sim.reasons,
        "invariants": [i.model_dump() for i in sim.invariants],
        "alternatives": sim.alternatives,
        "memories_used": len(recall.records),   # a count, matching what the dashboard shows
        "degraded_recall": recall.degraded,
        "path": [p.model_dump() for p in sim.path],
    }

@app.post("/observe")
def observe_outcome(req: ObserveRequest):
    """Reconcile a real outcome against the simulation identified by
    `simulation_id` (the promise actually made), retain the trace and proposed
    corrections, and log the reconciliation. Idempotent by trace.id."""
    if req.scope.domain != req.domain:
        raise InvalidScope("scope.domain must equal domain")
    svc = PromiseKeeperService(req.domain)
    sim = local_store.load_simulation(req.scope, req.simulation_id)
    return svc.record_outcome(req.scope, sim, req.trace).model_dump(mode="json")

@app.get("/history")
def get_reconciliation_history(tenant: str = Query(...), domain: str = Query(...), account: str = Query(...)):
    """Reconciliation history for ONE scope. Empty until /observe has been called."""
    try:
        scope = Scope(tenant=tenant, domain=domain, account=account)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=f"invalid scope: {e.errors()}")
    return local_store.list_reconciliations(scope)
