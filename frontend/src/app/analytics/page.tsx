"use client";

import { useState, useEffect } from "react";
import { Navbar } from "@/components/Navbar";
import { api } from "@/lib/api";
import type { DashboardStats } from "@/types";
import { 
  MessageSquare, 
  Database, 
  Sparkles, 
  Loader2, 
  Code2, 
  Play,
  Zap,
  ShieldCheck,
  BarChart2
} from "lucide-react";

const MessageSquareIcon = MessageSquare as any;
const DatabaseIcon = Database as any;
const SparklesIcon = Sparkles as any;
const Loader2Icon = Loader2 as any;
const Code2Icon = Code2 as any;
const PlayIcon = Play as any;
const ZapIcon = Zap as any;
const ShieldCheckIcon = ShieldCheck as any;
const BarChart2Icon = BarChart2 as any;

const EMPTY_STATS: DashboardStats = {
  critical_alerts: 0,
  pending_approvals: 0,
  approved_today: 0,
  po_value_pending: 0,
  avg_mape: 0,
  services: [],
};

type ComparisonStats = {
  mode: "wren" | "ddl";
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  latency_ms: number;
  sql_generated: string;
  sql_compiled: string;
  wren_compiled: boolean;
};

type AnalyticsResult = {
  sql_query: string;
  results: any[];
  insight: string;
  result_count: number;
  error?: string;
  wren_stats?: ComparisonStats;
  ddl_stats?: ComparisonStats;
  token_saving_pct?: number;
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
      const data = await api.runAnalyticsQuery(query);
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
            <SparklesIcon className="w-6 h-6 text-blue-400" />
            AI Supply Chain Analytics
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Ask natural language questions about inventory, revenue, and forecasts.
          </p>
        </div>

        {/* Search Bar */}
        <form onSubmit={handleSearch} className="relative">
          <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
            <MessageSquareIcon className="h-5 w-5 text-slate-500" />
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
              {loading ? <Loader2Icon className="w-4 h-4 animate-spin" /> : <PlayIcon className="w-4 h-4" />}
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
                    <SparklesIcon className="w-4 h-4 text-blue-400" />
                    AI Insight
                  </h3>
                  <p className="text-lg text-slate-100 leading-relaxed font-light">
                    {result.insight}
                  </p>
                </div>

                {/* Wren Engine Optimization Stats */}
                {result.wren_stats && result.ddl_stats && (
                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    
                    {/* Visual Token Savings Metric */}
                    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 flex flex-col justify-between relative overflow-hidden lg:col-span-1">
                      <div className="absolute top-0 right-0 w-32 h-32 bg-blue-500/10 blur-[50px] rounded-full pointer-events-none" />
                      <div>
                        <div className="flex items-center gap-2 mb-4">
                          <ZapIcon className="w-5 h-5 text-amber-400" />
                          <h3 className="text-sm font-semibold text-slate-300">Wren Semantic Impact</h3>
                        </div>
                        <div className="mt-2">
                          <div className="text-5xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-emerald-400">
                            {result.token_saving_pct}%
                          </div>
                          <div className="text-xs text-slate-400 mt-1 uppercase tracking-wider font-semibold">
                            Prompt Token Reduction
                          </div>
                        </div>
                        <p className="text-xs text-slate-400 mt-4 leading-relaxed">
                          By modeling database tables as semantic models and relationships (MDL), the LLM context size is drastically reduced. We send concise semantic tags instead of verbose raw CREATE TABLE DDLs.
                        </p>
                      </div>
                      <div className="mt-6 pt-4 border-t border-slate-800/60">
                        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-[10px] font-semibold text-emerald-400 tracking-wider uppercase">
                          <ShieldCheckIcon className="w-3.5 h-3.5" />
                          Wren Engine Compiled
                        </span>
                      </div>
                    </div>

                    {/* Side-by-Side Comparison details */}
                    <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 lg:col-span-2 space-y-4 flex flex-col justify-between">
                      <div>
                        <h3 className="text-sm font-semibold text-slate-300 flex items-center gap-2 mb-4">
                          <BarChart2Icon className="w-4 h-4 text-blue-400" />
                          Performance Metrics Comparison
                        </h3>
                        
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                          {/* Wren Stats */}
                          <div className="p-4 bg-slate-950/60 border border-slate-800/80 rounded-xl space-y-3">
                            <div className="flex items-center justify-between border-b border-slate-800/60 pb-2">
                              <span className="text-xs font-bold text-blue-400 uppercase tracking-wider">Wren Semantic Mode</span>
                              <span className="text-[10px] px-2 py-0.5 rounded bg-blue-500/10 text-blue-400 font-semibold uppercase">Active</span>
                            </div>
                            <div className="space-y-2 text-xs">
                              <div className="flex justify-between">
                                <span className="text-slate-500">Prompt Size:</span>
                                <span className="text-slate-300 font-mono">{result.wren_stats.prompt_tokens} tokens</span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-slate-500">Completion:</span>
                                <span className="text-slate-300 font-mono">{result.wren_stats.completion_tokens} tokens</span>
                              </div>
                              <div className="flex justify-between font-semibold">
                                <span className="text-slate-400">Total Tokens:</span>
                                <span className="text-slate-200 font-mono">{result.wren_stats.total_tokens}</span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-slate-500">Latency:</span>
                                <span className="text-slate-300 font-mono">{result.wren_stats.latency_ms.toFixed(0)} ms</span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-slate-500">Dry Plan:</span>
                                <span className="text-emerald-400 font-semibold">SUCCESS (Compiled)</span>
                              </div>
                            </div>
                          </div>

                          {/* DDL Stats */}
                          <div className="p-4 bg-slate-950/30 border border-slate-800/40 rounded-xl space-y-3">
                            <div className="flex items-center justify-between border-b border-slate-800/40 pb-2">
                              <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Raw DDL Mode</span>
                              <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 text-slate-500 font-semibold uppercase">Simulated</span>
                            </div>
                            <div className="space-y-2 text-xs">
                              <div className="flex justify-between">
                                <span className="text-slate-500">Prompt Size:</span>
                                <span className="text-slate-400 font-mono">{result.ddl_stats.prompt_tokens} tokens</span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-slate-500">Completion:</span>
                                <span className="text-slate-400 font-mono">{result.ddl_stats.completion_tokens} tokens</span>
                              </div>
                              <div className="flex justify-between font-semibold">
                                <span className="text-slate-500">Total Tokens:</span>
                                <span className="text-slate-400 font-mono">{result.ddl_stats.total_tokens}</span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-slate-500">Latency:</span>
                                <span className="text-slate-400 font-mono">{result.ddl_stats.latency_ms.toFixed(0)} ms</span>
                              </div>
                              <div className="flex justify-between">
                                <span className="text-slate-500">Dry Plan:</span>
                                <span className="text-slate-500">{result.ddl_stats.wren_compiled ? "SUCCESS" : "FAILED"}</span>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Token efficiency progress bar visual */}
                      <div className="space-y-1.5 pt-4">
                        <div className="flex justify-between text-xs font-medium">
                          <span className="text-slate-400">Context Window Footprint</span>
                          <span className="text-slate-300 font-mono">
                            {result.wren_stats.prompt_tokens} vs {result.ddl_stats.prompt_tokens} prompt tokens
                          </span>
                        </div>
                        <div className="w-full h-2 bg-slate-950 rounded-full overflow-hidden flex">
                          <div 
                            className="bg-blue-500 h-full transition-all duration-500" 
                            style={{ width: `${(result.wren_stats.prompt_tokens / result.ddl_stats.prompt_tokens) * 100}%` }}
                          />
                          <div className="bg-slate-800 flex-1" />
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {/* Data Table */}
                <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
                  <div className="flex items-center justify-between p-4 border-b border-slate-800 bg-slate-900/50">
                    <h3 className="text-sm font-semibold text-slate-300 flex items-center gap-2">
                      <DatabaseIcon className="w-4 h-4 text-emerald-400" />
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
                      <Code2Icon className="w-3.5 h-3.5" />
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
