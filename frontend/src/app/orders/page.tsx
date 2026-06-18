"use client";

import { useState, useEffect, useMemo } from "react";
import { Navbar } from "@/components/Navbar";
import { api } from "@/lib/api";
import type { DashboardStats, Proposal } from "@/types";
import { ShoppingCart, ArrowRightLeft, Truck, CheckCircle2, Clock } from "lucide-react";

const ShoppingCartIcon = ShoppingCart as any;
const ArrowRightLeftIcon = ArrowRightLeft as any;
const TruckIcon = Truck as any;
const CheckCircle2Icon = CheckCircle2 as any;
const ClockIcon = Clock as any;

const EMPTY_STATS: DashboardStats = {
  critical_alerts: 0,
  pending_approvals: 0,
  approved_today: 0,
  po_value_pending: 0,
  avg_mape: 0,
  services: [],
};

export default function OrdersPage() {
  const [stats, setStats] = useState<DashboardStats>(EMPTY_STATS);
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.getStats(),
      api.getProposals("approved"),
    ])
      .then(([statsData, proposalsData]) => {
        setStats(statsData);
        setProposals(proposalsData);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const { replenishments, allocations } = useMemo(() => {
    return {
      replenishments: proposals.filter(p => p.type === "replenishment" && p.replenishment),
      allocations: proposals.filter(p => p.type === "allocation" && p.allocation)
    };
  }, [proposals]);

  const totalInTransitValue = useMemo(() => {
    return replenishments.reduce((acc, p) => acc + (p.replenishment?.total_order_value || 0), 0);
  }, [replenishments]);

  const totalTransfers = useMemo(() => {
    return allocations.reduce((acc, p) => acc + ((p.allocation as any)?.total_units_transferred || (p.allocation as any)?.total_units || 0), 0);
  }, [allocations]);

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col">
      <Navbar stats={stats} />

      <main className="flex-1 p-4 md:p-6 max-w-[1400px] mx-auto w-full space-y-8">
        
        {/* Header Section */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <ShoppingCartIcon className="w-6 h-6 text-sky-400" />
              Active Orders & Transfers
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              Historical ledger of AI-approved purchase orders and inventory allocations in transit.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="bg-slate-900 border border-slate-800 rounded-lg px-4 py-2 flex items-center gap-3">
              <span className="text-sm text-slate-400">Total In Transit Value:</span>
              <span className="text-lg font-bold text-emerald-400">
                ${totalInTransitValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </span>
            </div>
            <div className="bg-sky-500/10 border border-sky-500/20 rounded-lg px-4 py-2 flex items-center gap-3">
              <span className="text-sm text-sky-400">Units Transferring:</span>
              <span className="text-lg font-bold text-sky-400">{totalTransfers}</span>
            </div>
          </div>
        </div>

        {/* Purchase Orders Section */}
        <div className="space-y-4">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <TruckIcon className="w-5 h-5 text-emerald-500" />
            Purchase Orders (Replenishments)
          </h2>
          
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl min-h-[200px] relative">
            {loading ? (
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : replenishments.length === 0 ? (
              <div className="absolute inset-0 flex items-center justify-center text-slate-500 text-sm">
                No active purchase orders found.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm whitespace-nowrap">
                  <thead className="bg-slate-950/50 text-slate-400 border-b border-slate-800">
                    <tr>
                      <th className="px-6 py-4 font-medium">Status</th>
                      <th className="px-6 py-4 font-medium">PO Details</th>
                      <th className="px-6 py-4 font-medium">Product</th>
                      <th className="px-6 py-4 font-medium">Supplier</th>
                      <th className="px-6 py-4 font-medium">Quantity</th>
                      <th className="px-6 py-4 font-medium text-right">Value</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/50">
                    {replenishments.flatMap(p => 
                      (p.replenishment?.purchase_orders || []).map((po, idx) => (
                        <tr key={`${p.id}-${idx}`} className="hover:bg-slate-800/20 transition-colors">
                          <td className="px-6 py-4">
                            <div className="flex items-center gap-1.5 text-emerald-400 bg-emerald-400/10 px-2.5 py-1 rounded-full w-max text-xs font-medium border border-emerald-400/20">
                              <CheckCircle2Icon className="w-3.5 h-3.5" />
                              Approved
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            <p className="font-mono text-slate-300 font-semibold">{po.po_number}</p>
                            {po.jira_ticket_key && (
                              <a
                                href={`http://localhost:8003/api/dashboard/jira/browse/${po.jira_ticket_key}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-xs text-sky-400 hover:text-sky-300 hover:underline flex items-center gap-1 mt-1 font-mono w-max"
                              >
                                🎫 {po.jira_ticket_key}
                              </a>
                            )}
                            <p className="text-xs text-slate-500 mt-1 flex items-center gap-1">
                              <ClockIcon className="w-3 h-3" />
                              ETA: {po.expected_delivery} ({po.lead_time_days} days)
                            </p>
                          </td>
                          <td className="px-6 py-4">
                            <p className="font-medium text-slate-200">{po.product_name}</p>
                            <p className="text-xs text-slate-500 font-mono mt-0.5">{po.product_id}</p>
                          </td>
                          <td className="px-6 py-4 text-slate-300">
                            {po.supplier_name}
                          </td>
                          <td className="px-6 py-4 text-slate-300">
                            {po.order_quantity} units
                          </td>
                          <td className="px-6 py-4 text-right font-medium text-emerald-400">
                            ${po.order_value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Transfers Section */}
        <div className="space-y-4 pt-4">
          <h2 className="text-lg font-semibold text-white flex items-center gap-2">
            <ArrowRightLeftIcon className="w-5 h-5 text-sky-500" />
            Inter-Warehouse Transfers (Allocations)
          </h2>
          
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl min-h-[200px] relative">
            {loading ? (
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="w-8 h-8 border-2 border-sky-500 border-t-transparent rounded-full animate-spin" />
              </div>
            ) : allocations.length === 0 ? (
              <div className="absolute inset-0 flex items-center justify-center text-slate-500 text-sm">
                No active transfers found.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm whitespace-nowrap">
                  <thead className="bg-slate-950/50 text-slate-400 border-b border-slate-800">
                    <tr>
                      <th className="px-6 py-4 font-medium">Status</th>
                      <th className="px-6 py-4 font-medium">Product</th>
                      <th className="px-6 py-4 font-medium">Route</th>
                      <th className="px-6 py-4 font-medium">Quantity</th>
                      <th className="px-6 py-4 font-medium">Rationale</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/50">
                    {allocations.flatMap(p => 
                      ((p.allocation as any)?.transfers || (p.allocation as any)?.allocation_plan || []).map((transfer: any, idx: number) => (
                        <tr key={`${p.id}-${idx}`} className="hover:bg-slate-800/20 transition-colors">
                          <td className="px-6 py-4">
                            <div className="flex items-center gap-1.5 text-sky-400 bg-sky-400/10 px-2.5 py-1 rounded-full w-max text-xs font-medium border border-sky-400/20">
                              <TruckIcon className="w-3.5 h-3.5" />
                              In Transit
                            </div>
                          </td>
                          <td className="px-6 py-4">
                            <p className="font-medium text-slate-200">{transfer.product_name || p.trigger.product_name}</p>
                            <p className="text-xs text-slate-500 font-mono mt-0.5">{transfer.product_id || p.trigger.product_id}</p>
                          </td>
                          <td className="px-6 py-4">
                            <div className="flex items-center gap-2">
                              <span className="text-slate-300 bg-slate-800 px-2 py-1 rounded text-xs">
                                {transfer.from_location}
                              </span>
                              <ArrowRightLeftIcon className="w-3 h-3 text-slate-500" />
                              <span className="text-slate-300 bg-slate-800 px-2 py-1 rounded text-xs">
                                {transfer.to_location}
                              </span>
                            </div>
                          </td>
                          <td className="px-6 py-4 font-medium text-sky-400">
                            {transfer.transfer_quantity} units
                          </td>
                          <td className="px-6 py-4">
                            <p className="text-slate-400 text-xs truncate max-w-sm" title={transfer.reason}>
                              {transfer.reason}
                            </p>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

      </main>
    </div>
  );
}
