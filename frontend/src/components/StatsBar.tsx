"use client";

import { AlertTriangle, Clock, CheckCircle2, DollarSign, TrendingUp, Server } from "lucide-react";
import type { DashboardStats } from "@/types";

interface StatsBarProps {
  stats: DashboardStats;
}

export function StatsBar({ stats }: StatsBarProps) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
      {/* Critical alerts */}
      <div className="stat-card">
        <div className="flex items-center gap-1.5 text-red-400 text-xs font-medium">
          <AlertTriangle className="w-3.5 h-3.5" />
          Critical Alerts
        </div>
        <p className="text-2xl font-bold text-red-400">{stats.critical_alerts}</p>
        <p className="text-[11px] text-slate-500">stockout risk</p>
      </div>

      {/* Pending approvals */}
      <div className="stat-card">
        <div className="flex items-center gap-1.5 text-amber-400 text-xs font-medium">
          <Clock className="w-3.5 h-3.5" />
          Pending Approval
        </div>
        <p className="text-2xl font-bold text-amber-400">{stats.pending_approvals}</p>
        <p className="text-[11px] text-slate-500">awaiting review</p>
      </div>

      {/* Approved today */}
      <div className="stat-card">
        <div className="flex items-center gap-1.5 text-emerald-400 text-xs font-medium">
          <CheckCircle2 className="w-3.5 h-3.5" />
          Approved Today
        </div>
        <p className="text-2xl font-bold text-emerald-400">{stats.approved_today}</p>
        <p className="text-[11px] text-slate-500">actions executed</p>
      </div>

      {/* PO value pending */}
      <div className="stat-card">
        <div className="flex items-center gap-1.5 text-blue-400 text-xs font-medium">
          <DollarSign className="w-3.5 h-3.5" />
          PO Value Pending
        </div>
        <p className="text-2xl font-bold text-blue-400">
          ${(stats.total_po_value_pending / 1000).toFixed(1)}k
        </p>
        <p className="text-[11px] text-slate-500">awaiting approval</p>
      </div>

      {/* Avg MAPE */}
      <div className="stat-card">
        <div className="flex items-center gap-1.5 text-violet-400 text-xs font-medium">
          <TrendingUp className="w-3.5 h-3.5" />
          Avg MAPE
        </div>
        <p className="text-2xl font-bold text-violet-400">{stats.avg_mape}%</p>
        <p className="text-[11px] text-slate-500">forecast accuracy</p>
      </div>

      {/* Services */}
      <div className="stat-card">
        <div className="flex items-center gap-1.5 text-slate-400 text-xs font-medium">
          <Server className="w-3.5 h-3.5" />
          Services
        </div>
        <div className="flex flex-col gap-1 mt-1">
          {stats.services.map((svc) => (
            <div key={svc.name} className="flex items-center justify-between">
              <span className="text-[10px] text-slate-400 truncate">{svc.name}</span>
              <div className="flex items-center gap-1">
                <span className="text-[10px] text-slate-500">{svc.latency_ms}ms</span>
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    svc.status === "healthy" ? "bg-emerald-400" : "bg-red-400"
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
