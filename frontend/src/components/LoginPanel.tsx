"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { Lock, User, ShieldAlert, Zap, Loader2 } from "lucide-react";

const LockIcon = Lock as any;
const UserIcon = User as any;
const ShieldAlertIcon = ShieldAlert as any;
const ZapIcon = Zap as any;
const Loader2Icon = Loader2 as any;

interface LoginPanelProps {
  onLoginSuccess: (token: string) => void;
}

export function LoginPanel({ onLoginSuccess }: LoginPanelProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLogin = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!username || !password) {
      setError("Please fill in all fields.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await api.login(username, password);
      localStorage.setItem("scai_access_token", res.access_token);
      localStorage.setItem("scai_user_role", res.role);
      localStorage.setItem("scai_user_name", res.full_name);
      onLoginSuccess(res.access_token);
    } catch (err) {
      console.error("Login failed:", err);
      setError("Invalid username or password. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleQuickLogin = (user: string, pass: string) => {
    setUsername(user);
    setPassword(pass);
    // Use setTimeout to ensure state updates before form submission
    setTimeout(() => {
      setLoading(true);
      api.login(user, pass)
        .then((res) => {
          localStorage.setItem("scai_access_token", res.access_token);
          localStorage.setItem("scai_user_role", res.role);
          localStorage.setItem("scai_user_name", res.full_name);
          onLoginSuccess(res.access_token);
        })
        .catch((err) => {
          console.error("Quick login failed:", err);
          setError("Failed to execute quick login.");
          setLoading(false);
        });
    }, 50);
  };

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col justify-center items-center px-4 relative overflow-hidden">
      {/* Background gradients for premium feel */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-blue-500/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-violet-600/10 rounded-full blur-3xl pointer-events-none" />

      <div className="w-full max-w-md z-10 space-y-6">
        {/* Brand/Logo header */}
        <div className="flex flex-col items-center text-center">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center shadow-lg shadow-blue-500/20 mb-3 animate-pulse">
            <ZapIcon className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-1.5">
            <span>CVS Health</span>
            <span className="bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-violet-400">SupplyChain AI</span>
          </h1>
          <p className="text-xs text-slate-500 mt-1.5 max-w-xs">
            Autonomous operations monitoring & role-based proposal execution
          </p>
        </div>

        {/* Login form Card */}
        <div className="bg-slate-900/40 backdrop-blur-md border border-slate-800/80 p-8 rounded-3xl shadow-2xl relative">
          <div className="absolute -inset-[1px] bg-gradient-to-r from-blue-500/20 to-violet-500/20 rounded-3xl -z-10 pointer-events-none" />
          
          <h2 className="text-lg font-semibold text-white mb-6">Log In to Operations Platform</h2>

          {error && (
            <div className="flex items-start gap-2.5 bg-red-500/10 border border-red-500/20 rounded-xl p-3 text-xs text-red-400 mb-5 animate-shake">
              <ShieldAlertIcon className="w-4 h-4 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleLogin} className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-[11px] font-bold text-slate-500 uppercase tracking-widest pl-1">
                Username
              </label>
              <div className="relative">
                <UserIcon className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  placeholder="Enter username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  disabled={loading}
                  className="w-full bg-slate-950/60 border border-slate-800 focus:border-slate-700 text-slate-200 text-sm rounded-xl pl-10 pr-4 py-2.5 focus:outline-none transition-colors"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-[11px] font-bold text-slate-500 uppercase tracking-widest pl-1">
                Password
              </label>
              <div className="relative">
                <LockIcon className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
                <input
                  type="password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={loading}
                  className="w-full bg-slate-950/60 border border-slate-800 focus:border-slate-700 text-slate-200 text-sm rounded-xl pl-10 pr-4 py-2.5 focus:outline-none transition-colors"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full mt-2 py-3 bg-gradient-to-r from-blue-500 to-violet-600 hover:from-blue-600 hover:to-violet-700 text-white font-medium rounded-xl text-sm transition-all shadow-lg shadow-violet-900/30 flex items-center justify-center gap-2 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {loading ? (
                <>
                  <Loader2Icon className="w-4 h-4 animate-spin" />
                  <span>Authenticating...</span>
                </>
              ) : (
                <span>Log In</span>
              )}
            </button>
          </form>
        </div>

        {/* Demo profiles quick-login cards */}
        <div className="space-y-2.5">
          <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest text-center">
            Or Quick Log In (Demo Mode)
          </p>
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={() => handleQuickLogin("mythili", "mythili123")}
              disabled={loading}
              className="flex flex-col text-left p-4 bg-slate-900/30 hover:bg-slate-900/60 border border-slate-800/60 hover:border-slate-800 rounded-2xl transition-all group disabled:opacity-60"
            >
              <span className="text-xs font-semibold text-white group-hover:text-blue-400 transition-colors">
                Supply Chain Analyst
              </span>
              <span className="text-[10px] text-slate-500 mt-1">
                Read-only dashboards, search, and resolution.
              </span>
            </button>

            <button
              onClick={() => handleQuickLogin("admin", "admin123")}
              disabled={loading}
              className="flex flex-col text-left p-4 bg-slate-900/30 hover:bg-slate-900/60 border border-slate-800/60 hover:border-slate-800 rounded-2xl transition-all group disabled:opacity-60"
            >
              <span className="text-xs font-semibold text-white group-hover:text-violet-400 transition-colors">
                Ops Administrator
              </span>
              <span className="text-[10px] text-slate-500 mt-1">
                Full privileges (Trigger scans, approve/reject).
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
