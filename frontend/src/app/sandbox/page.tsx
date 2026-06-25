"use client";

import React, { useState, useEffect, useMemo } from "react";
import { Line } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title as ChartTitle,
  Tooltip,
  Legend,
  Filler,
} from "chart.js";
import { 
  Zap, 
  TrendingUp, 
  Clock, 
  AlertTriangle, 
  ArrowUpRight, 
  ArrowRight,
  TrendingDown,
  RefreshCw,
  ShoppingBag,
  ArrowRightLeft,
  Info,
} from "lucide-react";
import { Navbar } from "@/components/Navbar";
import { api } from "@/lib/api";
import { useToast } from "@/components/Toast";
import type { 
  DashboardStats, 
  SimulationResponse, 
  ChartData,
  MitigationAction,
  SupplierScorecardItem
} from "@/types";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  ChartTitle,
  Tooltip,
  Legend,
  Filler
);

const EMPTY_STATS: DashboardStats = {
  critical_alerts: 0,
  pending_approvals: 0,
  approved_today: 0,
  po_value_pending: 0,
  avg_mape: 0,
  services: [],
};

const ZapIcon = Zap as any;
const TrendingUpIcon = TrendingUp as any;
const ClockIcon = Clock as any;
const AlertTriangleIcon = AlertTriangle as any;
const ArrowUpRightIcon = ArrowUpRight as any;
const ArrowRightIcon = ArrowRight as any;
const TrendingDownIcon = TrendingDown as any;
const RefreshCwIcon = RefreshCw as any;
const ShoppingBagIcon = ShoppingBag as any;
const ArrowRightLeftIcon = ArrowRightLeft as any;
const InfoIcon = Info as any;

export default function SandboxPage() {
  const { addToast } = useToast();
  const [stats, setStats] = useState<DashboardStats>(EMPTY_STATS);
  const [suppliers, setSuppliers] = useState<SupplierScorecardItem[]>([]);
  
  // Simulation params
  const [demandMultiplier, setDemandMultiplier] = useState(1.0);
  const [leadTimeMultiplier, setLeadTimeMultiplier] = useState(1.0);
  const [disruptedSupplierId, setDisruptedSupplierId] = useState<string>("");
  
  // Simulation results
  const [simResults, setSimResults] = useState<SimulationResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [simulating, setSimulating] = useState(false);

  // Selected item for the detail line chart
  const [selectedKey, setSelectedKey] = useState<string>("");

  // Fetch initial stats and suppliers list
  useEffect(() => {
    Promise.all([api.getStats(), api.getSourcingScorecard()])
      .then(([statsData, sourcingData]) => {
        setStats(statsData);
        setSuppliers(sourcingData);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  // Trigger simulation run when parameters change
  const handleRunSimulation = async (
    demand: number, 
    lead: number, 
    supplierId: string
  ) => {
    setSimulating(true);
    try {
      const data = await api.runSimulation({
        demand_multiplier: demand,
        lead_time_multiplier: lead,
        disrupted_supplier_id: supplierId || null,
      });
      setSimResults(data);
      
      // Auto-select first chart if none is selected or previous selection is gone
      if (data.charts.length > 0) {
        const firstKey = `${data.charts[0].product_id}::${data.charts[0].location}`;
        if (!selectedKey || !data.charts.some(c => `${c.product_id}::${c.location}` === selectedKey)) {
          setSelectedKey(firstKey);
        }
      }
    } catch (e: any) {
      console.error(e);
      addToast(e.message || "Failed to run scenario simulation", "error");
    } finally {
      setSimulating(false);
    }
  };

  // Run simulation initial load or on reset
  useEffect(() => {
    if (!loading) {
      handleRunSimulation(demandMultiplier, leadTimeMultiplier, disruptedSupplierId);
    }
  }, [loading]);

  const handleApplyMitigation = async (action: MitigationAction) => {
    addToast(
      <div className="flex items-center gap-2">
        <div className="w-3.5 h-3.5 border border-slate-350 border-t-transparent rounded-full animate-spin flex-shrink-0" />
        <span className="text-xs text-slate-300">Drafting sandbox proposal in database...</span>
      </div>,
      "info"
    );

    try {
      const result = await api.applyMitigation(action);
      
      // Update local stats counter to increment pending approvals
      setStats((prev) => ({
        ...prev,
        pending_approvals: prev.pending_approvals + 1,
      }));

      addToast(
        <div className="flex flex-col gap-1">
          <span className="font-semibold text-white">Mitigation Proposal Drafted!</span>
          <span className="text-xs text-slate-300">
            {action.action_type === "transfer" 
              ? `Drafted transfer of ${action.quantity} units from ${action.source_location || "Northeast"}.`
              : `Drafted purchase order for ${action.quantity} units from ${action.supplier_name || "primary supplier"}.`
            }
          </span>
          <span className="text-[10px] text-blue-400 mt-1 font-mono">
            Supervisor thread registered: {result.proposal_id.slice(0, 8)}
          </span>
        </div>,
        "success"
      );
    } catch (e: any) {
      console.error(e);
      addToast(e.message || "Failed to apply sandbox mitigation", "error");
    }
  };

  const handleReset = () => {
    setDemandMultiplier(1.0);
    setLeadTimeMultiplier(1.0);
    setDisruptedSupplierId("");
    handleRunSimulation(1.0, 1.0, "");
    addToast("Scenario sandbox parameters reset to baseline configuration", "info");
  };

  // Extract selected chart data
  const selectedChart = useMemo(() => {
    if (!simResults || !selectedKey) return null;
    const [pid, loc] = selectedKey.split("::");
    return simResults.charts.find(c => c.product_id === pid && c.location === loc) || null;
  }, [simResults, selectedKey]);

  // Chart configuration
  const lineChartData = useMemo(() => {
    if (!selectedChart) return { labels: [], datasets: [] };
    
    const labels = selectedChart.timeline.map(p => `Day ${p.day}`);
    const baseStock = selectedChart.timeline.map(p => p.base_stock);
    const simulatedStock = selectedChart.timeline.map(p => p.simulated_stock);

    return {
      labels,
      datasets: [
        {
          label: "Baseline Projection",
          data: baseStock,
          borderColor: "rgb(59, 130, 246)",
          backgroundColor: "rgba(59, 130, 246, 0.05)",
          borderWidth: 2,
          pointRadius: 1,
          pointHoverRadius: 4,
          fill: true,
        },
        {
          label: "Simulated Scenario",
          data: simulatedStock,
          borderColor: "rgb(236, 72, 153)",
          backgroundColor: "rgba(236, 72, 153, 0.05)",
          borderWidth: 2.5,
          pointRadius: 1,
          pointHoverRadius: 4,
          fill: true,
        }
      ]
    };
  }, [selectedChart]);

  const lineChartOptions = useMemo(() => {
    if (!simResults || !selectedKey) return {};
    
    // Find the item details to get reorder point
    const [pid, loc] = selectedKey.split("::");
    const detail = simResults.stockout_details.find(d => d.product_id === pid && d.location === loc);
    
    // Find the original item to get reorder point
    let reorderPoint = 150;
    const firstChart = simResults.charts.find(c => c.product_id === pid && c.location === loc);
    
    return {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        y: {
          min: 0,
          grid: { color: "rgba(255,255,255,0.05)" },
          ticks: { color: "#64748b" }
        },
        x: {
          grid: { display: false },
          ticks: { 
            color: "#64748b",
            maxTicksLimit: 10
          }
        }
      },
      plugins: {
        legend: {
          position: "top" as const,
          labels: { color: "#94a3b8", font: { size: 12 } }
        },
        tooltip: {
          mode: "index" as const,
          intersect: false,
          backgroundColor: "#0f172a",
          titleColor: "#f8fafc",
          bodyColor: "#cbd5e1",
          borderColor: "#334155",
          borderWidth: 1,
        }
      }
    };
  }, [simResults, selectedKey]);

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col text-slate-100">
      <Navbar stats={stats} onToggleCoPilot={() => {}} />

      <main className="flex-1 p-4 md:p-6 max-w-[1400px] mx-auto w-full space-y-6">
        
        {/* Header Section */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2.5">
              <ZapIcon className="w-6 h-6 text-fuchsia-400" />
              What-If Demand Simulation & Scenario Sandbox
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              Simulate localized demand surges and supplier delivery disruptions. Project 30-day stock depletion curves and evaluate AI-driven mitigations.
            </p>
          </div>

          <button
            onClick={handleReset}
            className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-slate-300 hover:text-white bg-slate-900 hover:bg-slate-800 border border-slate-800 rounded-lg transition-colors"
          >
            <RefreshCwIcon className="w-4 h-4" />
            Reset Sandbox
          </button>
        </div>

        {/* Top Controls and Stats Deck */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          
          {/* Simulation Parameter Controls Deck */}
          <div className="lg:col-span-1 bg-slate-900/50 backdrop-blur-md border border-slate-800 rounded-xl p-5 flex flex-col gap-5">
            <div>
              <h2 className="text-base font-semibold text-white">Scenario Parameters</h2>
              <p className="text-xs text-slate-500 mt-0.5">Tweak variables to recalculate projections instantly</p>
            </div>

            {/* Demand Spike Multiplier */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                  <TrendingUpIcon className="w-3.5 h-3.5 text-blue-400" />
                  Demand Spike Multiplier
                </label>
                <span className="text-xs font-mono font-semibold px-2 py-0.5 bg-blue-500/10 border border-blue-500/30 text-blue-400 rounded">
                  {demandMultiplier.toFixed(1)}x
                </span>
              </div>
              <input
                type="range"
                min="1.0"
                max="4.0"
                step="0.1"
                value={demandMultiplier}
                onChange={(e) => {
                  const val = parseFloat(e.target.value);
                  setDemandMultiplier(val);
                  handleRunSimulation(val, leadTimeMultiplier, disruptedSupplierId);
                }}
                className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-blue-500"
              />
              <div className="flex justify-between text-[10px] text-slate-500">
                <span>Baseline (1x)</span>
                <span>Double (2x)</span>
                <span>Triple (3x)</span>
                <span>Max (4x)</span>
              </div>
            </div>

            {/* Lead Time Multiplier */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                  <ClockIcon className="w-3.5 h-3.5 text-indigo-400" />
                  Lead Time Multiplier
                </label>
                <span className="text-xs font-mono font-semibold px-2 py-0.5 bg-indigo-500/10 border border-indigo-500/30 text-indigo-400 rounded">
                  {leadTimeMultiplier.toFixed(1)}x
                </span>
              </div>
              <input
                type="range"
                min="1.0"
                max="3.0"
                step="0.1"
                value={leadTimeMultiplier}
                onChange={(e) => {
                  const val = parseFloat(e.target.value);
                  setLeadTimeMultiplier(val);
                  handleRunSimulation(demandMultiplier, val, disruptedSupplierId);
                }}
                className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
              />
              <div className="flex justify-between text-[10px] text-slate-500">
                <span>Standard (1x)</span>
                <span>1.5x Days</span>
                <span>Double (2x)</span>
                <span>Triple (3x)</span>
              </div>
            </div>

            {/* Supplier Outage Selection */}
            <div className="space-y-2">
              <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                <AlertTriangleIcon className="w-3.5 h-3.5 text-amber-500" />
                Supplier Shipment Outage
              </label>
              <select
                value={disruptedSupplierId}
                onChange={(e) => {
                  const val = e.target.value;
                  setDisruptedSupplierId(val);
                  handleRunSimulation(demandMultiplier, leadTimeMultiplier, val);
                }}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-300 outline-none focus:border-blue-500 transition-colors"
              >
                <option value="">No Active Outages (All Healthy)</option>
                {suppliers.map((sup) => (
                  <option key={sup.supplier_id} value={sup.supplier_id}>
                    Outage: {sup.supplier_name} ({sup.supplier_id})
                  </option>
                ))}
              </select>
              <p className="text-[10px] text-slate-500 leading-normal">
                Simulates a complete delivery freeze. Orders dispatched to the chosen supplier will fail to arrive during the 30-day projection period.
              </p>
            </div>
          </div>

          {/* Scenario Impact Statistics Deck */}
          <div className="lg:col-span-2 grid grid-cols-1 md:grid-cols-2 gap-4">
            
            {/* Financial Impact Stats Card */}
            <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 flex flex-col justify-between shadow-xl">
              <div>
                <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Financial Risk Projections</h3>
                <p className="text-xs text-slate-500 mt-0.5">Potential revenue lost to projected stockouts</p>
              </div>

              <div className="my-4 space-y-3">
                <div className="flex justify-between items-baseline">
                  <span className="text-xs text-slate-400">Baseline Deficit:</span>
                  <span className="text-sm font-mono text-slate-300">
                    ${simResults?.summary.base_lost_revenue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                </div>
                <div className="flex justify-between items-baseline border-b border-slate-800 pb-2">
                  <span className="text-xs text-slate-400">Simulated Scenario Deficit:</span>
                  <span className="text-sm font-mono text-white font-semibold">
                    ${simResults?.summary.simulated_lost_revenue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                </div>
                <div className="flex justify-between items-baseline pt-1">
                  <span className="text-xs font-semibold text-slate-300">Scenario Net Impact:</span>
                  <span className={`text-lg font-mono font-bold ${
                    (simResults?.summary.revenue_impact || 0) > 0 ? "text-rose-400" : "text-emerald-400"
                  }`}>
                    {(simResults?.summary.revenue_impact || 0) > 0 ? "+" : ""}
                    ${simResults?.summary.revenue_impact.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                  </span>
                </div>
              </div>

              <div className={`text-[10px] px-3 py-1.5 rounded flex items-start gap-1.5 ${
                (simResults?.summary.revenue_impact || 0) > 0 
                  ? "bg-rose-500/10 border border-rose-500/20 text-rose-400" 
                  : "bg-slate-950 border border-slate-800 text-slate-400"
              }`}>
                <InfoIcon className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                <span>
                  {(simResults?.summary.revenue_impact || 0) > 0 
                    ? `Demand spike/logistics bottlenecks increase lost revenue risk by $${simResults?.summary.revenue_impact.toLocaleString()} over 30 days.` 
                    : "No incremental financial deficits projected vs baseline system settings."
                  }
                </span>
              </div>
            </div>

            {/* Operational Impact Stats Card */}
            <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-5 flex flex-col justify-between shadow-xl">
              <div>
                <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Product Deficit Alerts</h3>
                <p className="text-xs text-slate-500 mt-0.5">Projected number of region-SKU stockout events</p>
              </div>

              <div className="my-4 grid grid-cols-2 gap-4">
                <div className="bg-slate-950/60 rounded-lg p-3 border border-slate-850 flex flex-col items-center justify-center">
                  <span className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider">Baseline Alerts</span>
                  <span className="text-2xl font-bold text-slate-300 mt-1">
                    {simResults?.summary.base_stockouts}
                  </span>
                  <span className="text-[9px] text-slate-500 mt-0.5">SKU-region pairs</span>
                </div>
                <div className={`rounded-lg p-3 border flex flex-col items-center justify-center ${
                  (simResults?.summary.simulated_stockouts || 0) > (simResults?.summary.base_stockouts || 0)
                    ? "bg-rose-500/5 border-rose-500/20"
                    : "bg-slate-950/60 border-slate-850"
                }`}>
                  <span className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider">Simulated Alerts</span>
                  <span className={`text-2xl font-bold mt-1 ${
                    (simResults?.summary.simulated_stockouts || 0) > (simResults?.summary.base_stockouts || 0)
                      ? "text-rose-400"
                      : "text-slate-300"
                  }`}>
                    {simResults?.summary.simulated_stockouts}
                  </span>
                  <span className="text-[9px] text-slate-500 mt-0.5">SKU-region pairs</span>
                </div>
              </div>

              <div className={`text-[10px] px-3 py-1.5 rounded flex items-start gap-1.5 ${
                (simResults?.summary.simulated_stockouts || 0) > (simResults?.summary.base_stockouts || 0)
                  ? "bg-rose-500/10 border border-rose-500/20 text-rose-400" 
                  : "bg-slate-950 border border-slate-800 text-slate-400"
              }`}>
                <InfoIcon className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
                <span>
                  {(simResults?.summary.simulated_stockouts || 0) > (simResults?.summary.base_stockouts || 0)
                    ? `Additional ${(simResults?.summary.simulated_stockouts || 0) - (simResults?.summary.base_stockouts || 0)} location-SKU pair(s) are projected to exhaust stock within 30 days.` 
                    : "No new inventory stockouts projected under simulated parameters."
                  }
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Main Charts & Mitigation Proposals Area */}
        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
          
          {/* Interactive Chart Section */}
          <div className="xl:col-span-2 bg-slate-900/50 backdrop-blur-md border border-slate-800 rounded-xl p-5 flex flex-col shadow-xl">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-5 border-b border-slate-800/80 pb-4">
              <div>
                <h3 className="text-base font-semibold text-white">Daily Projected Inventory Trajectory</h3>
                <p className="text-xs text-slate-500 mt-0.5">30-day projection curves under scenario conditions</p>
              </div>

              {/* Selector for which SKU-region pair to chart */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-400 hidden sm:inline">SKU:</span>
                <select
                  value={selectedKey}
                  onChange={(e) => setSelectedKey(e.target.value)}
                  className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 outline-none focus:border-blue-500"
                >
                  {simResults?.charts.map((c) => (
                    <option key={`${c.product_id}::${c.location}`} value={`${c.product_id}::${c.location}`}>
                      {c.product_name} ({c.location})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Line Chart */}
            <div className="relative flex-1 min-h-[300px] h-80">
              {simulating ? (
                <div className="absolute inset-0 flex items-center justify-center bg-slate-950/20">
                  <div className="flex flex-col items-center gap-3">
                    <div className="w-8 h-8 border-2 border-fuchsia-500 border-t-transparent rounded-full animate-spin" />
                    <span className="text-xs text-slate-400">Recalculating curves...</span>
                  </div>
                </div>
              ) : selectedChart ? (
                <Line data={lineChartData} options={lineChartOptions} />
              ) : (
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="text-xs text-slate-500">Select a SKU from the dropdown to load the chart</span>
                </div>
              )}
            </div>

            {/* Chart Summary Footnote */}
            {selectedChart && (
              <div className="mt-4 pt-3 border-t border-slate-800/50 flex flex-wrap gap-x-6 gap-y-2 text-xs text-slate-400">
                <div>
                  <span className="text-slate-500 font-semibold">SKU:</span>{" "}
                  <span className="text-slate-300">{selectedChart.product_id}</span>
                </div>
                <div>
                  <span className="text-slate-500 font-semibold">Location:</span>{" "}
                  <span className="text-slate-300">{selectedChart.location}</span>
                </div>
                {simResults && (
                  <>
                    {(() => {
                      const detail = simResults.stockout_details.find(
                        d => d.product_id === selectedChart.product_id && d.location === selectedChart.location
                      );
                      if (!detail) return null;
                      return (
                        <>
                          <div>
                            <span className="text-slate-500 font-semibold">Base Stockout Day:</span>{" "}
                            <span className={detail.base_days_to_stockout <= 30 ? "text-amber-400" : "text-emerald-400"}>
                              {detail.base_days_to_stockout <= 30 ? `Day ${detail.base_days_to_stockout}` : "Never"}
                            </span>
                          </div>
                          <div>
                            <span className="text-slate-500 font-semibold">Simulated Stockout Day:</span>{" "}
                            <span className={detail.simulated_days_to_stockout <= 30 ? "text-rose-400 font-semibold" : "text-emerald-400"}>
                              {detail.simulated_days_to_stockout <= 30 ? `Day ${detail.simulated_days_to_stockout}` : "Never"}
                            </span>
                          </div>
                        </>
                      );
                    })()}
                  </>
                )}
              </div>
            )}
          </div>

          {/* AI Recommended Mitigations Section */}
          <div className="xl:col-span-1 bg-slate-900/50 backdrop-blur-md border border-slate-800 rounded-xl p-5 flex flex-col shadow-xl">
            <div className="mb-4 pb-3 border-b border-slate-800/80">
              <h3 className="text-base font-semibold text-white">AI Mitigation Proposals</h3>
              <p className="text-xs text-slate-500 mt-0.5">Recommendations to resolve simulated stockouts</p>
            </div>

            <div className="flex-1 overflow-y-auto space-y-3 max-h-[360px] pr-1 scrollbar-thin">
              {simulating ? (
                <div className="flex items-center justify-center py-10">
                  <div className="w-6 h-6 border-2 border-fuchsia-500 border-t-transparent rounded-full animate-spin" />
                </div>
              ) : simResults && simResults.mitigations.length > 0 ? (
                simResults.mitigations.map((action, idx) => (
                  <div 
                    key={idx} 
                    className="bg-slate-950/60 border border-slate-800 hover:border-slate-700 rounded-lg p-3.5 flex flex-col gap-3 transition-colors shadow-inner"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex flex-col gap-0.5">
                        <span className="text-xs font-semibold text-white">{action.product_name}</span>
                        <span className="text-[10px] text-slate-500 font-mono">{action.product_id} @ {action.location}</span>
                      </div>
                      
                      {/* Action Type Badge */}
                      <span className={`text-[9px] font-bold tracking-wider px-2 py-0.5 rounded-full ${
                        action.action_type === "transfer"
                          ? "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                          : "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                      }`}>
                        {action.action_type.toUpperCase()}
                      </span>
                    </div>

                    <p className="text-xs text-slate-300 leading-normal bg-slate-950 p-2 rounded border border-slate-900 flex items-start gap-2">
                      {action.action_type === "transfer" ? (
                        <ArrowRightLeftIcon className="w-3.5 h-3.5 text-blue-400 flex-shrink-0 mt-0.5" />
                      ) : (
                        <ShoppingBagIcon className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0 mt-0.5" />
                      )}
                      <span>{action.details}</span>
                    </p>

                    <button
                      onClick={() => handleApplyMitigation(action)}
                      className="w-full py-1.5 text-xs font-medium bg-slate-900 hover:bg-slate-850 hover:text-white border border-slate-800 rounded-lg transition-colors flex items-center justify-center gap-1"
                    >
                      <span>Draft Action Plan</span>
                      <ArrowRightIcon className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))
              ) : (
                <div className="flex flex-col items-center justify-center py-10 px-4 text-center">
                  <div className="w-10 h-10 rounded-full bg-slate-950 flex items-center justify-center mb-3">
                    <ZapIcon className="w-5 h-5 text-slate-650" />
                  </div>
                  <span className="text-xs text-slate-400 font-semibold">All Stocks Secure</span>
                  <span className="text-[10px] text-slate-500 mt-1 max-w-[200px]">
                    No stockout events projected in the simulated scenario. No mitigations required.
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Detailed Grid Section */}
        <div className="bg-slate-900/50 backdrop-blur-md border border-slate-800 rounded-xl p-5 shadow-xl">
          <div className="mb-4">
            <h3 className="text-base font-semibold text-white">SKU-Region Scenario Impact Matrix</h3>
            <p className="text-xs text-slate-500 mt-0.5">Comparison of baseline vs simulated metrics for each node</p>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-850 text-slate-400 text-xs font-semibold uppercase tracking-wider">
                  <th className="py-3 px-4">Product Name / ID</th>
                  <th className="py-3 px-4">Location</th>
                  <th className="py-3 px-4 text-center">Base Stockout Day</th>
                  <th className="py-3 px-4 text-center">Simulated Stockout Day</th>
                  <th className="py-3 px-4 text-right">Base Loss</th>
                  <th className="py-3 px-4 text-right">Simulated Loss</th>
                  <th className="py-3 px-4 text-right">Revenue Delta</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-850 text-slate-300">
                {simulating ? (
                  <tr>
                    <td colSpan={7} className="py-10 text-center text-xs text-slate-500">
                      Recalculating impact matrix...
                    </td>
                  </tr>
                ) : simResults && simResults.stockout_details.map((detail, index) => {
                  const delta = detail.simulated_lost_revenue - detail.base_lost_revenue;
                  return (
                    <tr 
                      key={index}
                      onClick={() => setSelectedKey(`${detail.product_id}::${detail.location}`)}
                      className={`hover:bg-slate-850/40 transition-colors cursor-pointer ${
                        selectedKey === `${detail.product_id}::${detail.location}` ? "bg-slate-850/20" : ""
                      }`}
                    >
                      <td className="py-3.5 px-4">
                        <div className="flex flex-col">
                          <span className="font-semibold text-white text-xs">{detail.product_name}</span>
                          <span className="text-[10px] text-slate-500 font-mono mt-0.5">{detail.product_id}</span>
                        </div>
                      </td>
                      <td className="py-3.5 px-4 font-medium text-xs">
                        {detail.location}
                      </td>
                      <td className="py-3.5 px-4 text-center text-xs font-semibold">
                        <span className={detail.base_days_to_stockout <= 30 ? "text-amber-400" : "text-emerald-400"}>
                          {detail.base_days_to_stockout <= 30 ? `Day ${detail.base_days_to_stockout}` : "Never"}
                        </span>
                      </td>
                      <td className="py-3.5 px-4 text-center text-xs font-bold">
                        <span className={detail.simulated_days_to_stockout <= 30 ? "text-rose-400" : "text-emerald-400"}>
                          {detail.simulated_days_to_stockout <= 30 ? `Day ${detail.simulated_days_to_stockout}` : "Never"}
                        </span>
                      </td>
                      <td className="py-3.5 px-4 text-right font-mono text-xs text-slate-400">
                        ${detail.base_lost_revenue.toFixed(2)}
                      </td>
                      <td className="py-3.5 px-4 text-right font-mono text-xs text-white">
                        ${detail.simulated_lost_revenue.toFixed(2)}
                      </td>
                      <td className={`py-3.5 px-4 text-right font-mono text-xs font-bold ${
                        delta > 0 ? "text-rose-450" : delta < 0 ? "text-emerald-400" : "text-slate-500"
                      }`}>
                        {delta > 0 ? "+" : ""}
                        ${delta.toFixed(2)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

      </main>
    </div>
  );
}
