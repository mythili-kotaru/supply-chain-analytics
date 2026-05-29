#!/bin/bash
# ─────────────────────────────────────────────────────────────
# day9_deploy.sh — Deploy Day 9: Anomaly Detection
# Run from: ~/Documents/supply-chain-ai/
# Usage: bash day9_deploy.sh
# ─────────────────────────────────────────────────────────────

set -e
OUTPUTS="/Users/mythilikotaru/Library/Application Support/Claude/local-agent-mode-sessions/b90beeaf-7833-4db3-8ec9-a924ae97391b/221f9e6c-ef0e-4bfb-82fd-de0703744deb/local_01e01eaa-3cd3-4711-96db-41398e37df5d/outputs/supply-chain-ai"
DOCS="$HOME/Documents/supply-chain-ai"

echo ""
echo "══════════════════════════════════════════"
echo "  Day 9 Deploy — Anomaly Detection"
echo "══════════════════════════════════════════"

# ── Step 1: Copy backend files ────────────────────────────────
echo ""
echo "▶ Step 1: Copying backend files..."
cp "$OUTPUTS/agents/anomaly_detector.py"                              "$DOCS/agents/anomaly_detector.py"
cp "$OUTPUTS/services/dashboard_api/routers/anomaly.py"               "$DOCS/services/dashboard_api/routers/anomaly.py"
cp "$OUTPUTS/services/dashboard_api/main.py"                          "$DOCS/services/dashboard_api/main.py"
cp "$OUTPUTS/services/dashboard_api/monitor.py"                       "$DOCS/services/dashboard_api/monitor.py"
cp "$OUTPUTS/data/migrations/003_add_anomaly_table.sql"               "$DOCS/data/migrations/003_add_anomaly_table.sql"
echo "  ✓ Backend files copied"

# ── Step 2: Copy frontend files ───────────────────────────────
echo ""
echo "▶ Step 2: Copying frontend files..."
cp "$OUTPUTS/frontend/src/components/AnomalyFeed.tsx"                 "$DOCS/frontend/src/components/AnomalyFeed.tsx"
cp "$OUTPUTS/frontend/src/types/index.ts"                             "$DOCS/frontend/src/types/index.ts"
cp "$OUTPUTS/frontend/src/lib/api.ts"                                 "$DOCS/frontend/src/lib/api.ts"
cp "$OUTPUTS/frontend/src/app/page.tsx"                               "$DOCS/frontend/src/app/page.tsx"

mkdir -p "$DOCS/frontend/src/app/api/dashboard/anomaly/events/[id]/ack"
mkdir -p "$DOCS/frontend/src/app/api/dashboard/anomaly/scan"

cp "$OUTPUTS/frontend/src/app/api/dashboard/anomaly/events/route.ts"             "$DOCS/frontend/src/app/api/dashboard/anomaly/events/route.ts"
cp "$OUTPUTS/frontend/src/app/api/dashboard/anomaly/events/[id]/ack/route.ts"    "$DOCS/frontend/src/app/api/dashboard/anomaly/events/[id]/ack/route.ts"
cp "$OUTPUTS/frontend/src/app/api/dashboard/anomaly/scan/route.ts"               "$DOCS/frontend/src/app/api/dashboard/anomaly/scan/route.ts"
echo "  ✓ Frontend files copied"

# ── Step 3: Run DB migration ──────────────────────────────────
echo ""
echo "▶ Step 3: Running DB migration (anomaly_events table)..."
docker exec -i supply_chain_postgres psql -U scai -d supply_chain \
  < "$DOCS/data/migrations/003_add_anomaly_table.sql" 2>&1 | grep -E "(CREATE|ERROR|column_name)" || true
echo "  ✓ Migration done"

# ── Step 4: Restart dashboard_api ────────────────────────────
echo ""
echo "▶ Step 4: Restarting dashboard_api..."
docker restart supply_chain_dashboard_api
echo "  ✓ Restarting..."
sleep 8

# ── Step 5: Trigger a manual anomaly scan ────────────────────
echo ""
echo "▶ Step 5: Triggering manual anomaly scan..."
SCAN_RESULT=$(curl -s -X POST http://localhost:8003/api/dashboard/anomaly/scan)
echo "  $SCAN_RESULT"

# ── Step 6: Verify anomaly_events table ──────────────────────
echo ""
echo "▶ Step 6: Checking anomaly_events..."
docker exec supply_chain_postgres psql -U scai -d supply_chain -c "
SELECT anomaly_type, severity, product_id, location,
       round(metric_value::numeric, 1) AS value,
       round(baseline_value::numeric, 1) AS baseline,
       round(deviation_pct::numeric, 1) AS deviation_pct,
       acknowledged
FROM anomaly_events
ORDER BY detected_at DESC
LIMIT 10;"

# ── Step 7: Check API ─────────────────────────────────────────
echo ""
echo "▶ Step 7: Testing /anomaly/events API..."
curl -s http://localhost:8003/api/dashboard/anomaly/events | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f'  Total events returned: {len(data)}')
for d in data[:3]:
    print(f\"  [{d['severity']}] {d['anomaly_type']} — {d['product_name']} @ {d.get('location','N/A')}: {d['description'][:80]}...\")
" 2>/dev/null || echo "  API check failed — check logs"

echo ""
echo "══════════════════════════════════════════"
echo "  Day 9 Deploy Complete ✓"
echo "══════════════════════════════════════════"
echo ""
echo "Next: Open the dashboard — Anomaly Detection feed should appear above Drift Detection."
echo "APIs:"
echo "  http://localhost:8003/api/dashboard/anomaly/events"
echo "  http://localhost:8003/api/dashboard/anomaly/stats"
echo "  POST http://localhost:8003/api/dashboard/anomaly/scan  (manual trigger)"
