"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { DashboardStats } from "@/types";
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Zap,
  LayoutDashboard,
  LogOut,
  RefreshCw,
  ChevronRight,
} from "lucide-react";

interface UserProfilePanelProps {
  stats: DashboardStats;
  role: "analyst" | "admin";
  setRole: (role: "analyst" | "admin") => void;
  onClose: () => void;
}

function ServiceStatusDot({ status }: { status: string }) {
  if (status === "healthy")
    return <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />;
  if (status === "degraded")
    return <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />;
  return <XCircle className="w-3.5 h-3.5 text-red-400 shrink-0" />;
}

export function UserProfilePanel({ stats, role, setRole, onClose }: UserProfilePanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const [scanning, setScanning] = useState(false);
  const [scanResult, setScanResult] = useState<string | null>(null);

  const handleRoleChange = (newRole: "analyst" | "admin") => {
    if (typeof window !== "undefined") {
      localStorage.setItem("scai_user_role", newRole);
      setRole(newRole);
      onClose();
      window.location.reload();
    }
  };

  // Close on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose();
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [onClose]);

  async function handleMonitorRun() {
    setScanning(true);
    setScanResult(null);
    try {
      const res = await api.triggerMonitorRun();
      const errors = Object.values(res.results).filter((v) =>
        v.startsWith("error")
      );
      setScanResult(errors.length === 0 ? "✓ Scan complete — all monitors ran successfully." : `⚠ Scan finished with ${errors.length} error(s).`);
    } catch {
      setScanResult("✗ Failed to reach the backend.");
    } finally {
      setScanning(false);
    }
  }

  return (
    <div
      ref={panelRef}
      className="absolute top-full right-0 mt-2 w-80 bg-slate-900 border border-slate-700/60 rounded-2xl shadow-2xl shadow-black/60 z-[100] overflow-hidden animate-slide-up"
    >
      {/* User Card */}
      <div className="px-5 py-4 bg-gradient-to-br from-violet-500/10 to-purple-700/10 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-violet-500 to-purple-700 flex items-center justify-center text-sm font-bold text-white shadow-lg shadow-purple-900/40">
            MK
          </div>
          <div>
            <p className="text-sm font-semibold text-white leading-none">
              Mythili Kotaru
            </p>
            <span className={`mt-1.5 inline-block text-[10px] font-semibold px-2 py-0.5 rounded-full border ${
              role === "admin"
                ? "bg-violet-500/20 text-violet-300 border-violet-500/30"
                : "bg-blue-500/20 text-blue-300 border-blue-500/30"
            }`}>
              {role === "admin" ? "Ops Administrator" : "Supply Chain Analyst"}
            </span>
          </div>
        </div>

        {/* Active Role Selector */}
        <div className="mt-4 space-y-1.5">
          <p className="text-[9px] font-bold text-slate-500 uppercase tracking-widest">
            Select Active Role
          </p>
          <div className="grid grid-cols-2 gap-1 p-0.5 bg-slate-950/60 rounded-xl border border-slate-800/80">
            <button
              onClick={() => handleRoleChange("analyst")}
              className={`text-[10px] py-1 rounded-lg font-medium transition-all ${
                role === "analyst"
                  ? "bg-slate-800 text-white font-semibold shadow"
                  : "text-slate-500 hover:text-slate-300"
              }`}
            >
              Analyst
            </button>
            <button
              onClick={() => handleRoleChange("admin")}
              className={`text-[10px] py-1 rounded-lg font-medium transition-all ${
                role === "admin"
                  ? "bg-gradient-to-br from-violet-500 to-purple-600 text-white font-semibold shadow-lg shadow-violet-900/20"
                  : "text-slate-500 hover:text-slate-300"
              }`}
            >
              Admin
            </button>
          </div>
        </div>

        {/* Quick stats */}
        <div className="mt-3 grid grid-cols-2 gap-2">
          <div className="bg-slate-950/50 rounded-lg px-3 py-2 text-center">
            <p className="text-lg font-bold text-amber-400">
              {stats.pending_approvals}
            </p>
            <p className="text-[10px] text-slate-400">Pending Approvals</p>
          </div>
          <div className="bg-slate-950/50 rounded-lg px-3 py-2 text-center">
            <p className="text-lg font-bold text-red-400">
              {stats.critical_alerts}
            </p>
            <p className="text-[10px] text-slate-400">Critical Alerts</p>
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="px-3 py-2 border-b border-slate-800">
        <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest px-2 py-1.5">
          Quick Actions
        </p>
        <Link
          href="/"
          onClick={onClose}
          className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-slate-300 hover:text-white hover:bg-slate-800 transition-colors"
        >
          <LayoutDashboard className="w-4 h-4 text-slate-400" />
          View All Proposals
          <ChevronRight className="w-3.5 h-3.5 ml-auto text-slate-600" />
        </Link>
        <button
          onClick={handleMonitorRun}
          disabled={scanning}
          className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-slate-300 hover:text-white hover:bg-slate-800 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
        >
          <RefreshCw className={`w-4 h-4 text-slate-400 ${scanning ? "animate-spin" : ""}`} />
          {scanning ? "Running Monitors…" : "Trigger Monitor Scan"}
          {!scanning && <Zap className="w-3 h-3 ml-auto text-slate-600" />}
        </button>
        {scanResult && (
          <p className={`text-[11px] px-3 py-1.5 rounded-lg mx-0 mt-1 ${scanResult.startsWith("✓") ? "bg-emerald-500/10 text-emerald-400" : "bg-amber-500/10 text-amber-400"}`}>
            {scanResult}
          </p>
        )}
      </div>

      {/* System Health */}
      <div className="px-3 py-2 border-b border-slate-800">
        <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest px-2 py-1.5">
          System Health
        </p>
        <div className="space-y-1">
          {stats.services.map((svc) => (
            <div
              key={svc.name}
              className="flex items-center justify-between px-3 py-1.5"
            >
              <span className="text-xs text-slate-400">{svc.name}</span>
              <div className="flex items-center gap-1.5">
                <ServiceStatusDot status={svc.status} />
                <span
                  className={`text-[10px] font-medium capitalize ${
                    svc.status === "healthy"
                      ? "text-emerald-400"
                      : svc.status === "degraded"
                      ? "text-amber-400"
                      : "text-red-400"
                  }`}
                >
                  {svc.status}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Sign Out */}
      <div className="px-3 py-2">
        <button className="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm text-slate-400 hover:text-red-400 hover:bg-red-500/10 transition-colors">
          <LogOut className="w-4 h-4" />
          Sign Out
        </button>
      </div>
    </div>
  );
}
