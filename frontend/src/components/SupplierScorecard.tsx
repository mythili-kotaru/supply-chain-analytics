"use client";

import { useEffect, useState } from "react";
import { Bar } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
  Legend,
  PointElement,
  LineElement,
} from "chart.js";
import { Shield, AlertTriangle, Award, Clock, DollarSign, Activity, Percent, ArrowRight } from "lucide-react";

const ShieldIcon = Shield as any;
const AlertTriangleIcon = AlertTriangle as any;
const AwardIcon = Award as any;
const ClockIcon = Clock as any;
const DollarSignIcon = DollarSign as any;
const ActivityIcon = Activity as any;
const PercentIcon = Percent as any;
const ArrowRightIcon = ArrowRight as any;

import { api } from "@/lib/api";
import type { SupplierScorecardItem } from "@/types";

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend, PointElement, LineElement);

export function SupplierScorecard() {
  const [scorecard, setScorecard] = useState<SupplierScorecardItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedSupplier, setSelectedSupplier] = useState<SupplierScorecardItem | null>(null);

  useEffect(() => {
    api.getSourcingScorecard()
      .then((data) => {
        setScorecard(data);
        if (data.length > 0) {
          setSelectedSupplier(data[0]);
        }
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const getRiskBadge = (score: number) => {
    if (score < 15) {
      return (
        <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
          Low Risk ({score.toFixed(1)})
        </span>
      );
    }
    if (score < 30) {
      return (
        <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-500/10 border border-amber-500/30 text-amber-400">
          Medium Risk ({score.toFixed(1)})
        </span>
      );
    }
    return (
      <span className="px-2.5 py-1 rounded-full text-xs font-semibold bg-red-500/15 border border-red-500/30 text-red-400 shadow-[0_0_12px_rgba(239,68,68,0.2)]">
        High Risk ({score.toFixed(1)})
      </span>
    );
  };

  // ── Lead Time Drift Chart Data ───────────────────────────────────────
  const leadTimeData = {
    labels: scorecard.map((s) => s.supplier_name.split(" ")[0]),
    datasets: [
      {
        label: "Declared Lead Time (Days)",
        data: scorecard.map((s) => s.default_lead_time),
        backgroundColor: "rgba(59, 130, 246, 0.4)",
        borderColor: "rgba(59, 130, 246, 0.9)",
        borderWidth: 1.5,
        borderRadius: 4,
      },
      {
        label: "Actual Avg Lead Time (Days)",
        data: scorecard.map((s) => s.avg_delivery_days ?? s.default_lead_time),
        backgroundColor: "rgba(139, 92, 246, 0.6)",
        borderColor: "rgba(139, 92, 246, 0.9)",
        borderWidth: 1.5,
        borderRadius: 4,
      },
    ],
  };

  const leadTimeOptions = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      y: {
        grid: { color: "rgba(255, 255, 255, 0.05)" },
        ticks: { color: "#94a3b8" },
        border: { color: "transparent" },
      },
      x: {
        grid: { display: false },
        ticks: { color: "#94a3b8" },
        border: { color: "transparent" },
      },
    },
    plugins: {
      legend: {
        position: "top" as const,
        labels: { color: "#94a3b8", boxWidth: 12 },
      },
    },
  };

  // ── Cost Comparison Chart Data ────────────────────────────────────────
  const costData = {
    labels: scorecard.map((s) => s.supplier_name.split(" ")[0]),
    datasets: [
      {
        label: "Manufacturing Cost ($/unit)",
        data: scorecard.map((s) => s.avg_unit_manufacturing_cost ?? 0),
        backgroundColor: "rgba(236, 72, 153, 0.6)",
        borderColor: "rgba(236, 72, 153, 0.9)",
        borderWidth: 1.5,
        borderRadius: 4,
      },
      {
        label: "Shipping Cost ($/unit)",
        data: scorecard.map((s) => s.avg_unit_shipping_cost ?? 0),
        backgroundColor: "rgba(34, 211, 238, 0.6)",
        borderColor: "rgba(34, 211, 238, 0.9)",
        borderWidth: 1.5,
        borderRadius: 4,
      },
    ],
  };

  const costOptions = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      y: {
        grid: { color: "rgba(255, 255, 255, 0.05)" },
        ticks: {
          color: "#94a3b8",
          callback: (v: any) => `$${v}`,
        },
        border: { color: "transparent" },
      },
      x: {
        grid: { display: false },
        ticks: { color: "#94a3b8" },
        border: { color: "transparent" },
      },
    },
    plugins: {
      legend: {
        position: "top" as const,
        labels: { color: "#94a3b8", boxWidth: 12 },
      },
    },
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Overview Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Supplier List Sidepanel */}
        <div className="card p-4 flex flex-col h-[520px]">
          <h3 className="text-sm font-semibold text-white mb-3">Suppliers Directory</h3>
          <div className="flex-1 overflow-y-auto space-y-2 pr-1">
            {scorecard.map((s) => {
              const isSelected = selectedSupplier?.supplier_id === s.supplier_id;
              return (
                <button
                  key={s.supplier_id}
                  onClick={() => setSelectedSupplier(s)}
                  className={`w-full text-left p-3.5 rounded-lg border transition-all duration-200 ${
                    isSelected
                      ? "bg-slate-800/80 border-blue-500/50 shadow-md shadow-blue-500/5"
                      : "bg-slate-900/40 border-slate-850 hover:bg-slate-800/30 hover:border-slate-700"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-semibold text-slate-200 truncate">{s.supplier_name}</p>
                      <p className="text-xs text-slate-500 font-mono mt-0.5">{s.supplier_id} • {s.location}</p>
                    </div>
                    {getRiskBadge(s.risk_score)}
                  </div>
                  <div className="grid grid-cols-2 gap-2 mt-3 text-[11px] text-slate-400 border-t border-slate-800/60 pt-2.5">
                    <div>
                      <span className="block text-slate-500">On-Time Pct</span>
                      <span className="font-medium text-slate-300">
                        {s.on_time_delivery_pct !== null ? `${s.on_time_delivery_pct}%` : "N/A"}
                      </span>
                    </div>
                    <div>
                      <span className="block text-slate-500">Avg Lead Drift</span>
                      <span className={`font-medium ${
                        (s.avg_lead_time_drift ?? 0) > 2 ? "text-red-400" :
                        (s.avg_lead_time_drift ?? 0) > 0 ? "text-amber-400" : "text-emerald-400"
                      }`}>
                        {s.avg_lead_time_drift !== null ? `${s.avg_lead_time_drift > 0 ? "+" : ""}${s.avg_lead_time_drift}d` : "0d"}
                      </span>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Selected Supplier Detailed Scorecard */}
        {selectedSupplier && (
          <div className="card p-6 lg:col-span-2 flex flex-col h-[520px] justify-between relative overflow-hidden">
            <div className="absolute inset-0 bg-gradient-to-br from-blue-500/5 via-transparent to-transparent pointer-events-none" />
            <div>
              {/* Header */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
                <div>
                  <h2 className="text-xl font-bold text-white flex items-center gap-2">
                    <AwardIcon className="w-5 h-5 text-yellow-400" />
                    {selectedSupplier.supplier_name}
                  </h2>
                  <p className="text-sm text-slate-400 mt-0.5">
                    Supplier score card summary and optimization weights
                  </p>
                </div>
                <div className="flex flex-col items-end gap-1.5">
                  <span className="text-[10px] text-slate-500 font-mono">SUPPLIER RISK CATEGORY</span>
                  {getRiskBadge(selectedSupplier.risk_score)}
                </div>
              </div>

              {/* Stats Grid */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-6">
                <div className="bg-slate-950/40 border border-slate-800/80 p-3.5 rounded-lg">
                  <span className="text-xs text-slate-500 block mb-1">On-Time Delivery</span>
                  <div className="flex items-center gap-1.5">
                    <PercentIcon className="w-4 h-4 text-emerald-400" />
                    <span className="text-lg font-bold text-white">
                      {selectedSupplier.on_time_delivery_pct !== null ? `${selectedSupplier.on_time_delivery_pct}%` : "100.0%"}
                    </span>
                  </div>
                </div>

                <div className="bg-slate-950/40 border border-slate-800/80 p-3.5 rounded-lg">
                  <span className="text-xs text-slate-500 block mb-1">Fulfillment Latency</span>
                  <div className="flex items-center gap-1.5">
                    <ClockIcon className="w-4 h-4 text-violet-400" />
                    <span className="text-lg font-bold text-white">
                      {selectedSupplier.avg_delivery_days !== null ? `${selectedSupplier.avg_delivery_days}d` : `${selectedSupplier.default_lead_time}d`}
                    </span>
                  </div>
                </div>

                <div className="bg-slate-950/40 border border-slate-800/80 p-3.5 rounded-lg">
                  <span className="text-xs text-slate-500 block mb-1">Defect Rate (Declared)</span>
                  <div className="flex items-center gap-1.5">
                    <AlertTriangleIcon className="w-4 h-4 text-orange-400" />
                    <span className="text-lg font-bold text-white">
                      {(selectedSupplier.declared_defect_rate * 100).toFixed(2)}%
                    </span>
                  </div>
                </div>

                <div className="bg-slate-950/40 border border-slate-800/80 p-3.5 rounded-lg">
                  <span className="text-xs text-slate-500 block mb-1">Total History Orders</span>
                  <div className="flex items-center gap-1.5">
                    <ActivityIcon className="w-4 h-4 text-blue-400" />
                    <span className="text-lg font-bold text-white">
                      {selectedSupplier.total_orders} orders
                    </span>
                  </div>
                </div>
              </div>

              {/* Dynamic Cost breakdown */}
              <div className="mt-6 space-y-3.5">
                <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">Unit Cost Breakdown</h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="flex items-center justify-between p-3.5 bg-slate-950/20 border border-slate-900 rounded-lg">
                    <div className="flex items-center gap-2">
                      <DollarSignIcon className="w-4 h-4 text-pink-400" />
                      <span className="text-sm text-slate-300">Manufacturing Cost</span>
                    </div>
                    <span className="text-base font-bold text-slate-200">
                      {selectedSupplier.avg_unit_manufacturing_cost !== null ? `$${selectedSupplier.avg_unit_manufacturing_cost.toFixed(2)}` : "N/A"}
                    </span>
                  </div>
                  <div className="flex items-center justify-between p-3.5 bg-slate-950/20 border border-slate-900 rounded-lg">
                    <div className="flex items-center gap-2">
                      <DollarSignIcon className="w-4 h-4 text-cyan-400" />
                      <span className="text-sm text-slate-300">Avg Shipping Cost</span>
                    </div>
                    <span className="text-base font-bold text-slate-200">
                      {selectedSupplier.avg_unit_shipping_cost !== null ? `$${selectedSupplier.avg_unit_shipping_cost.toFixed(2)}` : "N/A"}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Sourcing Splitting Optimizer Strategy Details */}
            <div className="bg-blue-950/15 border border-blue-500/10 rounded-lg p-4 mt-6">
              <div className="flex gap-2">
                <ShieldIcon className="w-4 h-4 text-blue-400 shrink-0 mt-0.5" />
                <div>
                  <h4 className="text-xs font-bold text-blue-300 uppercase tracking-wider">Replenishment Sourcing Policy</h4>
                  <p className="text-[11px] text-slate-400 mt-1">
                    When order quantities exceed **150 units**, the Multi-Criteria Sourcing Node automatically splits purchase order distribution to hedge risk:
                  </p>
                  <div className="flex items-center gap-3 mt-3">
                    <div className="flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                      <span className="text-[10px] text-slate-300 font-medium">70% to Primary ({selectedSupplier.supplier_id === scorecard[0]?.supplier_id ? "This Supplier" : scorecard[0]?.supplier_name.split(" ")[0]})</span>
                    </div>
                    <ArrowRightIcon className="w-3 h-3 text-slate-600" />
                    <div className="flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
                      <span className="text-[10px] text-slate-300 font-medium">30% to Backup (Fastest Delivery)</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Visual Analytics Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Lead time comparison */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col shadow-xl">
          <div>
            <h3 className="text-sm font-semibold text-white">Lead Time & Drift Analysis</h3>
            <p className="text-xs text-slate-500 mt-0.5">Declared lead times vs real actual delivery duration averages (Days)</p>
          </div>
          <div className="relative flex-1 h-64 mt-4">
            <Bar data={leadTimeData} options={leadTimeOptions} />
          </div>
        </div>

        {/* Cost comparison */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col shadow-xl">
          <div>
            <h3 className="text-sm font-semibold text-white">Supplier Cost Efficiency Benchmarks</h3>
            <p className="text-xs text-slate-500 mt-0.5">Comparison of average manufacturing and transport shipping charges per unit</p>
          </div>
          <div className="relative flex-1 h-64 mt-4">
            <Bar data={costData} options={costOptions} />
          </div>
        </div>
      </div>
    </div>
  );
}
