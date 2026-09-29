# 🤖 PromiseKeeper: AI Delivery Risk & Fulfillment Agent

An AI-powered supply chain risk simulator that predicts delivery timelines and assesses B2B order fulfillment risk. PromiseKeeper abandons static SLA heuristics in favor of **Hindsight persistent agent memory**, allowing the system to dynamically learn from past SLA breaches, unmodeled delays, and successful interventions.

Instead of statically assuming a Gold-tier account takes 3 days, PromiseKeeper recalls historical deviations, adjusts pathfinding coefficients on the fly, and applies protective buffers when model confidence drops, preventing costly enterprise SLA violations.

## ✨ Features

- **🧠 Hindsight Persistent Memory** — Retains project-level fulfillment traces, account preferences, and historical delays across orders.
- **⚙️ Reality Compiler Engine** — A deterministic graph algorithm (Dijkstra) that calculates the lowest-cost fulfillment path based on dynamic, memory-adjusted coefficients.
- **🔄 Reconcile & Retain Pipeline** — Compares predicted timelines against observed reality, automatically retaining `ProposedCorrections` to fix future estimates.
- **🛡️ Strict Typed Hydration** — Bridges the gap between LLM semantic recall and deterministic execution by extracting UUIDs from Hindsight prose and hydrating them into strict Pydantic `EvidenceRecord` models.
- **🚫 SLA Breach Prevention** — Automatically blocks or flags promises that violate invariant contract rules using memory-injected reality checks.
- **⚖️ Calibrated Confidence Buffers** — Distinguishes between highly supported transitions and low-sample observations, applying conservative time buffers when model confidence is low.
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
        2. Returns Prose Memories   | (Past delays, SLA breaches)
                            v
    +-------------------------------------------------+
    |            Typed Hydration Bridge               |
    |      - Extracts UUIDs from semantic text        |
    |      - Hydrates strict Pydantic EvidenceRecords |
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

### 2. Start Hindsight Server (Docker Required)

    docker run -d -p 8888:8888 ghcr.io/vectorize-io/hindsight:latest

### 3. Start the FastAPI Backend & Dashboard

    uvicorn src.promisekeeper.api:app --reload --port 8000

Open `http://localhost:8000` in your browser to view the interactive dashboard.

## 📡 API Reference

### `POST /simulate`

Evaluates an order's fulfillment risk by querying Hindsight for semantic context, hydrating the context into strict Pydantic rules, and calculating paths via Dijkstra.

**Request:**

    {
      "domain": "fulfillment",
      "scope": {
        "tenant": "pk-demo",
        "domain": "fulfillment",
        "account": "acct-gold-01"
      },
      "state": {
        "order_value": 6000,
        "destination_region": "EU",
        "tier": "gold"
      }
    }

**Response:**

    {
      "decision": "review",
      "total_value": 3.5,
      "reasons": [
        "Analyzed via compiled evidence bounds"
      ],
      "memories_used": 2
    }

### `GET /history`

Returns a historical audit trail of trace reconciliations, showing where predicted execution deviated from real-world outcomes and what coefficients were modified.

**Response:**

    [
      {
        "trace_id": "TRC-8891-EU",
        "classification": "unmodeled",
        "residual_delta": 2.0,
        "unmodeled_states": [
          "customs_hold"
        ],
        "proposed_corrections": [
          {
            "kind": "new_transition",
            "value": 2.0
          }
        ]
      }
    ]
