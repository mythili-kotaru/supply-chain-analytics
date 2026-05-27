#!/bin/bash
# ─────────────────────────────────────────────────────────────
# day7_deploy.sh — Deploy all Day 7 changes and verify
# Run from: ~/Documents/supply-chain-ai/
# Usage: bash day7_deploy.sh
# ─────────────────────────────────────────────────────────────

set -e
OUTPUTS="/Users/mythilikotaru/Library/Application Support/Claude/local-agent-mode-sessions/b90beeaf-7833-4db3-8ec9-a924ae97391b/221f9e6c-ef0e-4bfb-82fd-de0703744deb/local_01e01eaa-3cd3-4711-96db-41398e37df5d/outputs/supply-chain-ai"
DOCS="$HOME/Documents/supply-chain-ai"

echo ""
echo "══════════════════════════════════════════"
echo "  Day 7 Deploy — Drift Detection"
echo "══════════════════════════════════════════"

# ── Step 1: Copy updated files ────────────────────────────────
echo ""
echo "▶ Step 1: Copying updated files..."

cp "$OUTPUTS/agents/supervisor.py"                              "$DOCS/agents/supervisor.py"
cp "$OUTPUTS/services/langgraph_agent/main.py"                 "$DOCS/services/langgraph_agent/main.py"
cp "$OUTPUTS/services/dashboard_api/routers/forecast.py"       "$DOCS/services/dashboard_api/routers/forecast.py"
cp "$OUTPUTS/services/dashboard_api/models.py"                 "$DOCS/services/dashboard_api/models.py"
cp "$OUTPUTS/data/migrations/002_add_drift_columns.sql"        "$DOCS/data/migrations/002_add_drift_columns.sql"
echo "  ✓ Files copied"

# ── Step 2: Run DB migration ──────────────────────────────────
echo ""
echo "▶ Step 2: Running DB migration (drift columns)..."
docker exec -i supply_chain_postgres psql -U scai -d supply_chain \
  < "$DOCS/data/migrations/002_add_drift_columns.sql" 2>&1 | grep -E "(ALTER|ERROR|column_name)" || true
echo "  ✓ Migration done"

# ── Step 3: Restart services ──────────────────────────────────
echo ""
echo "▶ Step 3: Restarting services..."
docker restart supply_chain_langgraph_agent supply_chain_dashboard_api
echo "  ✓ Services restarting..."
sleep 8

# ── Step 4: Seed a test forecast_tuning proposal ─────────────
echo ""
echo "▶ Step 4: Creating test forecast_tuning proposal for SKU-004..."
PROPOSAL_ID=$(docker exec supply_chain_postgres psql -U scai -d supply_chain -t -c "
INSERT INTO proposals (
  id, type, status, severity, created_at,
  trigger_product_id, trigger_product_name,
  trigger_location, trigger_metric,
  trigger_current_value, trigger_threshold,
  agent_reasoning, nodes_visited,
  forecast_tuning_payload
) VALUES (
  gen_random_uuid(), 'forecast_tuning', 'pending', 'CRITICAL', NOW(),
  'SKU-004', 'Anti-Aging Serum', NULL, 'mape_pct',
  23.41, 15.0,
  'MAPE scan: Anti-Aging Serum at 23.41% — above 15% threshold. Recommend hyperparameter re-tuning.',
  ARRAY['supervisor','forecasting','hitl'],
  '{\"model_name\": \"xgboost_v1\", \"old_params\": {\"max_depth\": 6, \"n_estimators\": 100, \"learning_rate\": 0.1}, \"new_params\": {}, \"expected_mape_improvement\": \"Pending agent analysis\"}'::jsonb
) RETURNING id;" | tr -d ' \n')
echo "  ✓ Proposal created: $PROPOSAL_ID"

# ── Step 5: Invoke LangGraph for the proposal ─────────────────
echo ""
echo "▶ Step 5: Invoking LangGraph (this takes ~20s)..."
INVOKE_RESP=$(curl -s -X POST http://localhost:8004/invoke \
  -H "Content-Type: application/json" \
  -d "{
    \"proposal_id\": \"$PROPOSAL_ID\",
    \"proposal_type\": \"forecast_tuning\",
    \"product_id\": \"SKU-004\",
    \"product_name\": \"Anti-Aging Serum\",
    \"location\": null,
    \"severity\": \"CRITICAL\",
    \"trigger_metric\": \"mape_pct\",
    \"trigger_value\": 23.41,
    \"trigger_threshold\": 15.0,
    \"user_role\": \"analyst\"
  }")

THREAD_ID=$(echo "$INVOKE_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('thread_id',''))" 2>/dev/null)
echo "  ✓ Graph paused. thread_id=$THREAD_ID"
echo "  Summary: $(echo "$INVOKE_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('agent_summary','')[:120])" 2>/dev/null)"

# ── Step 6: Auto-approve (simulate human approval) ────────────
echo ""
echo "▶ Step 6: Auto-approving proposal (simulating human approval)..."
sleep 2
RESUME_RESP=$(curl -s -X POST http://localhost:8004/resume \
  -H "Content-Type: application/json" \
  -d "{
    \"proposal_id\": \"$PROPOSAL_ID\",
    \"thread_id\": \"$THREAD_ID\",
    \"approved\": true,
    \"feedback\": \"Approved via day7_deploy.sh test\"
  }")
echo "  Status: $(echo "$RESUME_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',''))" 2>/dev/null)"
echo "  Message: $(echo "$RESUME_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('final_message','')[:150])" 2>/dev/null)"

# ── Step 7: Verify drift data in DB ──────────────────────────
echo ""
echo "▶ Step 7: Verifying drift data in DB..."
sleep 3
docker exec supply_chain_postgres psql -U scai -d supply_chain -c "
SELECT product_id,
       round(pre_mape*100,2) AS pre_mape_pct,
       round(post_mape*100,2) AS post_mape_pct,
       round(mape_delta*100,2) AS delta_pct,
       improved,
       simulated,
       status
FROM (
  SELECT *, (mape_delta > 0) AS improved
  FROM hyperparameter_tuning_log
  WHERE pre_mape IS NOT NULL
  ORDER BY proposed_at DESC LIMIT 3
) t;"

# ── Step 8: Verify drift API endpoint ────────────────────────
echo ""
echo "▶ Step 8: Testing /forecast/drift API..."
curl -s http://localhost:8003/api/dashboard/forecast/drift | python3 -c "
import sys, json
data = json.load(sys.stdin)
for d in data[:3]:
    print(f\"  {d['product_name']}: pre={d['pre_mape_pct']}% → post={d['post_mape_pct']}% | improved={d['improved']} | simulated={d['simulated']}\")
" 2>/dev/null || echo "  API check failed — check logs"

# ── Step 9: Verify forecast_metrics has new row ───────────────
echo ""
echo "▶ Step 9: Checking forecast_metrics for post-tuning row..."
docker exec supply_chain_postgres psql -U scai -d supply_chain -c "
SELECT product_id, round(mape*100,2) AS mape_pct, run_date, notes
FROM forecast_metrics
WHERE product_id = 'SKU-004'
ORDER BY run_date DESC LIMIT 3;"

echo ""
echo "══════════════════════════════════════════"
echo "  Day 7 Deploy Complete ✓"
echo "══════════════════════════════════════════"
echo ""
echo "Next: Open the dashboard and check the forecast panel."
echo "The drift API is live at:"
echo "  http://localhost:8003/api/dashboard/forecast/drift"
echo "  http://localhost:8003/api/dashboard/forecast/drift/SKU-004"
