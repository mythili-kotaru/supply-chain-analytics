"use client";

/**
 * DriftPanel — Day 8
 *
 * Shows the full drift detection history for all hyperparameter tuning rounds:
 *   - Summary table: each tuning run with pre/post MAPE, delta, improved flag
 *   - Per-product drill-down: click a row to see MAPE-over-time chart for that product
 *
 * Data sources:
 *   GET /api/dashboard/forecast/drift            → all tuning outcomes
 *   GET /api/dashboard/forecast/drift/{product}  → MAPE history for drill-down
 *
 * WHY a separate section (not inside ForecastPanel)?
 * ForecastPanel shows *current* MAPE violations — things needing attention now.
 * DriftPanel shows *historical* tuning outcomes — did our interventions work?
 * They answer different questions; separating keeps both panels scannable.
 */

import { useState, useEffect, useCallback } from "react";
import { Activity, ChevronDown, ChevronUp, CheckCircle, XCircle, Minus, RefreshCw, TrendingDown } from "lucide-react";
import { api } from "@/lib/api";
import type { DriftRecord, DriftHistory } from "@/types";

// ── Tiny inline sparkline chart (SVG, no deps) ───────────────────────────────
function MapeSparkline({ history }: { history: DriftHistory["history"] }) {
  if (history.length < 2) {
    return (
      <p className="text-[11px] text-slate-500 italic py-2">
        Only one data point — run another tuning round to see trend.
      </p>
    );
  }

  const W = 480;
  const H = 80;
  const PAD = { top: 8, right: 12, bottom: 24, left: 36 };
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;

  const mapes = history.map((h) => h.mape_pct);
  const minV = Math.max(0, Math.min(...mapes) - 2);
  const maxV = Math.max(...mapes) + 2;

  const xScale = (i: number) => PAD.left + (i / (history.length - 1)) * innerW;
  const yScale = (v: number) => PAD.top + ((maxV - v) / (maxV - minV)) * innerH;

  const points = history.map((h, i) => `${xScale(i)},${yScale(h.mape_pct)}`).join(" ");

  // threshold at 15%
  const threshY = yScale(15);
  const showThresh = threshY >= PAD.top && threshY <= PAD.top + innerH;

  return (
    <div className="mt-3 mb-1">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ height: 80 }}>
        {/* Grid lines */}
        {[minV, (minV + maxV) / 2, maxV].map((v) => (
          <line
            key={v}
            x1={PAD.left} y1={yScale(v)}
            x2={PAD.left + innerW} y2={yScale(v)}
            stroke="#1e293b" strokeWidth="1"
          />
        ))}

        {/* 15% threshold line */}
        {showThresh && (
          <>
            <line
              x1={PAD.left} y1={threshY}
              x2={PAD.left + innerW} y2={threshY}
              stroke="#475569" strokeWidth="1" strokeDasharray="4 3"
            />
            <text x={PAD.left + innerW + 3} y={threshY + 3}
              fontSize="8" fill="#64748b">15%</text>
          </>
        )}

        {/* Y-axis labels */}
        {[minV, maxV].map((v) => (
          <text key={v} x={PAD.left - 4} y={yScale(v) + 3}
            fontSize="8" fill="#475569" textAnchor="end">
            {v.toFixed(0)}%
          </text>
        ))}

        {/* Area fill */}
        <polyline
          points={[
            `${PAD.left},${PAD.top + innerH}`,
            ...history.map((h, i) => `${xScale(i)},${yScale(h.mape_pct)}`),
            `${PAD.left + innerW},${PAD.top + innerH}`,
          ].join(" ")}
          fill="rgba(139,92,246,0.08)"
          stroke="none"
        />

        {/* Line */}
        <polyline
          points={points}
          fill="none"
          stroke="#8b5cf6"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />

        {/* Dots */}
        {history.map((h, i) => {
          const color = h.mape_pct > 25 ? "#f87171" : h.mape_pct > 15 ? "#fb923c" : "#34d399";
          return (
            <circle key={i}
              cx={xScale(i)} cy={yScale(h.mape_pct)} r="3"
              fill={color} stroke="#0f172a" strokeWidth="1"
            />
          );
        })}

        {/* X-axis labels — show first, last, and every other in between */}
        {history.map((h, i) => {
          if (i !== 0 && i !== history.length - 1 && i % 2 !== 0) return null;
          const label = h.run_date.slice(5); // MM-DD
          return (
            <text key={i} x={xScale(i)} y={H - 4}
              fontSize="8" fill="#475569" textAnchor="middle">
              {label}
            </text>
          );
        })}
      </svg>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-1 text-[10px] text-slate-500">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-emerald-400 inline-block" /> ≤15% (OK)
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-orange-400 inline-block" /> 15–25% (HIGH)
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-red-400 inline-block" /> &gt;25% (CRITICAL)
        </span>
      </div>
    </div>
  );
}

// ── Param diff chip ───────────────────────────────────────────────────────────
function ParamDiff({ oldP, newP }: { oldP: Record<string, number>; newP: Record<string, number> }) {
  const keys = Array.from(new Set([...Object.keys(oldP), ...Object.keys(newP)]));
  if (keys.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-1">
      {keys.map((k) => {
        const changed = oldP[k] !== newP[k];
        return (
          <span key={k} className="text-[10px] font-mono text-slate-500">
            {k}:{" "}
            <span className={changed ? "line-through text-slate-600" : "text-slate-400"}>
              {oldP[k] ?? "—"}
            </span>
            {changed && (
              <>
                {" → "}
                <span className="text-violet-400">{newP[k] ?? "—"}</span>
              </>
            )}
          </span>
        );
      })}
    </div>
  );
}

// ── Expanded drill-down row ───────────────────────────────────────────────────
function DrillDown({ productId, record }: { productId: string; record: DriftRecord }) {
  const [history, setHistory] = useState<DriftHistory | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getDriftHistory(productId).then((h) => {
      setHistory(h);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [productId]);

  return (
    <div className="px-4 py-3 bg-slate-900/60 border-t border-slate-800">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Left: param diff + rationale */}
        <div>
          <p className="text-[11px] font-semibold text-slate-400 mb-1">Parameter Changes</p>
          <ParamDiff oldP={record.old_params} newP={record.new_params} />
          {record.rationale && (
            <p className="text-[11px] text-slate-500 italic mt-2 leading-relaxed">
              {record.rationale}
            </p>
          )}
          {record.simulated && (
            <span className="inline-block mt-2 text-[9px] font-semibold text-amber-400 bg-amber-400/10 border border-amber-400/20 rounded px-1.5 py-0.5">
              SIMULATED — post-MAPE was estimated, not measured
            </span>
          )}
        </div>

        {/* Right: MAPE history chart */}
        <div>
          <p className="text-[11px] font-semibold text-slate-400 mb-1">MAPE Over Time</p>
          {loading ? (
            <p className="text-[11px] text-slate-500">Loading history…</p>
          ) : history && history.history.length > 0 ? (
            <MapeSparkline history={history.history} />
          ) : (
            <p className="text-[11px] text-slate-500 italic">No history found.</p>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Main DriftPanel ───────────────────────────────────────────────────────────
export function DriftPanel() {
  const [records, setRecords] = useState<DriftRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.getDriftSummary();
      setRecords(data);
    } catch (e) {
      console.error("DriftPanel load error:", e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const improvedCount = records.filter((r) => r.improved === true).length;
  const worsenedCount = records.filter((r) => r.improved === false).length;
  const pendingCount  = records.filter((r) => r.improved === null).length;

  return (
    <div className="card">
      {/* ── Section header ── */}
      <div
        className="flex items-center justify-between px-4 py-3 border-b border-slate-800 cursor-pointer select-none"
        onClick={() => setCollapsed((c) => !c)}
      >
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-violet-400" />
          <h2 className="text-sm font-semibold text-white">Drift Detection</h2>
          <span className="text-[10px] text-slate-500">— Hyperparameter Tuning Outcomes</span>
        </div>

        <div className="flex items-center gap-3">
          {/* Summary chips */}
          {!loading && records.length > 0 && (
            <div className="flex items-center gap-2 text-[11px]">
              <span className="flex items-center gap-1 text-emerald-400">
                <CheckCircle className="w-3 h-3" /> {improvedCount} improved
              </span>
              {worsenedCount > 0 && (
                <span className="flex items-center gap-1 text-red-400">
                  <XCircle className="w-3 h-3" /> {worsenedCount} worsened
                </span>
              )}
              {pendingCount > 0 && (
                <span className="flex items-center gap-1 text-slate-500">
                  <Minus className="w-3 h-3" /> {pendingCount} pending
                </span>
              )}
            </div>
          )}

          {/* Refresh button */}
          <button
            onClick={(e) => { e.stopPropagation(); handleRefresh(); }}
            className="p-1.5 rounded-lg hover:bg-slate-800 border border-slate-800 transition-colors"
            title="Refresh drift data"
          >
            <RefreshCw className={`w-3.5 h-3.5 text-slate-400 ${refreshing ? "animate-spin" : ""}`} />
          </button>

          {collapsed
            ? <ChevronDown className="w-4 h-4 text-slate-500" />
            : <ChevronUp   className="w-4 h-4 text-slate-500" />
          }
        </div>
      </div>

      {/* ── Body ── */}
      {!collapsed && (
        loading ? (
          <div className="flex items-center gap-2 px-4 py-6 text-slate-500 text-sm">
            <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Loading drift data…
          </div>
        ) : records.length === 0 ? (
          <div className="flex items-center gap-2 px-4 py-6 text-slate-500 text-sm">
            <TrendingDown className="w-4 h-4" />
            No tuning rounds recorded yet. Approve a forecast_tuning proposal to see drift data here.
          </div>
        ) : (
          <div className="divide-y divide-slate-800/60">
            {/* Table header */}
            <div className="grid grid-cols-12 gap-2 px-4 py-2 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
              <div className="col-span-3">Product</div>
              <div className="col-span-2">Status</div>
              <div className="col-span-2 text-right">Pre-MAPE</div>
              <div className="col-span-2 text-right">Post-MAPE</div>
              <div className="col-span-2 text-right">Delta</div>
              <div className="col-span-1 text-center">Result</div>
            </div>

            {records.map((rec) => {
              const isExpanded = expandedId === rec.id;
              const deltaColor =
                rec.mape_delta_pct === null ? "text-slate-500"
                : rec.improved          ? "text-emerald-400"
                : "text-red-400";

              return (
                <div key={rec.id}>
                  {/* Summary row */}
                  <div
                    className="grid grid-cols-12 gap-2 px-4 py-2.5 hover:bg-slate-800/30 cursor-pointer transition-colors items-center"
                    onClick={() => setExpandedId(isExpanded ? null : rec.id)}
                  >
                    {/* Product */}
                    <div className="col-span-3">
                      <p className="text-sm font-semibold text-white truncate">{rec.product_name}</p>
                      <p className="text-[10px] text-slate-500 font-mono">{rec.product_id}</p>
                    </div>

                    {/* Status */}
                    <div className="col-span-2">
                      <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded capitalize
                        ${rec.status === "approved"  ? "bg-emerald-400/10 text-emerald-400" :
                          rec.status === "rejected"  ? "bg-red-400/10 text-red-400" :
                          rec.status === "pending"   ? "bg-amber-400/10 text-amber-400" :
                          "bg-slate-700/50 text-slate-400"}`}>
                        {rec.status}
                      </span>
                    </div>

                    {/* Pre-MAPE */}
                    <div className="col-span-2 text-right">
                      <span className={`text-sm font-mono tabular-nums ${
                        rec.pre_mape_pct === null ? "text-slate-500"
                        : rec.pre_mape_pct > 25 ? "text-red-400"
                        : rec.pre_mape_pct > 15 ? "text-orange-400"
                        : "text-emerald-400"
                      }`}>
                        {rec.pre_mape_pct !== null ? `${rec.pre_mape_pct}%` : "—"}
                      </span>
                    </div>

                    {/* Post-MAPE */}
                    <div className="col-span-2 text-right">
                      <span className={`text-sm font-mono tabular-nums ${
                        rec.post_mape_pct === null ? "text-slate-500"
                        : rec.post_mape_pct > 25 ? "text-red-400"
                        : rec.post_mape_pct > 15 ? "text-orange-400"
                        : "text-emerald-400"
                      }`}>
                        {rec.post_mape_pct !== null ? `${rec.post_mape_pct}%` : "—"}
                      </span>
                    </div>

                    {/* Delta */}
                    <div className="col-span-2 text-right">
                      <span className={`text-sm font-mono tabular-nums font-semibold ${deltaColor}`}>
                        {rec.mape_delta_pct !== null
                          ? `${rec.improved ? "−" : "+"}${Math.abs(rec.mape_delta_pct)}%`
                          : "—"}
                      </span>
                    </div>

                    {/* Improved icon */}
                    <div className="col-span-1 flex justify-center items-center gap-1">
                      {rec.improved === true  && <CheckCircle className="w-4 h-4 text-emerald-400" />}
                      {rec.improved === false && <XCircle     className="w-4 h-4 text-red-400"     />}
                      {rec.improved === null  && <Minus       className="w-4 h-4 text-slate-500"   />}
                      {isExpanded
                        ? <ChevronUp   className="w-3 h-3 text-slate-600" />
                        : <ChevronDown className="w-3 h-3 text-slate-600" />}
                    </div>
                  </div>

                  {/* Drill-down */}
                  {isExpanded && (
                    <DrillDown productId={rec.product_id} record={rec} />
                  )}
                </div>
              );
            })}
          </div>
        )
      )}
    </div>
  );
}
