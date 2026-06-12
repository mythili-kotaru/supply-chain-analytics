"use client";

import { AlertTriangle, Clock, CheckCircle2, DollarSign, TrendingUp, Server } from "lucide-react";

const AlertTriangleIcon = AlertTriangle as any;
const ClockIcon = Clock as any;
const CheckCircle2Icon = CheckCircle2 as any;
const DollarSignIcon = DollarSign as any;
const TrendingUpIcon = TrendingUp as any;
const ServerIcon = Server as any;

import type { DashboardStats } from "@/types";

interface StatsBarProps {
  stats: DashboardStats;
}

function formatPOValue(val: number): string {
  if (!val || isNaN(val)) return "$0";
  if (val >= 1_000_000) return `$${(val / 1_000_000).toFixed(1)}M`;
  if (val >= 1_000) return `$${(val / 1_000).toFixed(1)}k`;
  return `$${val.toFixed(0)}`;
}

const MAPE_COLOR = (mape: number) =>
  mape > 20 ? "text-red-400" : mape > 15 ? "text-orange-400" : "text-violet-400";

const MAPE_LABEL = (mape: number) =>
  mape > 20 ? "high error" : mape > 15 ? "above threshold" : "forecast accuracy";

export function StatsBar({ stats }: StatsBarProps) {
  const allHealthy = stats.services.every((s) => s.status === "healthy");

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">

      {/* Critical alerts */}
      <div className="stat-card border-l-2 border-l-red-500/60 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-red-500/5 to-transparent pointer-events-none" />
        <div className="flex items-center gap-1.5 text-red-400 text-xs font-medium">
          <AlertTriangleIcon className="w-3.5 h-3.5" />
          Critical Alerts
        </div>
        <p className={`text-2xl font-bold ${stats.critical_alerts > 0 ? "text-red-400" : "text-slate-400"}`}>
          {stats.critical_alerts}
        </p>
        <p className="text-[11px] text-slate-500">
          {stats.critical_alerts > 0 ? "immediate action needed" : "no active risks"}
        </p>
      </div>

      {/* Pending approvals */}
      <div className="stat-card border-l-2 border-l-amber-500/60 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-amber-500/5 to-transparent pointer-events-none" />
        <div className="flex items-center gap-1.5 text-amber-400 text-xs font-medium">
          <ClockIcon className="w-3.5 h-3.5" />
          Pending Approval
        </div>
        <div className="flex items-end gap-2">
          <p className="text-2xl font-bold text-amber-400">{stats.pending_approvals}</p>
          {stats.pending_approvals > 0 && (
            <span className="text-[10px] text-amber-500 mb-1 animate-pulse">needs review</span>
          )}
        </div>
        <p className="text-[11px] text-slate-500">awaiting review</p>
      </div>

      {/* Approved today */}
      <div className="stat-card border-l-2 border-l-emerald-500/60 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-emerald-500/5 to-transparent pointer-events-none" />
        <div className="flex items-center gap-1.5 text-emerald-400 text-xs font-medium">
          <CheckCircle2Icon className="w-3.5 h-3.5" />
          Approved Today
        </div>
        <p className="text-2xl font-bold text-emerald-400">{stats.approved_today}</p>
        <p className="text-[11px] text-slate-500">actions executed</p>
      </div>

      {/* PO value pending */}
      <div className="stat-card border-l-2 border-l-blue-500/60 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-blue-500/5 to-transparent pointer-events-none" />
        <div className="flex items-center gap-1.5 text-blue-400 text-xs font-medium">
          <DollarSignIcon className="w-3.5 h-3.5" />
          PO Value Pending
        </div>
        <p className="text-2xl font-bold text-blue-400 tabular-nums">
          {formatPOValue(stats.po_value_pending)}
        </p>
        <p className="text-[11px] text-slate-500">awaiting approval</p>
      </div>

      {/* Avg MAPE */}
      <div className="stat-card border-l-2 border-l-violet-500/60 relative overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-br from-violet-500/5 to-transparent pointer-events-none" />
        <div className="flex items-center gap-1.5 text-violet-400 text-xs font-medium">
          <TrendingUpIcon className="w-3.5 h-3.5" />
          Avg MAPE
        </div>
        <div className="flex items-end gap-2">
          <p className={`text-2xl font-bold tabular-nums ${MAPE_COLOR(stats.avg_mape)}`}>
            {stats.avg_mape}%
          </p>
          {/* threshold marker line */}
          <div className="mb-1.5 flex-1 h-4 relative">
            <div className="absolute bottom-0 left-0 right-0 h-1 bg-slate-800 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-700"
                style={{
                  width: `${Math.min(100, (stats.avg_mape / 30) * 100)}%`,
                  backgroundColor: stats.avg_mape > 20 ? "#f87171" : stats.avg_mape > 15 ? "#fb923c" : "#a78bfa",
                }}
              />
            </div>
            {/* 15% threshold marker */}
            <div className="absolute bottom-0 h-2 w-0.5 bg-slate-500" style={{ left: "50%" }} />
          </div>
        </div>
        <p className={`text-[11px] ${MAPE_COLOR(stats.avg_mape).replace("text-", "text-").replace("400", "500")}`}>
          {MAPE_LABEL(stats.avg_mape)}
        </p>
      </div>

      {/* Services */}
      <div className="stat-card border-l-2 border-l-slate-600 relative overflow-hidden">
        <div className="flex items-center gap-1.5 text-slate-400 text-xs font-medium">
          <ServerIcon className="w-3.5 h-3.5" />
          Services
          {allHealthy && (
            <span className="ml-auto text-[10px] text-emerald-500 font-normal">all healthy</span>
          )}
        </div>
        <div className="flex flex-col gap-1.5 mt-0.5">
          {stats.services.map((svc) => (
            <div key={svc.name} className="flex items-center justify-between gap-2">
              <span className="text-[10px] text-slate-400 truncate">{svc.name}</span>
              <div className="flex items-center gap-1.5 shrink-0">
                <span className={`text-[9px] font-medium ${
                  svc.status === "healthy" ? "text-emerald-500" : "text-red-500"
                }`}>
                  {svc.status}
                </span>
                <span
                  className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                    svc.status === "healthy" ? "bg-emerald-400 live-dot" : "bg-red-400"
                  }`}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

    </div>
  );
}
