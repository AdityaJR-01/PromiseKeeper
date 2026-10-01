# 🤖 PromiseKeeper: AI Delivery Risk & Fulfillment Agent

An AI-powered supply chain risk simulator that predicts delivery timelines and assesses B2B order fulfillment risk. PromiseKeeper abandons static SLA heuristics in favor of **Hindsight persistent agent memory**, allowing the system to dynamically learn from past SLA breaches, unmodeled delays, and successful interventions.

Instead of statically assuming a Gold-tier account takes 3 days, PromiseKeeper recalls historical deviations, adjusts pathfinding coefficients on the fly, and applies protective buffers when model confidence drops, preventing costly enterprise SLA violations.

## ✨ Features

- **🧠 Hindsight Persistent Memory** — Retains project-level fulfillment traces, account preferences, and historical delays across orders.
- **⚙️ Reality Compiler Engine** — A deterministic graph algorithm (Dijkstra) that calculates the lowest-cost fulfillment path based on dynamic, memory-adjusted coefficients.
- **🔄 Reconcile & Retain Pipeline** — Compares predicted timelines against observed reality, automatically retaining `ProposedCorrections` to fix future estimates.
- **🛡️ Strict Typed Hydration** — Bridges the gap between LLM semantic recall and deterministic execution: every memory is retained with its `evidence_id` as Hindsight metadata, and recall hits are hydrated from the local canonical store into strict Pydantic `EvidenceRecord` models (no prose parsing).
- **🚫 SLA Breach Prevention** — Automatically blocks or flags promises that violate invariant contract rules using memory-injected reality checks.
- **⚖️ Calibrated Confidence Buffers** — Confidence grows with sample count and shrinks with spread; a single observation (confidence 0.50) triggers a conservative buffer, three consistent ones (0.75) do not.
- **🕒 Recency-Weighted Learning** — Observations are weighted by a 30-day half-life (`compilation.recency_half_life_days`), and `supersedes`/`superseded_by` evidence is excluded, so a policy change converges instead of being averaged away.
- **🧯 Interventions** — Retained `successful_intervention` evidence (e.g. `risk_pre_clearance`) trains intervention-specific rules. A blocked or reviewed promise lists evidence-backed alternatives; an intervention with no evidence reports `insufficient_evidence` instead of pretending.
- **📊 Next-Gen Glassmorphism UI** — Real-time TailwindCSS dashboard tracking simulation outcomes, trace history, and API documentation modules.
- **🔌 Graceful Degradation** — Always functions via local scope-wide hydration if the Hindsight API is unreachable or offline.

## 🛠️ Tech Stack

- **Frontend:** HTML5 • TailwindCSS • Modern Vanilla JavaScript • Glassmorphism UI
- **Backend:** Python 3.10+ • FastAPI • Pydantic v2 • Uvicorn
- **Agent Memory:** Hindsight (Semantic retrieval & persistence)
- **Engine:** Custom Reality Compiler (AST Expression Evaluator, Graph Pathfinding)
- **Testing:** Pytest

## 🧠 Memory & Compilation Architecture

    +-------------------------------------------------+
    |             Operations Manager                  |
    +-----------------------+-------------------------+
                            |
                            | Submits Order Context (Value, Region)
                            v
    +-------------------------------------------------+
    |                 FastAPI Backend                 |
    +-----------------------+-------------------------+
                            |
        1. Semantic Query Trigger   | (Scoped by Tenant/Domain)
                            v
    +-------------------------------------------------+
    |                Hindsight Server                 |
    |          (Persistent Memory Bank Layer)         |
    +-----------------------+-------------------------+
                            |
        2. Returns Ranked Hits      | (metadata: evidence_id)
                            v
    +-------------------------------------------------+
    |            Typed Hydration Bridge               |
    |      - Looks up evidence_id in the local store  |
    |      - Hydrates strict Pydantic EvidenceRecords |
    |      - Tops up with newest local records        |
    +-----------------------+-------------------------+
                            |
        3. Verified Evidence Base   |
                            v
    +-------------------------------------------------+
    |           Reality Compiler Engine               |
    |  - Applies deviations to transition rules      |
    |  - Calculates lowest-cost path (Dijkstra)       |
    +-----------------------+-------------------------+
                            |
        4. Timeline & Risk Decision |
                            v
    +-------------------------------------------------+
    |         Client Dashboard (Glassmorphism UI)     |
    +-----------------------+-------------------------+
                            |
        5. Post-Fulfillment         | (Observed vs Predicted)
                            v
    +-------------------------------------------------+
    |          Reconciliation & Retain Engine         |
    |      - Calculates residual delta                |
    |      - Retains new coefficient corrections      |
    +-----------------------+-------------------------+

## 🚀 Run Locally

### 1. Install Dependencies

    make install

### 2. (Optional) Start a Hindsight Server

The default `PK_MEMORY_BACKEND=local` needs no server. To use Hindsight (Docker + an LLM key, which Hindsight uses for fact extraction):

    docker run --rm -it -p 8888:8888 -p 9999:9999 \
      -e HINDSIGHT_API_LLM_API_KEY=$OPENAI_API_KEY \
      -v $HOME/.hindsight-docker:/home/hindsight/.pg0 \
      ghcr.io/vectorize-io/hindsight:latest

    export PK_MEMORY_BACKEND=hindsight   # or put it in .env (see .env.example)

If Hindsight is down or returns nothing, PromiseKeeper falls back to the local store and reports `degraded_recall: true`.

### 3. Start the FastAPI Backend & Dashboard

    make seed                                    # load deterministic demo evidence (idempotent)
    uvicorn promisekeeper.api:app --reload --port 8000

Open `http://localhost:8000` in your browser to view the interactive dashboard. Without `make seed` (or real `/observe` traffic) the engine honestly answers `insufficient_evidence`.

### 4. CLI, demo and audit

    pk seed                                   # or: python -m promisekeeper.cli seed
    pk demo                                   # gold EU order -> BLOCK + evidence-backed alternative
    pk reset --domain fulfillment --yes       # clears ONE account (add --all-accounts for the whole bank)
    make test                                 # pytest on the local backend, no network
    make audit                                # tests + seeded end-to-end demo + prohibited-word / .env checks

## 📡 API Reference

All scope fields (`tenant`, `domain`, `account`) must be 1–64 characters of letters, digits, `_` or `-`. `account` is a required scope key for the `fulfillment` domain. Errors: `404` unknown domain / simulation id, `422` invalid scope, state, intervention or trace.

### `POST /simulate`

Recalls memory for the scope, compiles transition rules from the evidence (guards, recency weights, confidence), finds the cheapest path with Dijkstra, checks invariants, and returns a decision. The result is stored so it can later be reconciled. The `state` must contain every field the domain's guards and invariants read (`tier`, `destination_region` for `fulfillment`); a request that omits one is rejected rather than silently skipping the SLA check.

**Request:**

    {
      "domain": "fulfillment",
      "scope": {"tenant": "pk-demo", "domain": "fulfillment", "account": "acct-gold-01"},
      "state": {"order_value": 6000, "destination_region": "EU", "tier": "gold", "placed_at": "2026-09-28"},
      "intervention": null
    }

**Response (seeded demo):**

    {
      "simulation_id": "sim-1cbe5ae406",
      "decision": "block",
      "reachable": true,
      "total_value": 4.529,
      "metric_unit": "business days",
      "projected_date": "2026-10-05",
      "reasons": ["Blocked by invariant GOLD_TIER_SLA: violated: total_days <= 3 (given total_days=4.529)"],
      "alternatives": [{"intervention": "risk_pre_clearance", "total_value": 2.9, "lead_time_days": 0.5, "decision": "allow"}],
      "memories_used": 7,
      ...
    }

`decision` is one of `allow`, `review` (low confidence -> buffer applied, or a warning invariant failed), `block` (a blocking invariant fails) or `insufficient_evidence` (no evidence-backed path yet).

### `POST /observe`

Records what actually happened. Reconciles the trace against the simulation named by `simulation_id` (the promise that was made), retains the trace and any proposed corrections, and appends to the scope's history. `trace.scope` must equal `scope`. Idempotent by `trace.id`: replaying a trace returns the stored reconciliation and retains nothing twice.

    {
      "domain": "fulfillment",
      "scope": {"tenant": "pk-demo", "domain": "fulfillment", "account": "acct-gold-01"},
      "simulation_id": "sim-1cbe5ae406",
      "trace": {"id": "ops-4411", "scope": {"tenant": "pk-demo", "domain": "fulfillment", "account": "acct-gold-01"},
                "kind": "observed_transition", "occurred_at": "2026-10-02", "source": "ops-system",
                "state": {"order_value": 6000, "destination_region": "EU", "tier": "gold"},
                "transitions": [{"from": "shipped", "to": "delivered", "value": 5.0}]}
    }

### `GET /history?tenant=&domain=&account=`

Reconciliation history for one scope (empty until `/observe` has been called; nothing is fabricated).

### `GET /health`

`{"memory_backend": "local" | "hindsight", "hindsight_reachable": null | true | false}`

## ⚠️ Known limitations

- Dijkstra returns the *fastest* observed route, which is optimistic when several routes exist. Confidence and the conservative buffer partly compensate; a percentile-based estimate is future work.
- A predicted stage that never happens (`missing`) marks the model invalid but proposes no correction.
- `scope.relevance_keys` in the domain YAML is not consumed yet.
- Business-day projection skips weekends only (no holiday calendar).
- Not yet exercised against a live Hindsight server in CI; the Hindsight path is covered by tests with a fake client.
