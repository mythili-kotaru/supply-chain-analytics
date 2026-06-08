"use client";

import { useEffect, useState } from "react";
import { Doughnut } from "react-chartjs-2";
import { Chart as ChartJS, ArcElement, Tooltip, Legend } from "chart.js";
import { api } from "@/lib/api";

ChartJS.register(ArcElement, Tooltip, Legend);

export function InventoryDonutChart() {
  const [data, setData] = useState<Record<string, number> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getInventoryHealthChart()
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const critical = data?.CRITICAL ?? 0;
  const low = data?.LOW ?? 0;
  const ok = data?.OK ?? 0;
  const total = critical + low + ok;

  const chartData = {
    labels: ["Critical", "Low Stock", "Healthy"],
    datasets: [
      {
        data: [critical, low, ok],
        backgroundColor: ["#ef4444", "#f59e0b", "#10b981"],
        borderColor: ["#991b1b", "#b45309", "#065f46"],
        borderWidth: 1.5,
        hoverOffset: 6,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    cutout: "68%",
    plugins: {
      legend: {
        position: "bottom" as const,
        labels: {
          color: "#94a3b8",
          font: { size: 11 },
          padding: 16,
          usePointStyle: true,
          pointStyleWidth: 8,
        },
      },
      tooltip: {
        callbacks: {
          label: (ctx: { label: string; raw: unknown }) =>
            ` ${ctx.label}: ${ctx.raw} SKUs`,
        },
      },
    },
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col shadow-xl">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-sm font-semibold text-white">Inventory Health</h3>
          <p className="text-xs text-slate-500 mt-0.5">{total} total SKUs across all locations</p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className="text-xs text-red-400 font-medium">{critical} Critical</span>
          <span className="text-xs text-amber-400 font-medium">{low} Low</span>
          <span className="text-xs text-emerald-400 font-medium">{ok} Healthy</span>
        </div>
      </div>
      <div className="relative flex-1 h-52">
        {loading ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-7 h-7 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <>
            <Doughnut data={chartData} options={options} />
            {/* Center label */}
            <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none" style={{ top: "-24px" }}>
              <span className="text-2xl font-bold text-white">{total}</span>
              <span className="text-[10px] text-slate-500">SKUs</span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
