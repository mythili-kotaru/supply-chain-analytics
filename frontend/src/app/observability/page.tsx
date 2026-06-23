"use client";

import { useState, useEffect } from "react";
import { Navbar } from "@/components/Navbar";
import { api } from "@/lib/api";
import type { DashboardStats } from "@/types";
import { Activity, ExternalLink, RefreshCw } from "lucide-react";

const ActivityIcon = Activity as any;
const ExternalLinkIcon = ExternalLink as any;
const RefreshCwIcon = RefreshCw as any;

const EMPTY_STATS: DashboardStats = {
  critical_alerts: 0,
  pending_approvals: 0,
  approved_today: 0,
  po_value_pending: 0,
  avg_mape: 0,
  services: [],
};

export default function ObservabilityPage() {
  const [stats, setStats] = useState<DashboardStats>(EMPTY_STATS);
  const [loading, setLoading] = useState(true);
  const [iframeKey, setIframeKey] = useState(0);

  useEffect(() => {
    api.getStats()
      .then(setStats)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const handleRefresh = () => {
    setIframeKey((prev) => prev + 1);
  };

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col">
      <Navbar stats={stats} />

      <main className="flex-1 p-4 md:p-6 max-w-[1600px] mx-auto w-full flex flex-col space-y-6">
        
        {/* Header Section */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <ActivityIcon className="w-6 h-6 text-blue-400" />
              Centralized Log Observability
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              Live container log streams collected via Promtail & Loki.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={handleRefresh}
              className="bg-slate-900 hover:bg-slate-800 text-slate-300 rounded-lg px-4 py-2 text-sm font-semibold flex items-center gap-2 border border-slate-800 transition-colors"
            >
              <RefreshCwIcon className="w-4 h-4" />
              Refresh Streams
            </button>
            
            <a
              href="http://localhost:3200/d/supply-chain-logs/supply-chain-ai-unified-logs?orgId=1"
              target="_blank"
              rel="noopener noreferrer"
              className="bg-blue-600 hover:bg-blue-700 text-white rounded-lg px-4 py-2 text-sm font-semibold flex items-center gap-2 border border-blue-500/30 hover:border-blue-500 transition-all shadow-lg shadow-blue-500/20 active:scale-95"
            >
              <ExternalLinkIcon className="w-4 h-4" />
              Open Grafana Console
            </a>
          </div>
        </div>

        {/* Embedded Grafana Dashboard */}
        <div className="flex-1 min-h-[650px] bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-2xl relative">
          <iframe
            key={iframeKey}
            src="http://localhost:3200/d/supply-chain-logs/supply-chain-ai-unified-logs?orgId=1&kiosk=tv&theme=dark"
            className="absolute inset-0 w-full h-full border-0"
            allow="autoplay; clipboard-write; encrypted-media; picture-in-picture"
          />
        </div>
      </main>
    </div>
  );
}
