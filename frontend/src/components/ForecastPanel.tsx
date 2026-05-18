"use client";

import { TrendingUp, TrendingDown, AlertTriangle } from "lucide-react";
import type { ForecastAlert } from "@/types";

interface ForecastPanelProps {
  alerts: ForecastAlert[];
}

function MapeBar({ value, threshold = 15 }: { value: number; threshold?: number }) {
  const pct = Math.min(100, value);
  const color =
    value > 25 ? "#f87171" : value > 15 ? "#fb923c" : "#34d399";

  return (
    <div className="relative">
      <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
        {/* Threshold marker */}
        <div
          className="absolute top-0 h-full w-0.5 bg-slate-500"
          style={{ left: `${threshold}%` }}
        />
      </div>
      <div className="flex justify-between mt-0.5">
        <span className="text-[10px] text-slate-600">0%</span>
        <span className="text-[10px] text-slate-600">threshold: {threshold}%</span>
        <span className="text-[10px] text-slate-600">50%</span>
      </div>
    </div>
  );
}

export function ForecastPanel({ alerts }: ForecastPanelProps) {
  return (
    <div className="card h-full flex flex-col">
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-violet-400" />
          <h2 className="text-sm font-semibold text-white">Forecast Health</h2>
        </div>
        <span className="badge-high">{alerts.length} above threshold</span>
      </div>

      <div className="flex-1 overflow-y-auto divide-y divide-slate-800/60">
        {alerts.map((alert) => (
          <div key={alert.product_id} className="px-4 py-3 hover:bg-slate-800/30 transition-colors">
            <div className="flex items-start justify-between gap-2 mb-2">
              <div>
                <p className="text-sm font-medium text-white">{alert.product_name}</p>
                <p className="text-xs text-slate-500">{alert.model_name} · {alert.run_date}</p>
              </div>
              <div className="text-right">
                <div className="flex items-center gap-1 justify-end">
                  <AlertTriangle className="w-3.5 h-3.5 text-orange-400" />
                  <span
                    className={`text-sm font-bold ${
                      alert.mape_pct > 25
                        ? "text-red-400"
                        : alert.mape_pct > 15
                        ? "text-orange-400"
                        : "text-emerald-400"
                    }`}
                  >
                    {alert.mape_pct}%
                  </span>
                </div>
                <p className="text-[10px] text-slate-500">MAPE</p>
              </div>
            </div>

            <MapeBar value={alert.mape_pct} />

            <p className="text-[11px] text-slate-500 mt-1.5 italic">{alert.notes}</p>

            <div className="flex items-center gap-3 mt-2 text-[10px] text-slate-600">
              {Object.entries(alert.hyperparameters).map(([k, v]) => (
                <span key={k}>
                  <span className="font-mono">{k}</span>={v}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
