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
} from "chart.js";
import { api } from "@/lib/api";

ChartJS.register(CategoryScale, LinearScale, BarElement, Tooltip, Legend);

type CategoryRow = {
  category: string;
  avg_capacity_pct: number;
  sku_count: number;
  at_risk: number;
};

const CATEGORY_COLORS: Record<string, { bg: string; border: string }> = {
  skincare:   { bg: "rgba(139, 92, 246, 0.7)",  border: "#7c3aed" },
  haircare:   { bg: "rgba(59, 130, 246, 0.7)",   border: "#2563eb" },
  cosmetics:  { bg: "rgba(236, 72, 153, 0.7)",   border: "#db2777" },
};

export function CategoryCapacityBarChart() {
  const [data, setData] = useState<CategoryRow[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getInventoryByCategoryChart()
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const labels = data.map((d) => d.category.charAt(0).toUpperCase() + d.category.slice(1));
  const values = data.map((d) => d.avg_capacity_pct);
  const bgColors = data.map((d) => CATEGORY_COLORS[d.category]?.bg ?? "rgba(100,116,139,0.7)");
  const borderColors = data.map((d) => CATEGORY_COLORS[d.category]?.border ?? "#64748b");

  const chartData = {
    labels,
    datasets: [
      {
        label: "Avg Capacity %",
        data: values,
        backgroundColor: bgColors,
        borderColor: borderColors,
        borderWidth: 1.5,
        borderRadius: 6,
        borderSkipped: false,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    indexAxis: "x" as const,
    scales: {
      y: {
        min: 0,
        max: 100,
        ticks: {
          color: "#64748b",
          font: { size: 11 },
          callback: (v: number | string) => `${v}%`,
        },
        grid: { color: "rgba(255,255,255,0.05)" },
        border: { color: "transparent" },
      },
      x: {
        ticks: { color: "#94a3b8", font: { size: 12 } },
        grid: { display: false },
        border: { color: "transparent" },
      },
    },
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (ctx: { raw: unknown; dataIndex: number }) => {
            const row = data[ctx.dataIndex];
            return [
              ` Avg Capacity: ${ctx.raw}%`,
              ` SKUs: ${row?.sku_count}`,
              ` At Risk: ${row?.at_risk}`,
            ];
          },
        },
      },
    },
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 flex flex-col shadow-xl">
      <div className="mb-4">
        <h3 className="text-sm font-semibold text-white">Inventory by Category</h3>
        <p className="text-xs text-slate-500 mt-0.5">Average capacity utilization per product line</p>
      </div>

      {/* Legend */}
      <div className="flex gap-4 mb-4">
        {data.map((d) => (
          <div key={d.category} className="flex items-center gap-1.5">
            <span
              className="w-2.5 h-2.5 rounded-sm"
              style={{ backgroundColor: CATEGORY_COLORS[d.category]?.bg }}
            />
            <span className="text-xs text-slate-400 capitalize">{d.category}</span>
            <span className="text-xs text-slate-600">({d.sku_count} SKUs)</span>
          </div>
        ))}
      </div>

      <div className="relative flex-1 h-52">
        {loading ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-7 h-7 border-2 border-fuchsia-500 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : (
          <Bar data={chartData} options={options} />
        )}
      </div>
    </div>
  );
}
