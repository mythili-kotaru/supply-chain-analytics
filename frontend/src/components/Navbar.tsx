"use client";

import { Activity, Bell, Settings, ChevronDown, Zap } from "lucide-react";
import type { DashboardStats } from "@/types";

interface NavbarProps {
  stats: DashboardStats;
}

export function Navbar({ stats }: NavbarProps) {
  const allHealthy = stats.services.every((s) => s.status === "healthy");

  return (
    <header className="h-14 border-b border-slate-800 bg-slate-950/80 backdrop-blur-sm flex items-center px-6 gap-6 sticky top-0 z-50">
      {/* Logo / Brand */}
      <div className="flex items-center gap-2.5 mr-4">
        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-blue-500 to-blue-700 flex items-center justify-center">
          <Zap className="w-4 h-4 text-white" />
        </div>
        <div>
          <span className="text-sm font-bold text-white tracking-tight">SupplyChain</span>
          <span className="text-sm font-bold text-blue-400 tracking-tight"> AI</span>
        </div>
        <span className="text-xs text-slate-500 border border-slate-700 rounded px-1.5 py-0.5 ml-1">
          CVS Health
        </span>
      </div>

      {/* Nav links */}
      <nav className="hidden md:flex items-center gap-1 text-sm">
        {["Dashboard", "Inventory", "Forecasting", "Orders", "Analytics"].map((item, i) => (
          <button
            key={item}
            className={`px-3 py-1.5 rounded-lg transition-colors ${
              i === 0
                ? "bg-slate-800 text-white font-medium"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
            }`}
          >
            {item}
          </button>
        ))}
      </nav>

      {/* Spacer */}
      <div className="flex-1" />

      {/* System health pill */}
      <div
        className={`hidden sm:flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full border ${
          allHealthy
            ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
            : "bg-red-500/10 border-red-500/30 text-red-400"
        }`}
      >
        <span className={`w-1.5 h-1.5 rounded-full live-dot ${allHealthy ? "bg-emerald-400" : "bg-red-400"}`} />
        <Activity className="w-3 h-3" />
        <span className="font-medium">{allHealthy ? "All systems operational" : "Degraded"}</span>
      </div>

      {/* Pending approvals badge */}
      <button className="relative p-2 rounded-lg hover:bg-slate-800 transition-colors">
        <Bell className="w-4 h-4 text-slate-400" />
        {stats.pending_approvals > 0 && (
          <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-red-500 rounded-full text-[10px] font-bold text-white flex items-center justify-center">
            {stats.pending_approvals}
          </span>
        )}
      </button>

      {/* User */}
      <button className="flex items-center gap-2 pl-3 border-l border-slate-800 hover:opacity-80 transition-opacity">
        <div className="w-7 h-7 rounded-full bg-gradient-to-br from-violet-500 to-purple-700 flex items-center justify-center text-xs font-bold text-white">
          U
        </div>
        <div className="hidden sm:block text-left">
          <p className="text-xs font-medium text-white leading-none">User</p>
          <p className="text-[10px] text-slate-500 leading-none mt-0.5">Analyst</p>
        </div>
        <ChevronDown className="w-3 h-3 text-slate-500" />
      </button>
    </header>
  );
}
