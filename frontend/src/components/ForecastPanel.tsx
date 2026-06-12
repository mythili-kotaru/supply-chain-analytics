"use client";

import { TrendingUp, AlertTriangle, Zap } from "lucide-react";

const TrendingUpIcon = TrendingUp as any;
const AlertTriangleIcon = AlertTriangle as any;
const ZapIcon = Zap as any;

import type { ForecastAlert } from "@/types";

interface ForecastPanelProps {
  alerts: ForecastAlert[];
}

const MAPE_THRESHOLD = 15;

function mapeColor(mape: number) {
  if (mape > 25) return { bar: "#f87171", text: "text-red-400",     label: "CRITICAL" };
  if (mape > 15) return { bar: "#fb923c", text: "text-orange-400",  label: "HIGH"     };
  return           { bar: "#34d399", text: "text-emerald-400", label: "OK"       };
}

function MapeBar({ value }: { value: number }) {
  const pct       = Math.min(100, (value / 50) * 100);
  const threshPct = (MAPE_THRESHOLD / 50) * 100;
  const meta      = mapeColor(value);

  return (
    <div className="mt-2 mb-1">
      <div className="relative h-2 bg-slate-800 rounded-full">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: meta.bar }}
        />
        {/* Threshold tick — bright white so it's visible against any bar color */}
        <div
          className="absolute -top-0.5 h-3 w-0.5 bg-white/50 rounded-full"
          style={{ left: `${threshPct}%` }}
        />
      </div>
      <div className="flex justify-between mt-0.5 text-[9px] text-slate-600">
        <span>0%</span>
        <span className="text-slate-500">▲ {MAPE_THRESHOLD}% threshold</span>
        <span>50%</span>
      </div>
    </div>
  );
}

import Link from "next/link";
const LinkComponent = Link as any;

export function ForecastPanel({ alerts }: ForecastPanelProps) {
  const criticalCount = alerts.filter((a) => a.mape_pct > 25).length;

  return (
    <div className="card h-full flex flex-col relative group">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <TrendingUpIcon className="w-4 h-4 text-violet-400" />
          <h2 className="text-sm font-semibold text-white">Forecast Health</h2>
        </div>
        <div className="flex items-center gap-3">
          <span className={criticalCount > 0 ? "badge-critical" : "badge-high"}>
            {alerts.length} above threshold
          </span>
          <LinkComponent 
            href="/forecasting"
            className="text-xs text-violet-400 hover:text-violet-300 font-medium opacity-0 group-hover:opacity-100 transition-opacity"
          >
            View Models &rarr;
          </LinkComponent>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto divide-y divide-slate-800/60">
        {alerts.length === 0 ? (
          <div className="flex items-center justify-center h-full gap-2 text-slate-500 text-sm">
            <ZapIcon className="w-4 h-4 text-emerald-400" />
            All models within threshold
          </div>
        ) : (
          alerts.map((alert) => {
            const meta = mapeColor(alert.mape_pct);
            return (
              <div key={alert.product_id} className="px-4 py-3 hover:bg-slate-800/30 transition-colors">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-white truncate">{alert.product_name}</p>
                    <p className="text-[10px] text-slate-500 mt-0.5">
                      {alert.model_name} · {alert.run_date}
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    <div className="flex items-center gap-1 justify-end">
                      <AlertTriangleIcon className={`w-3 h-3 ${meta.text}`} />
                      <span className={`text-base font-bold tabular-nums ${meta.text}`}>
                        {alert.mape_pct}%
                      </span>
                    </div>
                    <span className={`text-[9px] font-semibold ${meta.text} opacity-70`}>
                      {meta.label}
                    </span>
                  </div>
                </div>

                <MapeBar value={alert.mape_pct} />

                <p className="text-[10px] text-slate-500 italic mt-1 leading-relaxed">{alert.notes}</p>

                {alert.hyperparameters && Object.keys(alert.hyperparameters).length > 0 && (
                  <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1.5">
                    {Object.entries(alert.hyperparameters).map(([k, v]) => (
                      <span key={k} className="text-[9px] text-slate-600 font-mono">
                        {k}=<span className="text-slate-500">{String(v)}</span>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
