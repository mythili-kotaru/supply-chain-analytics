"use client";

/**
 * AnomalyFeed — Day 9
 *
 * Live feed of anomaly detections from the background scanner.
 * The scanner runs every 5 minutes and writes to anomaly_events.
 * This component polls every 30s and shows the last 24h of detections.
 *
 * Features:
 *   - Three anomaly types with distinct icons: stock_drop, demand_spike, mape_regression
 *   - Severity colour coding: CRITICAL (red), HIGH (orange)
 *   - Acknowledge button to dismiss alerts one by one
 *   - "Scan now" button to trigger an immediate scan for testing
 *   - Filter by type and unacknowledged-only
 *   - Proposal link badge if the anomaly auto-created a HITL proposal
 */

import { useState, useEffect, useCallback } from "react";
import {
  Zap, TrendingDown, BarChart2, CheckCircle,
  RefreshCw, ChevronDown, ChevronUp, Scan
} from "lucide-react";
import { api } from "@/lib/api";
import type { AnomalyEvent, AnomalyType } from "@/types";

// ── Icons per anomaly type ────────────────────────────────────────────────────
function AnomalyIcon({ type, className }: { type: AnomalyType; className?: string }) {
  switch (type) {
    case "stock_drop":     return <TrendingDown className={className} />;
    case "demand_spike":   return <Zap           className={className} />;
    case "mape_regression":return <BarChart2     className={className} />;
  }
}

function anomalyLabel(type: AnomalyType): string {
  switch (type) {
    case "stock_drop":      return "Stock Drop";
    case "demand_spike":    return "Demand Spike";
    case "mape_regression": return "MAPE Regression";
  }
}

function severityStyle(severity: string) {
  if (severity === "CRITICAL") return { text: "text-red-400",    badge: "bg-red-400/10 border border-red-400/20 text-red-400" };
  if (severity === "HIGH")     return { text: "text-orange-400", badge: "bg-orange-400/10 border border-orange-400/20 text-orange-400" };
  return                              { text: "text-slate-400",  badge: "bg-slate-700/50 border border-slate-700 text-slate-400" };
}

function relativeTime(isoStr: string): string {
  const diff = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1)  return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24)  return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

// ── Score bar ─────────────────────────────────────────────────────────────────
function ScoreBar({ score, severity }: { score: number; severity: string }) {
  const pct   = Math.min(100, score * 100);
  const color = severity === "CRITICAL" ? "#f87171" : "#fb923c";
  return (
    <div className="h-1 bg-slate-800 rounded-full mt-1.5">
      <div className="h-full rounded-full transition-all duration-500"
           style={{ width: `${pct}%`, backgroundColor: color }} />
    </div>
  );
}

// ── Single anomaly card ───────────────────────────────────────────────────────
function AnomalyCard({
  event,
  onAck,
}: {
  event: AnomalyEvent;
  onAck: (id: number) => void;
}) {
  const [acking, setAcking] = useState(false);
  const sty = severityStyle(event.severity);

  const handleAck = async () => {
    setAcking(true);
    try {
      await api.acknowledgeAnomaly(event.id);
      onAck(event.id);
    } finally {
      setAcking(false);
    }
  };

  return (
    <div className={`px-4 py-3 transition-colors hover:bg-slate-800/20 ${
      event.acknowledged ? "opacity-40" : ""
    }`}>
      <div className="flex items-start gap-3">
        {/* Type icon */}
        <div className={`mt-0.5 shrink-0 ${sty.text}`}>
          <AnomalyIcon type={event.anomaly_type} className="w-4 h-4" />
        </div>

        {/* Body */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${sty.badge}`}>
              {event.severity}
            </span>
            <span className="text-[10px] text-slate-500">
              {anomalyLabel(event.anomaly_type)}
            </span>
            {event.proposal_id && (
              <span className="text-[10px] font-semibold text-violet-400 bg-violet-400/10 border border-violet-400/20 rounded px-1.5 py-0.5">
                → Proposal created
              </span>
            )}
            <span className="text-[10px] text-slate-600 ml-auto shrink-0">
              {relativeTime(event.detected_at)}
            </span>
          </div>

          <p className="text-sm font-semibold text-white mt-0.5 truncate">
            {event.product_name}
            {event.location && (
              <span className="text-slate-500 font-normal"> · {event.location}</span>
            )}
          </p>

          <p className="text-[11px] text-slate-400 mt-0.5 leading-relaxed">
            {event.description}
          </p>

          {/* Score bar + metric */}
          <div className="flex items-center gap-4 mt-1.5">
            <div className="flex-1">
              <ScoreBar score={event.anomaly_score} severity={event.severity} />
            </div>
            <span className="text-[10px] text-slate-500 shrink-0 tabular-nums">
              {event.metric_name}: <span className={sty.text}>{event.metric_value.toFixed(1)}</span>
              {" "}vs {event.baseline_value.toFixed(1)} baseline
            </span>
          </div>
        </div>

        {/* Ack button */}
        {!event.acknowledged && (
          <button
            onClick={handleAck}
            disabled={acking}
            className="shrink-0 mt-0.5 p-1 rounded hover:bg-slate-700 transition-colors text-slate-500 hover:text-emerald-400"
            title="Acknowledge"
          >
            {acking
              ? <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              : <CheckCircle className="w-3.5 h-3.5" />
            }
          </button>
        )}
      </div>
    </div>
  );
}

// ── Main AnomalyFeed ──────────────────────────────────────────────────────────
export function AnomalyFeed() {
  const [events, setEvents]       = useState<AnomalyEvent[]>([]);
  const [loading, setLoading]     = useState(true);
  const [scanning, setScanning]   = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [unackedOnly, setUnackedOnly] = useState(false);
  const [typeFilter, setTypeFilter] = useState<AnomalyType | "all">("all");
  const [lastScan, setLastScan]   = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await api.getAnomalyEvents(unackedOnly);
      setEvents(data);
    } catch (e) {
      console.error("AnomalyFeed load error:", e);
    } finally {
      setLoading(false);
    }
  }, [unackedOnly]);

  useEffect(() => { load(); }, [load]);

  // Auto-refresh every 30s (same as the rest of the dashboard)
  useEffect(() => {
    const interval = setInterval(load, 30_000);
    return () => clearInterval(interval);
  }, [load]);

  const handleRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const handleScan = async () => {
    setScanning(true);
    try {
      const result = await api.triggerAnomalyScan();
      setLastScan(`Scan found ${result.summary.total_new ?? 0} new anomalies`);
      await load();
    } catch (e) {
      setLastScan("Scan failed — check logs");
    } finally {
      setScanning(false);
    }
  };

  const handleAck = (id: number) => {
    setEvents((prev) =>
      prev.map((e) => e.id === id ? { ...e, acknowledged: true } : e)
    );
  };

  // Apply type filter
  const filtered = events.filter((e) =>
    typeFilter === "all" ? true : e.anomaly_type === typeFilter
  );

  const unackedCount   = events.filter((e) => !e.acknowledged).length;
  const criticalCount  = events.filter((e) => !e.acknowledged && e.severity === "CRITICAL").length;

  return (
    <div className="card">
      {/* ── Header ── */}
      <div
        className="flex items-center justify-between px-4 py-3 border-b border-slate-800 cursor-pointer select-none"
        onClick={() => setCollapsed((c) => !c)}
      >
        <div className="flex items-center gap-2">
          <Zap className="w-4 h-4 text-amber-400" />
          <h2 className="text-sm font-semibold text-white">Anomaly Detection</h2>
          <span className="text-[10px] text-slate-500">— Live Scanner · Last 24h</span>
        </div>

        <div className="flex items-center gap-3">
          {/* Summary badges */}
          {!loading && (
            <div className="flex items-center gap-2 text-[11px]">
              {criticalCount > 0 && (
                <span className="flex items-center gap-1 text-red-400 font-semibold">
                  {criticalCount} CRITICAL
                </span>
              )}
              {unackedCount > 0 && (
                <span className="text-slate-400">{unackedCount} unacknowledged</span>
              )}
              {unackedCount === 0 && !loading && (
                <span className="text-emerald-400">All clear</span>
              )}
            </div>
          )}

          {/* Scan now */}
          <button
            onClick={(e) => { e.stopPropagation(); handleScan(); }}
            disabled={scanning}
            className="flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-semibold
                       bg-amber-400/10 border border-amber-400/20 text-amber-400
                       hover:bg-amber-400/20 transition-colors disabled:opacity-50"
            title="Trigger immediate anomaly scan"
          >
            {scanning
              ? <RefreshCw className="w-3 h-3 animate-spin" />
              : <Scan className="w-3 h-3" />
            }
            Scan now
          </button>

          {/* Refresh */}
          <button
            onClick={(e) => { e.stopPropagation(); handleRefresh(); }}
            className="p-1.5 rounded-lg hover:bg-slate-800 border border-slate-800 transition-colors"
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
        <>
          {/* Filter bar */}
          <div className="flex items-center gap-3 px-4 py-2 border-b border-slate-800/60 flex-wrap">
            {/* Type filter */}
            <div className="flex items-center bg-slate-900 border border-slate-800 rounded-lg p-0.5 text-[10px]">
              {(["all", "stock_drop", "demand_spike", "mape_regression"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setTypeFilter(t)}
                  className={`px-2 py-1 rounded-md capitalize transition-colors ${
                    typeFilter === t
                      ? "bg-slate-700 text-white font-medium"
                      : "text-slate-500 hover:text-slate-300"
                  }`}
                >
                  {t === "all" ? "All" : anomalyLabel(t as AnomalyType)}
                </button>
              ))}
            </div>

            {/* Unacked toggle */}
            <label className="flex items-center gap-1.5 text-[10px] text-slate-400 cursor-pointer">
              <input
                type="checkbox"
                checked={unackedOnly}
                onChange={(e) => setUnackedOnly(e.target.checked)}
                className="w-3 h-3 rounded accent-amber-400"
              />
              Unacknowledged only
            </label>

            {lastScan && (
              <span className="text-[10px] text-slate-500 ml-auto">{lastScan}</span>
            )}
          </div>

          {/* Event list */}
          {loading ? (
            <div className="flex items-center gap-2 px-4 py-6 text-slate-500 text-sm">
              <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Loading anomaly feed…
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex items-center gap-2 px-4 py-6 text-slate-500 text-sm">
              <CheckCircle className="w-4 h-4 text-emerald-400" />
              {unackedOnly
                ? "No unacknowledged anomalies. Run a scan to check for new ones."
                : "No anomalies detected in the last 24 hours. Run a scan to check now."}
            </div>
          ) : (
            <div className="divide-y divide-slate-800/60 max-h-[400px] overflow-y-auto">
              {filtered.map((event) => (
                <AnomalyCard key={event.id} event={event} onAck={handleAck} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
