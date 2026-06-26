-- Migration: Add sandbox_scenarios table for Day 14 Scenario Versioning & Comparison
-- Day 14: Scenario Versioning

CREATE TABLE IF NOT EXISTS sandbox_scenarios (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                    TEXT NOT NULL UNIQUE,
    demand_multiplier       NUMERIC(3, 2) NOT NULL,
    lead_time_multiplier    NUMERIC(3, 2) NOT NULL,
    disrupted_supplier_id   TEXT REFERENCES suppliers(supplier_id),
    disrupted_supplier_name TEXT,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    critical_stockouts      INTEGER NOT NULL,
    total_mitigation_cost   NUMERIC(12, 2) NOT NULL,
    avg_mitigation_risk     NUMERIC(5, 2) NOT NULL,
    total_mitigations_count INTEGER NOT NULL,
    charts_data             JSONB NOT NULL
);
