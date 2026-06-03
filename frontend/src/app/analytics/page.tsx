"use client";

import { useState, useEffect } from "react";
import { Navbar } from "@/components/Navbar";
import { api } from "@/lib/api";
import type { DashboardStats } from "@/types";
import { MessageSquare, Database, Sparkles, Loader2, Code2, Play } from "lucide-react";

const EMPTY_STATS: DashboardStats = {
  critical_alerts: 0,
  pending_approvals: 0,
  approved_today: 0,
  po_value_pending: 0,
  avg_mape: 0,
  services: [],
};

type AnalyticsResult = {
  sql_query: string;
  results: any[];
  insight: string;
  result_count: number;
  error?: string;
};

export default function AnalyticsPage() {
  const [stats, setStats] = useState<DashboardStats>(EMPTY_STATS);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<AnalyticsResult | null>(null);
  const [showSql, setShowSql] = useState(false);

  // Load stats for Navbar
  useEffect(() => {
    api.getStats().then(setStats).catch(console.error);
  }, []);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setResult(null);
    try {
      const res = await fetch("http://localhost:8003/api/dashboard/analytics/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });
      if (!res.ok) throw new Error("Failed to fetch analytics");
      const data = await res.json();
      setResult(data);
    } catch (err) {
      console.error(err);
      setResult({
        sql_query: "",
        results: [],
        insight: "",
        result_count: 0,
        error: "Failed to connect to Analytics Engine.",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col">
      <Navbar stats={stats} />
      
      <main className="flex-1 p-4 md:p-6 max-w-[1200px] mx-auto w-full space-y-6">
        
        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-white flex items-center gap-2">
            <Sparkles className="w-6 h-6 text-blue-400" />
            AI Supply Chain Analytics
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Ask natural language questions about inventory, revenue, and forecasts.
          </p>
        </div>

        {/* Search Bar */}
        <form onSubmit={handleSearch} className="relative">
          <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
            <MessageSquare className="h-5 w-5 text-slate-500" />
          </div>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. Which products have a MAPE higher than 20%?"
            className="block w-full pl-11 pr-32 py-4 bg-slate-900 border border-slate-800 rounded-xl text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500 transition-all text-lg"
          />
          <div className="absolute inset-y-0 right-2 flex items-center">
            <button
              type="submit"
              disabled={loading || !query.trim()}
              className="px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium rounded-lg transition-colors flex items-center gap-2"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              Analyze
            </button>
          </div>
        </form>

        {/* Results Area */}
        {result && (
          <div className="space-y-6 animate-slide-up">
            
            {/* Error State */}
            {result.error && (
              <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-xl text-red-400">
                <p className="font-medium">Analysis Failed</p>
                <p className="text-sm mt-1">{result.error}</p>
              </div>
            )}

            {/* Success State */}
            {!result.error && (
              <>
                {/* AI Insight */}
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 relative overflow-hidden">
                  <div className="absolute top-0 right-0 p-32 bg-blue-500/5 blur-[100px] rounded-full pointer-events-none" />
                  <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-blue-400" />
                    AI Insight
                  </h3>
                  <p className="text-lg text-slate-100 leading-relaxed font-light">
                    {result.insight}
                  </p>
                </div>

                {/* Data Table */}
                <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
                  <div className="flex items-center justify-between p-4 border-b border-slate-800 bg-slate-900/50">
                    <h3 className="text-sm font-semibold text-slate-300 flex items-center gap-2">
                      <Database className="w-4 h-4 text-emerald-400" />
                      Data Source ({result.result_count} rows)
                    </h3>
                    <button
                      onClick={() => setShowSql(!showSql)}
                      className={`text-xs px-3 py-1.5 rounded-lg border flex items-center gap-1.5 transition-colors ${
                        showSql 
                          ? "bg-slate-800 text-slate-200 border-slate-700" 
                          : "bg-transparent text-slate-400 border-slate-800 hover:bg-slate-800 hover:text-slate-300"
                      }`}
                    >
                      <Code2 className="w-3.5 h-3.5" />
                      {showSql ? "Hide SQL" : "View SQL"}
                    </button>
                  </div>

                  {/* SQL View */}
                  {showSql && (
                    <div className="p-4 bg-slate-950 border-b border-slate-800">
                      <pre className="text-xs text-blue-400 font-mono overflow-x-auto">
                        <code>{result.sql_query}</code>
                      </pre>
                    </div>
                  )}

                  {/* Table View */}
                  <div className="overflow-x-auto">
                    {result.results.length > 0 ? (
                      <table className="w-full text-left text-sm">
                        <thead className="bg-slate-950/50 text-slate-400 border-b border-slate-800">
                          <tr>
                            {Object.keys(result.results[0]).map((key) => (
                              <th key={key} className="px-4 py-3 font-medium whitespace-nowrap">
                                {key}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-800/50">
                          {result.results.map((row, i) => (
                            <tr key={i} className="hover:bg-slate-800/20 transition-colors">
                              {Object.values(row).map((val: any, j) => (
                                <td key={j} className="px-4 py-3 text-slate-300 whitespace-nowrap">
                                  {typeof val === 'number' && !Number.isInteger(val) 
                                    ? val.toFixed(2) 
                                    : String(val)}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    ) : (
                      <div className="p-8 text-center text-slate-500">
                        No data available to display.
                      </div>
                    )}
                  </div>
                </div>
              </>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
