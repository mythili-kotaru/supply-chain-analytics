"use client";

import { useState, useEffect } from "react";
import { Navbar } from "@/components/Navbar";
import { SupplierScorecard } from "@/components/SupplierScorecard";
import { api } from "@/lib/api";
import type { DashboardStats } from "@/types";
import { Truck } from "lucide-react";

const TruckIcon = Truck as any;

const EMPTY_STATS: DashboardStats = {
  critical_alerts: 0,
  pending_approvals: 0,
  approved_today: 0,
  po_value_pending: 0,
  avg_mape: 0,
  services: [],
};

export default function SourcingPage() {
  const [stats, setStats] = useState<DashboardStats>(EMPTY_STATS);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getStats()
      .then((statsData) => {
        setStats(statsData);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col">
      <Navbar stats={stats} onToggleCoPilot={() => {}} />

      <main className="flex-1 p-4 md:p-6 max-w-[1400px] mx-auto w-full space-y-6">
        
        {/* Header Section */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2.5">
              <TruckIcon className="w-6 h-6 text-blue-400" />
              Dynamic Supplier Sourcing & Risk Optimizer
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              Historical lead-time variance engine, unit manufacturing cost benchmarks, and risk-hedged split allocation strategies.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="bg-slate-900 border border-slate-800 rounded-lg px-4 py-2 flex items-center gap-3">
              <span className="text-sm text-slate-400">Policy Mode:</span>
              <span className="text-xs font-semibold px-2 py-0.5 rounded bg-blue-500/10 border border-blue-500/30 text-blue-400">
                Multi-Criteria Split PO (&gt;150 Units)
              </span>
            </div>
          </div>
        </div>

        {/* Scorecard Directory */}
        <div className="fade-in">
          <SupplierScorecard />
        </div>
      </main>
    </div>
  );
}
