"use client";

import { Package, MapPin, TrendingDown, AlertTriangle } from "lucide-react";

const PackageIcon = Package as any;
const MapPinIcon = MapPin as any;
const TrendingDownIcon = TrendingDown as any;
const AlertTriangleIcon = AlertTriangle as any;

import type { InventoryAlert } from "@/types";

interface InventoryAlertsFeedProps {
  alerts: InventoryAlert[];
}

const CATEGORY_COLORS: Record<string, string> = {
  skincare:  "text-pink-400 bg-pink-500/10 border border-pink-500/20",
  haircare:  "text-purple-400 bg-purple-500/10 border border-purple-500/20",
  cosmetics: "text-amber-400 bg-amber-500/10 border border-amber-500/20",
};

function StockBar({ stockLevel, reorderPoint, maxCapacity, status }: {
  stockLevel: number;
  reorderPoint: number;
  maxCapacity: number;
  status: string;
}) {
  const stockPct   = Math.min(100, (stockLevel / maxCapacity) * 100);
  const reorderPct = Math.min(100, (reorderPoint / maxCapacity) * 100);
  const barColor   =
    status === "CRITICAL" ? "#f87171" :
    status === "LOW"      ? "#fb923c" :
                            "#34d399";

  return (
    <div className="mt-2.5">
      <div className="relative h-1.5 bg-slate-800 rounded-full">
        {/* Stock fill */}
        <div
          className="absolute top-0 left-0 h-full rounded-full transition-all duration-500"
          style={{ width: `${stockPct}%`, backgroundColor: barColor }}
        />
        {/* Reorder point tick — sits above the bar */}
        <div
          className="absolute -top-1 h-3.5 w-0.5 bg-slate-400 rounded-full"
          style={{ left: `${reorderPct}%` }}
        />
      </div>
      <div className="flex justify-between mt-1">
        <span className="text-[9px] text-slate-600">0</span>
        <span className="text-[9px] text-slate-500">↑ reorder: {reorderPoint}</span>
        <span className="text-[9px] text-slate-600">{maxCapacity}</span>
      </div>
    </div>
  );
}

export function InventoryAlertsFeed({ alerts }: InventoryAlertsFeedProps) {
  const criticalCount = alerts.filter((a) => a.status === "CRITICAL").length;

  return (
    <div className="card flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-red-400 live-dot shrink-0" />
          <h2 className="text-sm font-semibold text-white">Inventory Alerts</h2>
          <span className="text-xs text-slate-500">live</span>
        </div>
        {criticalCount > 0 ? (
          <span className="badge-critical flex items-center gap-1">
            <AlertTriangleIcon className="w-3 h-3" />
            {criticalCount} critical
          </span>
        ) : (
          <span className="badge-ok">{alerts.length} monitored</span>
        )}
      </div>

      {/* Alert list */}
      <div className="flex-1 overflow-y-auto divide-y divide-slate-800/60">
        {alerts.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <p className="text-slate-500 text-sm">No active alerts</p>
          </div>
        ) : (
          alerts.map((alert) => {
            const deficitPct = Math.round(
              ((alert.reorder_point - alert.stock_level) / alert.reorder_point) * 100
            );

            return (
              <div
                key={`${alert.product_id}-${alert.location}`}
                className={`px-4 py-3 transition-colors slide-in ${
                  alert.status === "CRITICAL" ? "hover:bg-red-950/20" : "hover:bg-slate-800/30"
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 mb-1 flex-wrap">
                      <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-md ${
                        CATEGORY_COLORS[alert.category] ?? "text-slate-400 bg-slate-700 border border-slate-600"
                      }`}>
                        {alert.category}
                      </span>
                      <span className={alert.status === "CRITICAL" ? "badge-critical" : "badge-low"}>
                        {alert.status}
                      </span>
                    </div>
                    <p className="text-sm font-semibold text-white truncate">{alert.product_name}</p>
                    <div className="flex items-center gap-3 mt-0.5 text-xs text-slate-400">
                      <span className="flex items-center gap-1">
                        <MapPinIcon className="w-3 h-3" />
                        {alert.location}
                      </span>
                      <span className="flex items-center gap-1 text-slate-600">
                        <PackageIcon className="w-3 h-3" />
                        {alert.product_id}
                      </span>
                    </div>
                  </div>

                  <div className="text-right shrink-0">
                    <p className="text-[10px] text-slate-500 mb-0.5">stock / reorder</p>
                    <p className="text-sm font-bold text-white tabular-nums">
                      {alert.stock_level}
                      <span className="text-slate-500 font-normal"> / {alert.reorder_point}</span>
                    </p>
                    <div className="flex items-center gap-1 justify-end mt-0.5">
                      <TrendingDownIcon className="w-3 h-3 text-red-400" />
                      <span className={`text-xs font-semibold ${
                        deficitPct > 60 ? "text-red-400" : "text-orange-400"
                      }`}>
                        {deficitPct}% deficit
                      </span>
                    </div>
                  </div>
                </div>

                <StockBar
                  stockLevel={alert.stock_level}
                  reorderPoint={alert.reorder_point}
                  maxCapacity={alert.max_capacity}
                  status={alert.status}
                />
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
