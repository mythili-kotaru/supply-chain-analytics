"use client";

import { Package, MapPin, TrendingDown } from "lucide-react";
import type { InventoryAlert } from "@/types";

interface InventoryAlertsFeedProps {
  alerts: InventoryAlert[];
}

const CATEGORY_COLORS: Record<string, string> = {
  skincare: "text-pink-400 bg-pink-500/10",
  haircare: "text-purple-400 bg-purple-500/10",
  cosmetics: "text-amber-400 bg-amber-500/10",
};

export function InventoryAlertsFeed({ alerts }: InventoryAlertsFeedProps) {
  return (
    <div className="card flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-red-400 live-dot" />
          <h2 className="text-sm font-semibold text-white">Inventory Alerts</h2>
          <span className="text-xs text-slate-500">live</span>
        </div>
        <span className="badge-critical">{alerts.filter((a) => a.status === "CRITICAL").length} critical</span>
      </div>

      {/* Alert list */}
      <div className="flex-1 overflow-y-auto divide-y divide-slate-800/60">
        {alerts.map((alert) => {
          const deficitPct = Math.abs(
            ((alert.reorder_point - alert.stock_level) / alert.reorder_point) * 100
          ).toFixed(0);

          return (
            <div key={`${alert.product_id}-${alert.location}`} className="px-4 py-3 hover:bg-slate-800/30 transition-colors slide-in">
              <div className="flex items-start justify-between gap-3">
                {/* Left */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${CATEGORY_COLORS[alert.category] ?? "text-slate-400 bg-slate-700"}`}>
                      {alert.category}
                    </span>
                    <span className={alert.status === "CRITICAL" ? "badge-critical" : "badge-low"}>
                      {alert.status}
                    </span>
                  </div>
                  <p className="text-sm font-medium text-white truncate">{alert.product_name}</p>
                  <div className="flex items-center gap-3 mt-1 text-xs text-slate-400">
                    <span className="flex items-center gap-1">
                      <MapPin className="w-3 h-3" />
                      {alert.location}
                    </span>
                    <span className="flex items-center gap-1 text-slate-500">
                      <Package className="w-3 h-3" />
                      {alert.product_id}
                    </span>
                  </div>
                </div>

                {/* Right — stock gauge */}
                <div className="text-right shrink-0">
                  <p className="text-xs text-slate-500">stock / reorder</p>
                  <p className="text-sm font-bold text-white">
                    {alert.stock_level}
                    <span className="text-slate-500 font-normal"> / {alert.reorder_point}</span>
                  </p>
                  <div className="flex items-center gap-1 justify-end mt-0.5">
                    <TrendingDown className="w-3 h-3 text-red-400" />
                    <span className="text-xs text-red-400 font-medium">{deficitPct}% deficit</span>
                  </div>
                </div>
              </div>

              {/* Stock bar */}
              <div className="mt-2.5">
                <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${Math.min(100, alert.capacity_pct)}%`,
                      backgroundColor:
                        alert.status === "CRITICAL"
                          ? "#f87171"
                          : alert.status === "LOW"
                          ? "#fb923c"
                          : "#34d399",
                    }}
                  />
                </div>
                <div className="flex justify-between mt-0.5">
                  <span className="text-[10px] text-slate-600">0</span>
                  <span className="text-[10px] text-slate-600">
                    reorder: {alert.reorder_point}
                  </span>
                  <span className="text-[10px] text-slate-600">{alert.max_capacity}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
