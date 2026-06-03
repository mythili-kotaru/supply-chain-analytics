"use client";

import { useState, useEffect, useMemo } from "react";
import { Navbar } from "@/components/Navbar";
import { api } from "@/lib/api";
import type { DashboardStats, InventoryAlert } from "@/types";
import { Search, Filter, Box, Package, AlertTriangle, CheckCircle2 } from "lucide-react";

const EMPTY_STATS: DashboardStats = {
  critical_alerts: 0,
  pending_approvals: 0,
  approved_today: 0,
  po_value_pending: 0,
  avg_mape: 0,
  services: [],
};

export default function InventoryPage() {
  const [stats, setStats] = useState<DashboardStats>(EMPTY_STATS);
  const [inventory, setInventory] = useState<InventoryAlert[]>([]);
  const [loading, setLoading] = useState(true);

  // Filters
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("All");
  const [locationFilter, setLocationFilter] = useState("All");
  const [statusFilter, setStatusFilter] = useState("All");

  useEffect(() => {
    Promise.all([api.getStats(), api.getInventoryAll()])
      .then(([statsData, inventoryData]) => {
        setStats(statsData);
        setInventory(inventoryData);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const categories = ["All", ...Array.from(new Set(inventory.map((i) => i.category)))];
  const locations = ["All", ...Array.from(new Set(inventory.map((i) => i.location)))];
  const statuses = ["All", "CRITICAL", "LOW", "OK"];

  const filteredInventory = useMemo(() => {
    return inventory.filter((item) => {
      const matchSearch =
        item.product_name.toLowerCase().includes(search.toLowerCase()) ||
        item.product_id.toLowerCase().includes(search.toLowerCase());
      const matchCategory = categoryFilter === "All" || item.category === categoryFilter;
      const matchLocation = locationFilter === "All" || item.location === locationFilter;
      const matchStatus = statusFilter === "All" || item.status === statusFilter;
      return matchSearch && matchCategory && matchLocation && matchStatus;
    });
  }, [inventory, search, categoryFilter, locationFilter, statusFilter]);

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col">
      <Navbar stats={stats} />

      <main className="flex-1 p-4 md:p-6 max-w-[1400px] mx-auto w-full space-y-6">
        
        {/* Header Section */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <Package className="w-6 h-6 text-indigo-400" />
              Global Inventory
            </h1>
            <p className="text-slate-400 text-sm mt-1">
              Live ledger of all products across distribution centers.
            </p>
          </div>

          <div className="flex items-center gap-3">
            <div className="bg-slate-900 border border-slate-800 rounded-lg px-4 py-2 flex items-center gap-3">
              <span className="text-sm text-slate-400">Total SKUs:</span>
              <span className="text-lg font-bold text-white">{inventory.length}</span>
            </div>
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg px-4 py-2 flex items-center gap-3">
              <span className="text-sm text-red-400">At Risk:</span>
              <span className="text-lg font-bold text-red-400">
                {inventory.filter(i => i.status !== 'OK').length}
              </span>
            </div>
          </div>
        </div>

        {/* Filters Bar */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col lg:flex-row gap-4 items-center justify-between shadow-lg">
          
          <div className="relative w-full lg:w-96">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
            <input
              type="text"
              placeholder="Search by product name or ID..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-10 pr-4 py-2 bg-slate-950 border border-slate-800 rounded-lg text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/50 transition-all"
            />
          </div>

          <div className="flex flex-wrap items-center gap-3 w-full lg:w-auto">
            <Filter className="w-4 h-4 text-slate-500 hidden sm:block" />
            
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="bg-slate-950 border border-slate-800 text-slate-300 text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            >
              {categories.map((c) => (
                <option key={c} value={c}>{c === "All" ? "All Categories" : c}</option>
              ))}
            </select>

            <select
              value={locationFilter}
              onChange={(e) => setLocationFilter(e.target.value)}
              className="bg-slate-950 border border-slate-800 text-slate-300 text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            >
              {locations.map((l) => (
                <option key={l} value={l}>{l === "All" ? "All Regions" : l}</option>
              ))}
            </select>

            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-slate-950 border border-slate-800 text-slate-300 text-sm rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
            >
              {statuses.map((s) => (
                <option key={s} value={s}>{s === "All" ? "All Statuses" : s}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Data Grid */}
        <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl animate-slide-up relative min-h-[400px]">
          {loading ? (
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : filteredInventory.length === 0 ? (
            <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-500 gap-3">
              <Box className="w-12 h-12 opacity-20" />
              <p>No inventory items match your filters.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm whitespace-nowrap">
                <thead className="bg-slate-950/50 text-slate-400 border-b border-slate-800">
                  <tr>
                    <th className="px-6 py-4 font-medium">Product</th>
                    <th className="px-6 py-4 font-medium">Location</th>
                    <th className="px-6 py-4 font-medium">Category</th>
                    <th className="px-6 py-4 font-medium">Capacity</th>
                    <th className="px-6 py-4 font-medium">Reorder Pt</th>
                    <th className="px-6 py-4 font-medium">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/50">
                  {filteredInventory.map((item, idx) => (
                    <tr key={`${item.product_id}-${item.location}-${idx}`} className="hover:bg-slate-800/20 transition-colors">
                      <td className="px-6 py-4">
                        <p className="font-medium text-slate-200">{item.product_name}</p>
                        <p className="text-xs text-slate-500 mt-0.5 font-mono">{item.product_id}</p>
                      </td>
                      <td className="px-6 py-4 text-slate-300">
                        {item.location}
                      </td>
                      <td className="px-6 py-4">
                        <span className="px-2 py-1 bg-slate-800 text-slate-300 rounded text-xs capitalize">
                          {item.category}
                        </span>
                      </td>
                      <td className="px-6 py-4 min-w-[200px]">
                        <div className="flex items-center justify-between text-xs mb-1.5">
                          <span className="text-slate-300 font-medium">{item.stock_level} units</span>
                          <span className="text-slate-500">/ {item.max_capacity}</span>
                        </div>
                        <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                          <div 
                            className={`h-full transition-all duration-1000 ${
                              item.status === 'CRITICAL' ? 'bg-red-500' :
                              item.status === 'LOW' ? 'bg-amber-500' : 'bg-emerald-500'
                            }`}
                            style={{ width: `${Math.min(item.capacity_pct, 100)}%` }}
                          />
                        </div>
                      </td>
                      <td className="px-6 py-4 text-slate-400">
                        {item.reorder_point} units
                      </td>
                      <td className="px-6 py-4">
                        {item.status === 'OK' ? (
                          <div className="flex items-center gap-1.5 text-emerald-400 bg-emerald-400/10 px-2.5 py-1 rounded-full w-max text-xs font-medium border border-emerald-400/20">
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            Healthy
                          </div>
                        ) : item.status === 'LOW' ? (
                          <div className="flex items-center gap-1.5 text-amber-400 bg-amber-400/10 px-2.5 py-1 rounded-full w-max text-xs font-medium border border-amber-400/20">
                            <AlertTriangle className="w-3.5 h-3.5" />
                            Low Stock
                          </div>
                        ) : (
                          <div className="flex items-center gap-1.5 text-red-400 bg-red-400/10 px-2.5 py-1 rounded-full w-max text-xs font-medium border border-red-400/20 shadow-[0_0_10px_rgba(239,68,68,0.2)]">
                            <AlertTriangle className="w-3.5 h-3.5" />
                            Critical
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
