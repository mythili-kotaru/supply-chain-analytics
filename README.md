# Supply Chain AI — Autonomous Ops Dashboard

> A production-grade, event-driven supply chain intelligence system built with LangGraph, FastMCP, A2A orchestration, and a Next.js real-time ops dashboard. Built for CVS Health AI Engineering.

---

## What Problem Are We Solving?

Supply chain ops managers at a company like CVS Health deal with hundreds of SKUs across multiple regions. The traditional workflow looks like this:

1. Someone notices a shelf is empty — **too late**
2. They manually query a spreadsheet or ERP system
3. They email procurement — more lag
4. By the time a PO is raised, there's already a stockout

**This system flips that entirely.** Instead of humans querying data reactively, autonomous AI agents continuously monitor inventory levels, forecast accuracy, and regional allocation — and surface proposals for human approval *before* things go wrong.

The human's job is reduced to a single action: **Approve or Reject.**

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Next.js Ops Dashboard                     │
│     InventoryAlerts │ Approval Queue │ Forecast Health       │
└────────────────────────────┬────────────────────────────────┘
                             │ REST / SSE (Day 2+)
┌────────────────────────────▼────────────────────────────────┐
│              FastAPI Dashboard API  (Day 2)                  │
│         APScheduler: 60s inventory · 5min MAPE scan         │
└──────┬──────────────────┬──────────────────────┬────────────┘
       │                  │                      │
┌──────▼──────┐   ┌───────▼────────┐   ┌────────▼────────┐
│  LangGraph  │   │  FastMCP Server │   │  PostgreSQL +   │
│  Supervisor │   │  (hybrid search │   │  pgvector       │
│  + HITL     │   │   RBAC + RBAC)  │   │  (embeddings +  │
│  interrupt()│   └────────────────┘   │   inventory)    │
└──────┬──────┘                        └─────────────────┘
       │
  ┌────┴──────────────────┐
  │   A2A Sub-Agents      │
  ├───────────────────────┤
  │  Allocation Agent     │  :8001
  │  Replenishment Agent  │  :8002
  └───────────────────────┘
```

### Key Design Principles

- **Event-driven, not query-driven** — agents watch for violations autonomously; humans don't manually ask "is stock low?"
- **Human-in-the-loop by default** — every AI proposal is paused at a HITL node via LangGraph `interrupt()` before execution
- **A2A task lifecycle** — sub-agents expose `/tasks` endpoints; the supervisor polls for completion rather than blocking
- **Hybrid search** — vector (HNSW cosine) + full-text (BM25/tsvector) merged via Reciprocal Rank Fusion

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Frontend | Next.js 14 + Tailwind CSS | Real-time ops dashboard, RSC + client components |
| Agent Orchestration | LangGraph (StateGraph) | Checkpointing, HITL interrupt, typed shared state |
| MCP Server | FastMCP (Python) | Tool protocol for inventory/search/recommendations |
| Vector Search | pgvector (HNSW index) | Incremental ANN, better than IVFFlat for live inserts |
| Full-text Search | PostgreSQL tsvector + GIN | BM25-style ranking, combined via RRF |
| Sub-agents | FastAPI (A2A protocol) | Async task lifecycle: pending → in_progress → completed |
| Embeddings | OpenAI text-embedding-3-small | 1536-dim, cost-effective for product catalog |
| Database | PostgreSQL 15 | Products, inventory, forecast metrics, tuning log |
| Containerisation | Docker Compose | 4 services: postgres, mcp_server, allocation, replenishment |
| Scheduling | APScheduler (Day 3) | Autonomous inventory + MAPE monitoring loop |

---

## System Components

### 1. FastMCP Server (`mcp_server/`)

Implements the Model Context Protocol with four tools:

- **`hybrid_search`** — embeds query → HNSW vector search → tsvector full-text search → RRF merge → top-N results with `match_type: hybrid/vector/fulltext`
- **`inventory_lookup`** — filtered inventory query with `status` derivation (CRITICAL/LOW/OK), sorted by buffer units ascending (most at risk first)
- **`entity_resolve`** — fuzzy product/supplier name resolution using cosine similarity; returns top-3 candidates with confidence scores
- **`submit_recommendation`** — admin-only tool that writes approved proposals back to the database

**RBAC middleware** enforces role boundaries via `x-role` header: `analyst` gets read-only tools, `admin` gets all tools including writes.

### 2. LangGraph Supervisor (`agents/`)

A `StateGraph` with five nodes:

```
supervisor → [sql_insights | forecasting | allocation_replenishment] → hitl
```

- **supervisor**: intent classification only (GPT-4o-mini, temp=0) — routes via conditional edge, does no actual work
- **sql_insights**: 3-step pipeline — parse intent → generate SQL via compact semantic schema (~200 tokens vs ~800 for raw DDL) → execute → format insight
- **forecasting**: scans `forecast_metrics`, filters MAPE > 15%, uses GPT-4o to reason about root cause and propose hyperparameter changes
- **allocation_replenishment**: triggers A2A tasks to sub-agents, polls for completion, surfaces result as proposal
- **hitl**: `interrupt()` fires here — graph pauses, state checkpointed to SQLite, resumes only when human sends `approved=True`

### 3. A2A Sub-Agents (`services/`)

Both agents expose the same task lifecycle protocol:

```
POST /tasks   →  { task_id, status: "pending" }
GET  /tasks/{id}  →  { status: "in_progress" | "completed" | "failed", result: {...} }
```

- **Allocation Agent** (`:8001`): finds deficit SKUs (stock < reorder_point), matches with surplus of the same product in a different region, proposes inter-warehouse transfers
- **Replenishment Agent** (`:8002`): finds all inventory below reorder_point, selects best supplier by lead time, generates purchase order drafts with expected delivery dates

### 4. Next.js Dashboard (`frontend/`)

Three-column real-time ops layout:

| Column | Component | Data |
|---|---|---|
| Left (3/12) | `InventoryAlertsFeed` | Live stock levels, capacity bars, deficit % |
| Centre (6/12) | `ProposalCard` queue | Approve/Reject, expandable PO/transfer detail |
| Right (3/12) | `ForecastPanel` | MAPE bars with 15% threshold marker |

Proposal cards show: severity stripe, agent reasoning, type-specific detail (PO table / transfer plan / hyperparameter diff), and LangGraph node trace path.

---

## Database Schema

Seven tables in PostgreSQL with pgvector extension:

```sql
products          -- 10 SKUs, vector(1536) embeddings + tsvector GIN index
suppliers         -- 5 suppliers with lead times and MOQs
inventory         -- 12 rows across 4 regions; 4 intentionally CRITICAL
supply_chain_records -- 30 historical transactions
forecast_metrics  -- 10 rows; 3 high MAPE (SKU-008: 27.89%, SKU-004: 23.41%)
hyperparameter_tuning_log -- audit log of forecasting agent proposals
allocation_tasks  -- A2A task state persistence
```

HNSW index (m=16, ef_construction=64) chosen over IVFFlat for incremental insert support.

---

## Seed Data Highlights

The seed data is designed to create realistic conditions for all three agent paths:

- **4 CRITICAL inventory alerts**: SKU-001 Southeast (72% deficit), SKU-004 West, SKU-006 Southeast, SKU-010 Northeast
- **3 high-MAPE products**: SKU-008 Vitamin C Serum (27.89%), SKU-004 Keratin Treatment (23.41%), SKU-005 (18.76%)
- **Cross-region surplus**: Northeast has surplus of SKU-001 → allocation agent proposes transfer to Southeast

---

## Progress Tracker

### Week 1 — Foundation & Dashboard

| Day | Status | What We Built |
|---|---|---|
| Day 1 | ✅ Done | Full project scaffold: Docker Compose, PostgreSQL schema + seeds, FastMCP server (4 tools + RBAC), LangGraph supervisor + HITL, A2A allocation + replenishment agents, Next.js ops dashboard |
| Day 2 | 🔜 Next | FastAPI Dashboard API — real endpoints replace mock data: `GET /proposals`, `GET /inventory/alerts`, `POST /proposals/{id}/approve` |
| Day 3 | ✅ Done | APScheduler monitoring loop — 60s inventory scan, 5min MAPE scan, auto-generate proposals on violation (`scheduler.py` & `daily_digest.py`) |
| Day 4 | ✅ Done | Chaos Simulator (`chaos_simulator.py`) and Proactive Drift Agent (`drift_agent.py`) implemented for continuous ops stress-testing |
| Day 5 | 📅 Planned | Wire LangGraph to approval — `POST approve` resumes the checkpointed graph, triggers A2A execution |
| Day 6 | 📅 Planned | LangSmith tracing — instrument all nodes, surface trace in dashboard pipeline view |

### Future Enhancements

- Real Wren Engine integration (measure actual token reduction vs simulated schema prompt)
- GitHub PR agent — auto-create PRs on approved supplier config changes
- Slack approval workflow — surface HITL proposals in Slack with Approve/Reject buttons
- Jira ticket creation on PO approval
- Grafana + Loki log monitoring
- Confluence auto-reports from forecasting agent

---

## Running Locally

### Prerequisites

- Docker + Docker Compose
- Node.js 18+
- Python 3.11+
- OpenAI API key

### 1. Start backend services

```bash
# Copy and fill in your env vars
cp .env.example .env

# Start postgres + all agents
docker compose up -d

# Generate embeddings for hybrid search (run once)
python data/seeds/generate_embeddings.py
```

### 2. Start the frontend

```bash
cd frontend
npm install
npm run dev
# → http://localhost:3000
```

### 3. Test the A2A agents directly

```bash
# Check allocation agent
curl http://localhost:8001/agent-card

# Trigger an allocation task
curl -X POST http://localhost:8001/tasks \
  -H "Content-Type: application/json" \
  -d '{"task_id": "test-001", "type": "allocation", "role": "admin"}'

# Poll result
curl http://localhost:8001/tasks/test-001
```

### 4. Test the MCP server

The MCP protocol requires an `initialize` handshake before tool calls — it's not a plain REST API. Use the MCP client SDK or Claude Desktop to connect.

---

## Project Structure

```
supply-chain-ai/
├── agents/                     # LangGraph multi-agent system
│   ├── supervisor.py           # StateGraph: supervisor → sub-nodes → hitl
│   ├── state.py                # SupplyChainState TypedDict (shared state)
│   ├── a2a_client.py           # A2A polling client
│   ├── sql_insights/           # SQL pipeline: parse → generate → execute → format
│   └── forecasting_analyst/    # MAPE scan + hyperparameter tuning proposals
├── mcp_server/                 # FastMCP tools + RBAC middleware
│   ├── server.py
│   ├── middleware/rbac.py
│   └── tools/
│       ├── hybrid_search.py    # HNSW + tsvector + RRF
│       ├── inventory.py
│       ├── entity_resolve.py
│       └── recommendations.py
├── services/
│   ├── allocation_agent/       # FastAPI A2A agent :8001
│   └── replenishment_agent/    # FastAPI A2A agent :8002
├── data/seeds/
│   ├── 01_schema.sql           # Tables, pgvector, HNSW index, GIN index
│   ├── 02_seed_data.sql        # 10 products, 4 CRITICAL inventory rows
│   └── generate_embeddings.py  # OpenAI batch embedding backfill
├── frontend/                   # Next.js 14 + Tailwind ops dashboard
│   └── src/
│       ├── app/page.tsx        # Main dashboard layout
│       ├── components/         # InventoryAlertsFeed, ProposalCard, ForecastPanel
│       ├── lib/mock-data.ts    # Day 1 mock data (replaced Day 2+)
│       └── types/index.ts      # TypeScript interfaces mirroring DB schema
└── docker-compose.yml          # postgres, mcp_server, allocation, replenishment
```

---

## Key Concepts Implemented

**Why `interrupt()` and not a simple approval checkbox?**
LangGraph's `interrupt()` pauses the entire graph and serializes state to a SQLite checkpoint. This means the agent's full reasoning context — which MCP tools it called, what data it saw, what it decided — is preserved exactly. When a human approves, the graph resumes from that exact checkpoint. No state is lost, no re-computation needed.

**Why A2A instead of direct function calls?**
Each sub-agent runs as an independent service. The supervisor doesn't need to know *how* allocation or replenishment works — it just fires a task and polls. This means sub-agents can be swapped, scaled, or versioned independently without touching the supervisor.

**Why hybrid search instead of pure vector search?**
Pure vector search misses exact keyword matches (e.g., "SKU-008" or a specific supplier name). Pure full-text misses semantic similarity (e.g., "moisturizer" matching "hydrating serum"). RRF combines both ranked lists into a single score, getting the best of both.

---

*Built by Kimchi · CVS Health AI Engineering*
