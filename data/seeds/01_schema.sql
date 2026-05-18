-- 01_schema.sql
-- This runs automatically when Postgres first starts (via docker-entrypoint-initdb.d)
-- Files in that directory run in alphabetical order — hence the 01_ prefix.

-- ─────────────────────────────────────────────
-- ENABLE PGVECTOR
--
-- pgvector is a Postgres EXTENSION — it adds a new column type called `vector`
-- and new operators like <-> (L2 distance), <#> (inner product), <=> (cosine).
-- You must enable it once per database.
-- ─────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS vector;

-- ─────────────────────────────────────────────
-- PRODUCTS TABLE
--
-- Core entity: every supply chain record ties back to a product.
-- WHY TEXT for product_id and not SERIAL?
-- Real supply chain data uses SKU codes (strings), not auto-incremented ints.
-- Keeping it TEXT means we can load Kaggle data without ID remapping.
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS products (
    product_id      TEXT PRIMARY KEY,
    product_name    TEXT NOT NULL,
    category        TEXT NOT NULL,           -- e.g. 'skincare', 'haircare', 'cosmetics'
    price           NUMERIC(10, 2),
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────
-- SUPPLIERS TABLE
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id     TEXT PRIMARY KEY,
    supplier_name   TEXT NOT NULL,
    location        TEXT,
    lead_time_days  INTEGER,                -- how many days from order to delivery
    defect_rate     NUMERIC(5, 4)           -- e.g. 0.0234 = 2.34% defect rate
);

-- ─────────────────────────────────────────────
-- INVENTORY TABLE
--
-- Current stock levels per product per location.
-- This is what the MCP inventory_lookup tool queries.
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS inventory (
    id              SERIAL PRIMARY KEY,
    product_id      TEXT REFERENCES products(product_id),
    location        TEXT NOT NULL,           -- warehouse or region
    stock_level     INTEGER NOT NULL,
    reorder_point   INTEGER NOT NULL,        -- trigger replenishment when stock < this
    max_capacity    INTEGER NOT NULL,
    last_updated    TIMESTAMPTZ DEFAULT NOW()
);

-- ─────────────────────────────────────────────
-- SUPPLY_CHAIN_RECORDS TABLE
--
-- This is the main analytics table — loaded from the Kaggle dataset.
-- It captures each order/shipment record.
--
-- WHY denormalized (product_name repeated)?
-- Kaggle data often comes this way. We keep it as-is and normalize via
-- the products table separately. In practice, real-time transactional
-- data would be normalized; analytics tables are often denormalized for
-- query performance (avoiding JOINs on hot paths).
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS supply_chain_records (
    record_id           SERIAL PRIMARY KEY,
    product_id          TEXT REFERENCES products(product_id),
    supplier_id         TEXT REFERENCES suppliers(supplier_id),
    order_quantity      INTEGER,
    order_date          DATE,
    ship_date           DATE,
    delivery_date       DATE,
    shipping_costs      NUMERIC(10, 2),
    manufacturing_costs NUMERIC(10, 2),
    revenue             NUMERIC(10, 2),
    region              TEXT,               -- e.g. 'Northeast', 'Southeast', 'West'
    customer_segment    TEXT,               -- e.g. 'retail', 'wholesale'

    -- ─────────────────────────────────────────────
    -- EMBEDDING COLUMN
    --
    -- WHY store embeddings in Postgres and not a separate vector DB?
    -- This column holds a 1536-dimensional vector (OpenAI text-embedding-3-small output).
    -- We embed a text description of each record:
    --   "Product: Haircare Serum | Region: Southeast | Category: haircare | Revenue: $240"
    --
    -- This lets us do SEMANTIC search: "find products similar to sunscreen in hot climates"
    -- even if those exact words don't appear in the data.
    --
    -- vector(1536) = OpenAI text-embedding-3-small dimension.
    -- If you switch to text-embedding-3-large, change to vector(3072).
    -- ─────────────────────────────────────────────
    embedding           vector(1536),

    -- ─────────────────────────────────────────────
    -- TSVECTOR COLUMN
    --
    -- WHY tsvector alongside the embedding?
    -- Embeddings handle semantic similarity but are bad at exact keyword matches.
    -- If a user searches "SKU-XJ-4421", embeddings might miss it.
    -- tsvector is Postgres's built-in full-text search (BM25-like ranking).
    --
    -- The MCP hybrid_search tool combines BOTH:
    --   1. Vector similarity: embedding <-> query_embedding (semantic)
    --   2. Full-text match: search_vector @@ to_tsquery('english', 'query')
    -- Then RRF (Reciprocal Rank Fusion) merges the two ranked lists.
    -- ─────────────────────────────────────────────
    search_vector       tsvector
);

-- ─────────────────────────────────────────────
-- FORECAST METRICS TABLE
--
-- Stores MAPE (Mean Absolute Percentage Error) per product per model run.
-- The Forecasting Analyst agent reads this to identify underperforming forecasts.
--
-- WHY MAPE? It's the standard metric for demand forecasting accuracy.
-- MAPE = |actual - predicted| / actual * 100
-- Lower is better. Industry target is typically <15% for fast-moving goods.
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS forecast_metrics (
    id              SERIAL PRIMARY KEY,
    product_id      TEXT REFERENCES products(product_id),
    run_date        DATE NOT NULL,
    model_name      TEXT NOT NULL,           -- e.g. 'xgboost_v1', 'lstm_v2'
    mape            NUMERIC(6, 4),           -- e.g. 0.1823 = 18.23% error
    mae             NUMERIC(10, 2),          -- Mean Absolute Error (units)
    hyperparameters JSONB,                   -- e.g. {"n_estimators": 100, "max_depth": 6}
    notes           TEXT
);

-- ─────────────────────────────────────────────
-- HYPERPARAMETER TUNING LOG
--
-- The Forecasting Analyst agent writes here when it proposes a change.
-- This gives us an audit trail of what the agent decided and why.
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS hyperparameter_tuning_log (
    id              SERIAL PRIMARY KEY,
    product_id      TEXT REFERENCES products(product_id),
    agent_run_id    TEXT,                    -- ties back to LangGraph run_id
    proposed_at     TIMESTAMPTZ DEFAULT NOW(),
    old_params      JSONB,
    new_params      JSONB,
    rationale       TEXT,                    -- agent's explanation
    status          TEXT DEFAULT 'proposed'  -- 'proposed', 'approved', 'rejected'
);

-- ─────────────────────────────────────────────
-- ALLOCATION TASKS TABLE
--
-- When the Supervisor delegates to the Allocation Agent via A2A,
-- it creates a record here. The agent updates it when done.
-- This is the A2A "task lifecycle" — pending → in_progress → completed/failed.
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS allocation_tasks (
    task_id         TEXT PRIMARY KEY,        -- UUID generated by Supervisor
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    product_id      TEXT,
    region          TEXT,
    status          TEXT DEFAULT 'pending',  -- 'pending','in_progress','completed','failed'
    input_payload   JSONB,
    result_payload  JSONB,
    error           TEXT
);

-- ─────────────────────────────────────────────
-- INDEXES
--
-- WHY create indexes separately from the table?
-- Indexes slow down writes but massively speed up reads.
-- We add them after defining the schema so we're explicit about the trade-off.
-- ─────────────────────────────────────────────

-- Standard B-tree indexes for frequent filter columns
CREATE INDEX IF NOT EXISTS idx_scr_product_id ON supply_chain_records(product_id);
CREATE INDEX IF NOT EXISTS idx_scr_region ON supply_chain_records(region);
CREATE INDEX IF NOT EXISTS idx_scr_order_date ON supply_chain_records(order_date);
CREATE INDEX IF NOT EXISTS idx_inventory_product ON inventory(product_id);
CREATE INDEX IF NOT EXISTS idx_forecast_product ON forecast_metrics(product_id);

-- ─────────────────────────────────────────────
-- HNSW INDEX ON EMBEDDING
--
-- WHY HNSW and not IVFFlat?
-- HNSW (Hierarchical Navigable Small World) is a graph-based ANN index.
-- It gives better recall at similar query speeds compared to IVFFlat.
-- IVFFlat requires you to know your dataset size upfront (nlist parameter).
-- HNSW builds incrementally and works well at our dataset size (<1M rows).
--
-- m=16: number of connections per node (higher = better recall, more memory)
-- ef_construction=64: search width during index build (higher = better index quality)
--
-- At query time, set: SET hnsw.ef_search = 100;  (balance speed vs recall)
-- ─────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_scr_embedding_hnsw
    ON supply_chain_records
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ─────────────────────────────────────────────
-- GIN INDEX ON TSVECTOR
--
-- GIN (Generalized Inverted Index) is the right index type for tsvector.
-- It maps each lexeme (stemmed word) to the rows containing it.
-- This makes @@ (full-text match) queries very fast.
-- ─────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_scr_search_vector
    ON supply_chain_records
    USING gin(search_vector);
