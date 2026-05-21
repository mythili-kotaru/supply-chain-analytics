"use client";

import { useState } from "react";
import {
  CheckCircle2, XCircle, ChevronDown, ChevronUp,
  ShoppingCart, ArrowLeftRight, BarChart2,
  Clock, Cpu, GitBranch, Loader2, Zap,
} from "lucide-react";
import type { Proposal } from "@/types";

interface ProposalCardProps {
  proposal: Proposal;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
}

// ── Day 4: approval result shown after LangGraph resume completes ─────────────
interface AgentResult {
  via_langgraph: boolean;
  nodes_visited: string[];
  final_message: string;
  graph_status: string | null;
}

const TYPE_META = {
  replenishment: {
    icon: ShoppingCart,
    label: "Purchase Order",
    color: "text-blue-400",
    bg: "bg-blue-500/10",
    border: "border-blue-500/20",
  },
  allocation: {
    icon: ArrowLeftRight,
    label: "Inventory Transfer",
    color: "text-violet-400",
    bg: "bg-violet-500/10",
    border: "border-violet-500/20",
  },
  forecast_tuning: {
    icon: BarChart2,
    label: "Model Retuning",
    color: "text-amber-400",
    bg: "bg-amber-500/10",
    border: "border-amber-500/20",
  },
};

export function ProposalCard({ proposal, onApprove, onReject }: ProposalCardProps) {
  const [expanded, setExpanded] = useState(false);

  // ── Day 4: loading state while LangGraph graph is running ────────────────
  // approving/rejecting may take 5-30s (OpenAI + A2A polling)
  const [actionState, setActionState] = useState<
    "idle" | "approving" | "rejecting" | "done"
  >("idle");
  const [agentResult, setAgentResult] = useState<AgentResult | null>(null);

  const meta = TYPE_META[proposal.type];
  const Icon = meta.icon;
  const isPending = proposal.status === "pending" && actionState === "idle";
  const isApproved = proposal.status === "approved" || actionState === "done" && agentResult !== null && agentResult.graph_status !== "rejected";
  const isLoading = actionState === "approving" || actionState === "rejecting";

  const timeAgo = (iso: string) => {
    const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
    if (diff < 1) return "just now";
    if (diff < 60) return `${diff}m ago`;
    return `${Math.floor(diff / 60)}h ago`;
  };

  // ── Day 4: wrap onApprove/onReject to show loading + result ──────────────
  // The parent's onApprove calls the API and returns the response.
  // We show a spinner while it's in-flight, then surface the agent result.
  const handleApprove = async () => {
    setActionState("approving");
    try {
      // onApprove is async — the parent passes the API response back via a
      // custom event on the proposal element. We call it and await it.
      await (onApprove as unknown as (id: string) => Promise<AgentResult | void>)(proposal.id);
    } finally {
      setActionState("done");
    }
  };

  const handleReject = async () => {
    setActionState("rejecting");
    try {
      await (onReject as unknown as (id: string) => Promise<AgentResult | void>)(proposal.id);
    } finally {
      setActionState("done");
    }
  };

  return (
    <div
      className={`card overflow-hidden slide-in transition-all ${
        isPending
          ? proposal.severity === "CRITICAL"
            ? "border-red-800/40 card-critical-glow"
            : "border-slate-700"
          : isApproved
          ? "border-emerald-800/50"
          : "border-red-900/50"
      }`}
    >
      {/* Top bar — severity stripe */}
      <div
        className={`h-1 w-full ${
          proposal.severity === "CRITICAL"
            ? "bg-gradient-to-r from-red-500 to-red-400"
            : proposal.severity === "HIGH"
            ? "bg-gradient-to-r from-orange-500 to-orange-400"
            : "bg-gradient-to-r from-yellow-500 to-yellow-400"
        }`}
      />

      <div className="p-4">
        {/* Header row */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            {/* Type icon */}
            <div className={`p-2 rounded-lg ${meta.bg} ${meta.border} border shrink-0`}>
              <Icon className={`w-4 h-4 ${meta.color}`} />
            </div>

            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className={`text-xs font-semibold ${meta.color}`}>{meta.label}</span>
                <span
                  className={
                    proposal.severity === "CRITICAL"
                      ? "badge-critical"
                      : proposal.severity === "HIGH"
                      ? "badge-high"
                      : "badge-low"
                  }
                >
                  {proposal.severity}
                </span>
                {/* Day 4: show loading badge while LangGraph runs */}
                {isLoading && (
                  <span className="text-xs font-semibold px-2 py-0.5 rounded-full border bg-indigo-500/10 text-indigo-400 border-indigo-500/30 flex items-center gap-1">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    {actionState === "approving" ? "Resuming agent…" : "Rejecting…"}
                  </span>
                )}
                {!isPending && !isLoading && (
                  <span
                    className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${
                      proposal.status === "approved" || actionState === "done"
                        ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                        : "bg-red-500/10 text-red-400 border-red-500/30"
                    }`}
                  >
                    {proposal.status.toUpperCase()}
                  </span>
                )}
              </div>

              {/* Product + trigger */}
              <p className="text-sm font-semibold text-white mt-0.5">
                {proposal.trigger.product_name}
                {proposal.trigger.location && (
                  <span className="text-slate-400 font-normal"> · {proposal.trigger.location}</span>
                )}
              </p>

              {/* Trigger metric */}
              <p className="text-xs text-slate-400 mt-0.5">
                {proposal.trigger.metric === "stock_level" ? (
                  <>
                    Stock:{" "}
                    <span className="text-red-400 font-medium">{proposal.trigger.current_value} units</span>
                    {" "}(threshold: {proposal.trigger.threshold})
                  </>
                ) : (
                  <>
                    MAPE:{" "}
                    <span className="text-orange-400 font-medium">{proposal.trigger.current_value}%</span>
                    {" "}(threshold: {proposal.trigger.threshold}%)
                  </>
                )}
              </p>
            </div>
          </div>

          {/* Time + meta */}
          <div className="text-right shrink-0">
            <p className="text-xs text-slate-500 flex items-center gap-1 justify-end">
              <Clock className="w-3 h-3" />
              {timeAgo(proposal.created_at)}
            </p>
            {proposal.latency_ms && (
              <p className="text-xs text-slate-600 flex items-center gap-1 justify-end mt-0.5">
                <Cpu className="w-3 h-3" />
                {proposal.latency_ms}ms
              </p>
            )}
            {/* Day 4: show thread_id chip if available */}
            {proposal.thread_id && (
              <p className="text-xs text-indigo-600 flex items-center gap-1 justify-end mt-0.5 font-mono">
                <Zap className="w-3 h-3" />
                {proposal.thread_id.slice(0, 8)}…
              </p>
            )}
          </div>
        </div>

        {/* Agent reasoning */}
        <div className="mt-3 p-3 bg-slate-800/60 rounded-lg border border-slate-700/50">
          <p className="text-xs text-slate-400 leading-relaxed">
            <span className="text-slate-500 font-medium">Agent: </span>
            {proposal.agent_reasoning}
          </p>
        </div>

        {/* Day 4: Agent execution result — shown after LangGraph resume completes */}
        {agentResult && (
          <div className={`mt-2 p-3 rounded-lg border text-xs ${
            agentResult.graph_status === "executed"
              ? "bg-emerald-500/5 border-emerald-500/20"
              : "bg-slate-800/40 border-slate-700/50"
          }`}>
            <div className="flex items-center gap-1.5 mb-1.5">
              <Zap className="w-3 h-3 text-indigo-400" />
              <span className="font-semibold text-indigo-400">LangGraph Result</span>
              {agentResult.via_langgraph ? (
                <span className="text-slate-500">(graph executed)</span>
              ) : (
                <span className="text-slate-500">(direct update)</span>
              )}
            </div>
            <p className="text-slate-300 leading-relaxed">{agentResult.final_message}</p>
            {agentResult.nodes_visited.length > 0 && (
              <div className="flex items-center gap-1.5 mt-2 text-slate-500">
                <GitBranch className="w-3 h-3" />
                {agentResult.nodes_visited.map((n, i) => (
                  <span key={n}>
                    <span className="font-mono text-slate-400">{n}</span>
                    {i < agentResult.nodes_visited.length - 1 && (
                      <span className="text-slate-600 mx-1">→</span>
                    )}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Expanded detail */}
        {expanded && (
          <div className="mt-3 space-y-3">
            {/* Replenishment detail */}
            {proposal.replenishment && (
              <div className="rounded-lg border border-slate-700 overflow-hidden">
                <div className="px-3 py-2 bg-slate-800/60 border-b border-slate-700">
                  <p className="text-xs font-semibold text-slate-300">Purchase Order Detail</p>
                </div>
                <div className="divide-y divide-slate-800">
                  {proposal.replenishment.purchase_orders.map((po) => (
                    <div key={po.po_number} className="px-3 py-2.5 text-xs">
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="font-mono text-slate-400">{po.po_number}</span>
                        <span className="font-semibold text-white">${po.order_value.toLocaleString()}</span>
                      </div>
                      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-slate-500">
                        <span>Qty: <span className="text-slate-300">{po.order_quantity} units</span></span>
                        <span>Supplier: <span className="text-slate-300">{po.supplier_name}</span></span>
                        <span>Lead time: <span className="text-slate-300">{po.lead_time_days} days</span></span>
                        <span>Delivery: <span className="text-slate-300">{po.expected_delivery}</span></span>
                      </div>
                    </div>
                  ))}
                </div>
                <div className="px-3 py-2 bg-slate-800/40 flex items-center justify-between">
                  <span className="text-xs text-slate-500">Total order value</span>
                  <span className="text-sm font-bold text-white">
                    ${proposal.replenishment.total_order_value.toLocaleString()}
                  </span>
                </div>
              </div>
            )}

            {/* Allocation detail */}
            {proposal.allocation && (
              <div className="rounded-lg border border-slate-700 overflow-hidden">
                <div className="px-3 py-2 bg-slate-800/60 border-b border-slate-700">
                  <p className="text-xs font-semibold text-slate-300">Transfer Plan</p>
                </div>
                {proposal.allocation.transfers.map((t, i) => (
                  <div key={i} className="px-3 py-2.5 text-xs">
                    <div className="flex items-center gap-2 text-slate-300">
                      <span className="font-medium">{t.from_location}</span>
                      <ArrowLeftRight className="w-3 h-3 text-violet-400" />
                      <span className="font-medium">{t.to_location}</span>
                      <span className="ml-auto font-bold text-white">{t.transfer_quantity} units</span>
                    </div>
                    <p className="text-slate-500 mt-1">{t.reason}</p>
                  </div>
                ))}
              </div>
            )}

            {/* Forecast tuning detail */}
            {proposal.forecast_tuning && (
              <div className="rounded-lg border border-slate-700 overflow-hidden">
                <div className="px-3 py-2 bg-slate-800/60 border-b border-slate-700">
                  <p className="text-xs font-semibold text-slate-300">Hyperparameter Changes</p>
                </div>
                <div className="px-3 py-2.5">
                  <div className="grid grid-cols-3 gap-2 text-xs mb-2">
                    <span className="text-slate-500">Parameter</span>
                    <span className="text-slate-500">Current</span>
                    <span className="text-slate-500">Proposed</span>
                  </div>
                  {Object.entries(proposal.forecast_tuning.new_params).map(([key, newVal]) => {
                    const oldVal = proposal.forecast_tuning!.old_params[key];
                    const changed = oldVal !== newVal;
                    return (
                      <div key={key} className={`grid grid-cols-3 gap-2 text-xs py-1 ${changed ? "text-amber-400" : "text-slate-400"}`}>
                        <span className="font-mono">{key}</span>
                        <span className={changed ? "line-through text-slate-600" : ""}>{oldVal}</span>
                        <span className={changed ? "font-semibold" : ""}>{newVal}</span>
                      </div>
                    );
                  })}
                  <div className="mt-2 pt-2 border-t border-slate-700">
                    <p className="text-xs text-emerald-400 font-medium">
                      Expected: {proposal.forecast_tuning.expected_mape_improvement}
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* Trace info */}
            {proposal.nodes_visited && (
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <GitBranch className="w-3 h-3" />
                <span>Nodes: </span>
                {proposal.nodes_visited.map((n, i) => (
                  <span key={n}>
                    <span className="text-slate-400 font-mono">{n}</span>
                    {i < proposal.nodes_visited!.length - 1 && (
                      <span className="text-slate-600 mx-1">→</span>
                    )}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Footer */}
        <div className="mt-3 flex items-center justify-between">
          {/* Expand toggle */}
          <button
            onClick={() => setExpanded(!expanded)}
            className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300 transition-colors"
          >
            {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            {expanded ? "Hide details" : "View details"}
          </button>

          {/* Action buttons */}
          {isPending && !isLoading && (
            <div className="flex items-center gap-2">
              <button
                onClick={handleReject}
                className="btn-reject"
                disabled={isLoading}
              >
                <XCircle className="w-3.5 h-3.5" />
                Reject
              </button>
              <button
                onClick={handleApprove}
                className="btn-approve"
                disabled={isLoading}
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                Approve
              </button>
            </div>
          )}

          {/* Loading state */}
          {isLoading && (
            <div className="flex items-center gap-2 text-xs text-indigo-400">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              <span>
                {actionState === "approving"
                  ? "Resuming LangGraph — executing action…"
                  : "Sending rejection to agent…"}
              </span>
            </div>
          )}

          {!isPending && !isLoading && (
            <span className={`text-xs font-medium flex items-center gap-1 ${
              proposal.status === "approved" ? "text-emerald-400" : "text-red-400"
            }`}>
              {proposal.status === "approved"
                ? <><CheckCircle2 className="w-3.5 h-3.5" /> Approved &amp; executed</>
                : <><XCircle className="w-3.5 h-3.5" /> Rejected</>
              }
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
