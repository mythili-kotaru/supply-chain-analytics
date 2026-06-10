"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, Bell, ChevronDown, Zap } from "lucide-react";
import type { DashboardStats } from "@/types";
import { UserProfilePanel } from "@/components/UserProfilePanel";

interface NavbarProps {
  stats: DashboardStats;
}

const NAV_ITEMS = [
  { name: "Dashboard", href: "/" },
  { name: "Inventory", href: "/inventory" },
  { name: "Forecasting", href: "/forecasting" },
  { name: "Orders", href: "/orders" },
  { name: "Analytics", href: "/analytics" },
];

export function Navbar({ stats }: NavbarProps) {
  const allHealthy = stats.services.every((s) => s.status === "healthy");
  const pathname = usePathname();
  const [profileOpen, setProfileOpen] = useState(false);
  const [role, setRole] = useState<"analyst" | "admin">("analyst");
  const [userName, setUserName] = useState<string>("Mythili Kotaru");

  useEffect(() => {
    if (typeof window !== "undefined") {
      const storedRole = localStorage.getItem("scai_user_role") as "analyst" | "admin";
      if (storedRole) setRole(storedRole);
      const storedName = localStorage.getItem("scai_user_name");
      if (storedName) setUserName(storedName);
    }
  }, []);

  const initials = userName
    .split(" ")
    .map((n) => n[0])
    .join("")
    .substring(0, 2)
    .toUpperCase();

  return (
    <header className="h-14 border-b border-slate-800 bg-slate-950/80 backdrop-blur-sm flex items-center px-6 gap-6 sticky top-0 z-50">
      {/* Logo / Brand */}
      <div className="flex items-center gap-2.5 mr-4">
        <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-blue-500 to-blue-700 flex items-center justify-center">
          <Zap className="w-4 h-4 text-white" />
        </div>
        <div>
          <span className="text-sm font-bold text-white tracking-tight">SupplyChain</span>
          <span className="text-sm font-bold text-blue-400 tracking-tight"> AI</span>
        </div>
        <span className="text-xs text-slate-500 border border-slate-700 rounded px-1.5 py-0.5 ml-1">
          CVS Health
        </span>
      </div>

      {/* Nav links */}
      <nav className="hidden md:flex items-center gap-1 text-sm">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.name}
              href={item.href}
              className={`px-3 py-1.5 rounded-lg transition-colors ${
                isActive
                  ? "bg-slate-800 text-white font-medium"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
              }`}
            >
              {item.name}
            </Link>
          );
        })}
      </nav>

      {/* Spacer */}
      <div className="flex-1" />

      {/* System health pill */}
      <div
        className={`hidden sm:flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full border ${
          allHealthy
            ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
            : "bg-red-500/10 border-red-500/30 text-red-400"
        }`}
      >
        <span className={`w-1.5 h-1.5 rounded-full live-dot ${allHealthy ? "bg-emerald-400" : "bg-red-400"}`} />
        <Activity className="w-3 h-3" />
        <span className="font-medium">{allHealthy ? "All systems operational" : "Degraded"}</span>
      </div>

      {/* Pending approvals badge */}
      <button className="relative p-2 rounded-lg hover:bg-slate-800 transition-colors">
        <Bell className="w-4 h-4 text-slate-400" />
        {stats.pending_approvals > 0 && (
          <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-red-500 rounded-full text-[10px] font-bold text-white flex items-center justify-center">
            {stats.pending_approvals}
          </span>
        )}
      </button>

      {/* User — click to open profile panel */}
      <div className="relative">
        <button
          onClick={() => setProfileOpen((v) => !v)}
          className="flex items-center gap-2 pl-3 border-l border-slate-800 hover:opacity-80 transition-opacity"
        >
          <div className="w-7 h-7 rounded-full bg-gradient-to-br from-violet-500 to-purple-700 flex items-center justify-center text-xs font-bold text-white">
            {initials}
          </div>
          <div className="hidden sm:block text-left">
            <p className="text-xs font-medium text-white leading-none">{userName}</p>
            <p className="text-[10px] text-slate-500 leading-none mt-0.5 capitalize">{role}</p>
          </div>
          <ChevronDown className={`w-3 h-3 text-slate-500 transition-transform duration-200 ${profileOpen ? "rotate-180" : ""}`} />
        </button>

        {profileOpen && (
          <UserProfilePanel 
            stats={stats} 
            role={role}
            setRole={setRole}
            onClose={() => setProfileOpen(false)} 
          />
        )}
      </div>
    </header>
  );
}
