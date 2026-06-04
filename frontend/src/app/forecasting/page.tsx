"use client";

import { useState, useEffect } from "react";
import { Navbar } from "@/components/Navbar";
import { api } from "@/lib/api";
import type { DashboardStats, ForecastAlert, DriftRecord } from "@/types";
import { LineChart, Settings2, AlertTriangle, TrendingUp, TrendingDown, Info } from "lucide-react";

const EMPTY_STATS: DashboardStats = {
  critical_alerts: 0,
  pending_approvals: 0,
  approved_today: 0,
  po_value_pending: 0,
  avg_mape: 0,
  services: [],
};

export default function ForecastingPage() {
  const [stats, setStats] = useState<DashboardStats>(EMPTY_STATS);
  const [alerts, setAlerts] = useState<ForecastAlert[]>([]);
  const [drifts, setDrifts] = useState<DriftRecord[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.getStats(),
      api.getForecastAlerts(),
      api.getDriftSummary(),
    ])
      .then(([statsData, alertsData, driftsData]) => {
        setStats(statsData);
        setAlerts(alertsData);
        setDrifts(driftsData);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col">
      <Navbar stats={stats} />

      <main className="flex-1 p-4 md:p-6 max-w-[1400px] mx-auto w-full space-y-6">
        
        {/* Header Section */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <LineChart className="w-6 h-6 text-fuchsia-400" />
              Forecasting Models
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              Monitor predictive accuracy (MAPE) and AI-driven hyperparameter tuning.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="bg-slate-900 border border-slate-800 rounded-lg px-4 py-2 flex items-center gap-3">
              <span className="text-sm text-slate-400">System Avg MAPE:</span>
              <span className={`text-lg font-bold ${stats.avg_mape > 15 ? 'text-red-400' : 'text-emerald-400'}`}>
                {stats.avg_mape.toFixed(1)}%
              </span>
            </div>
            <div className="bg-fuchsia-500/10 border border-fuchsia-500/20 rounded-lg px-4 py-2 flex items-center gap-3">
              <span className="text-sm text-fuchsia-400">Active Models:</span>
              <span className="text-lg font-bold text-fuchsia-400">10</span>
            </div>
          </div>
        </div>

        {/* Forecast Alerts Grid */}
        <div className="space-y-4">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-amber-500" />
            Accuracy Alerts (MAPE &gt; 15%)
          </h2>
          {loading ? (
            <div className="h-32 bg-slate-900 rounded-xl animate-pulse" />
          ) : alerts.length === 0 ? (
            <div className="bg-emerald-500/10 border border-emerald-500/20 p-6 rounded-xl flex items-center justify-center text-emerald-400 gap-2">
              <Info className="w-5 h-5" />
              <p>All forecasting models are operating within acceptable accuracy bounds.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {alerts.map((alert) => (
                <div key={alert.product_id} className="bg-slate-900 border border-red-500/30 rounded-xl p-5 shadow-[0_4px_20px_-4px_rgba(239,68,68,0.1)] hover:border-red-500/50 transition-colors">
                  <div className="flex justify-between items-start mb-4">
                    <div>
                      <h3 className="font-semibold text-slate-100">{alert.product_name}</h3>
                      <p className="text-xs font-mono text-slate-500 mt-0.5">{alert.product_id}</p>
                    </div>
                    <span className="bg-red-500/20 text-red-400 px-2.5 py-1 rounded-md text-sm font-bold border border-red-500/30">
                      {alert.mape_pct.toFixed(1)}%
                    </span>
                  </div>
                  <div className="space-y-2 mb-4">
                    <p className="text-xs text-slate-400">
                      <span className="font-medium text-slate-300">Model:</span> {alert.model_name}
                    </p>
                    <p className="text-xs text-slate-400 line-clamp-2">
                      <span className="font-medium text-slate-300">Notes:</span> {alert.notes}
                    </p>
                  </div>
                  <div className="bg-slate-950 rounded p-3 text-xs font-mono text-slate-400">
                    {Object.entries(alert.hyperparameters).map(([k, v]) => (
                      <div key={k} className="flex justify-between">
                        <span>{k}</span>
                        <span className="text-slate-300">{v}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Model Drift History Table */}
        <div className="space-y-4 pt-6">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <Settings2 className="w-5 h-5 text-slate-400" />
            AI Hyperparameter Tuning Log
          </h2>
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
            {loading ? (
              <div className="h-64 flex items-center justify-center">
                <div className="w-8 h-8 border-2 border-fuchsia-500 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : drifts.length === 0 ? (
              <div className="p-8 text-center text-slate-500">
                No tuning history available.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="bg-slate-950/50 text-slate-400 border-b border-slate-800">
                    <tr>
                      <th className="px-6 py-4 font-medium">Date</th>
                      <th className="px-6 py-4 font-medium">Product</th>
                      <th className="px-6 py-4 font-medium">Action</th>
                      <th className="px-6 py-4 font-medium">Tuning Rationale</th>
                      <th className="px-6 py-4 font-medium">Impact (MAPE)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/50">
                    {drifts.map((drift) => (
                      <tr key={drift.id} className="hover:bg-slate-800/20 transition-colors">
                        <td className="px-6 py-4 text-slate-400 whitespace-nowrap">
                          {new Date(drift.proposed_at || "").toLocaleDateString()}
                        </td>
                        <td className="px-6 py-4">
                          <p className="font-medium text-slate-200">{drift.product_name}</p>
                          <p className="text-xs text-slate-500 font-mono mt-0.5">{drift.product_id}</p>
                        </td>
                        <td className="px-6 py-4">
                          <span className={`px-2 py-1 rounded text-xs capitalize border ${
                            drift.status === 'approved' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                            drift.status === 'rejected' ? 'bg-red-500/10 text-red-400 border-red-500/20' :
                            'bg-slate-800 text-slate-300 border-slate-700'
                          }`}>
                            {drift.status}
                          </span>
                        </td>
                        <td className="px-6 py-4">
                          <p className="text-slate-300 text-xs line-clamp-2 max-w-md" title={drift.rationale}>
                            {drift.rationale}
                          </p>
                          <div className="flex gap-4 mt-2 text-[10px] font-mono">
                            <div className="bg-slate-950 px-2 py-1 rounded text-slate-500">
                              Old: {Object.keys(drift.old_params).length} params
                            </div>
                            <div className="bg-fuchsia-500/10 text-fuchsia-400 px-2 py-1 rounded border border-fuchsia-500/20">
                              New: {Object.keys(drift.new_params).length} params
                            </div>
                          </div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          {drift.improved === null ? (
                            <span className="text-slate-500 italic text-xs">Awaiting evaluation...</span>
                          ) : drift.improved ? (
                            <div className="flex items-center gap-1.5 text-emerald-400 font-medium">
                              <TrendingDown className="w-4 h-4" />
                              -{drift.mape_delta_pct?.toFixed(1)}%
                            </div>
                          ) : (
                            <div className="flex items-center gap-1.5 text-red-400 font-medium">
                              <TrendingUp className="w-4 h-4" />
                              +{drift.mape_delta_pct?.toFixed(1)}%
                            </div>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
