"use client";

import { useState, useEffect, useRef } from "react";
import {
  CheckCircle2, XCircle, ChevronDown, ChevronUp,
  ShoppingCart, ArrowLeftRight, BarChart2,
  Clock, Cpu, GitBranch, Loader2, Zap, ExternalLink,
} from "lucide-react";

const CheckCircle2Icon = CheckCircle2 as any;
const XCircleIcon = XCircle as any;
const ChevronDownIcon = ChevronDown as any;
const ChevronUpIcon = ChevronUp as any;
const ShoppingCartIcon = ShoppingCart as any;
const ArrowLeftRightIcon = ArrowLeftRight as any;
const BarChart2Icon = BarChart2 as any;
const ClockIcon = Clock as any;
const CpuIcon = Cpu as any;
const GitBranchIcon = GitBranch as any;
const Loader2Icon = Loader2 as any;
const ZapIcon = Zap as any;
const ExternalLinkIcon = ExternalLink as any;

import type { Proposal } from "@/types";
import { api } from "@/lib/api";

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
    icon: ShoppingCartIcon,
    label: "Purchase Order",
    color: "text-blue-400",
    bg: "bg-blue-500/10",
    border: "border-blue-500/20",
  },
  allocation: {
    icon: ArrowLeftRightIcon,
    label: "Inventory Transfer",
    color: "text-violet-400",
    bg: "bg-violet-500/10",
    border: "border-violet-500/20",
  },
  forecast_tuning: {
    icon: BarChart2Icon,
    label: "Model Retuning",
    color: "text-amber-400",
    bg: "bg-amber-500/10",
    border: "border-amber-500/20",
  },
  supplier_config: {
    icon: CpuIcon,
    label: "Supplier Config",
    color: "text-rose-400",
    bg: "bg-rose-500/10",
    border: "border-rose-500/20",
  },
};

interface TerminalLog {
  timestamp: string;
  type: "info" | "success" | "poll" | "error";
  message: string;
}

export function ProposalCard({ proposal, onApprove, onReject }: ProposalCardProps) {
  const [expanded, setExpanded] = useState(false);

  // ── Day 4: loading state while LangGraph graph is running ────────────────
  // approving/rejecting may take 5-30s (OpenAI + A2A polling)
  const [actionState, setActionState] = useState<
    "idle" | "approving" | "rejecting" | "done"
  >("idle");
  const [agentResult, setAgentResult] = useState<AgentResult | null>(null);

  // Terminal log state
  const [logs, setLogs] = useState<TerminalLog[]>([]);
  const [showTerminal, setShowTerminal] = useState(false);
  const terminalEndRef = useRef<HTMLDivElement>(null);

  const meta = TYPE_META[proposal.type];
  const Icon = meta.icon;
  const isPending = proposal.status === "pending" && actionState === "idle";
  const isApproved = proposal.status === "approved" || (actionState === "done" && agentResult !== null && agentResult.graph_status !== "rejected");
  const isLoading = actionState === "approving" || actionState === "rejecting";

  // Auto-scroll terminal
  useEffect(() => {
    if (terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs]);

  const timeAgo = (iso: string) => {
    const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 60000);
    if (diff < 1) return "just now";
    if (diff < 60) return `${diff}m ago`;
    return `${Math.floor(diff / 60)}h ago`;
  };

  const addLog = (message: string, type: "info" | "success" | "poll" | "error" = "info") => {
    const timestamp = new Date().toLocaleTimeString();
    setLogs((prev) => [...prev, { timestamp, type, message }]);
  };

  // ── Day 4: wrap onApprove/onReject to show loading + result ──────────────
  const handleApprove = async () => {
    setActionState("approving");
    setShowTerminal(true);
    setLogs([]);
    addLog("Initializing secure approval connection...", "info");

    try {
      await api.streamProposalApprove(proposal.id, (event) => {
        if (event.event === "thought") {
          const type = event.message.includes("Polling") ? "poll" : "info";
          addLog(event.message, type);
        } else if (event.event === "node_complete") {
          addLog(`Completed LangGraph node: ${event.node}`, "success");
        } else if (event.event === "complete") {
          addLog("LangGraph workflow completed successfully.", "success");
          setAgentResult({
            via_langgraph: event.thread_id !== null,
            nodes_visited: event.nodes_visited,
            final_message: event.final_message,
            graph_status: event.status === "paused_at_hitl" ? "executed" : event.status,
          });
        } else if (event.event === "error") {
          addLog(`Error: ${event.message}`, "error");
        }
      });
      // Let the parent refresh the proposal list
      onApprove(proposal.id);
    } catch (err) {
      console.error("Approve stream failed:", err);
      addLog(`Approve failed: ${err instanceof Error ? err.message : String(err)}`, "error");
    } finally {
      setActionState("done");
    }
  };

  const handleReject = async () => {
    setActionState("rejecting");
    setShowTerminal(true);
    setLogs([]);
    addLog("Initializing secure rejection connection...", "info");

    try {
      await api.streamProposalReject(proposal.id, (event) => {
        if (event.event === "thought") {
          addLog(event.message, "info");
        } else if (event.event === "node_complete") {
          addLog(`Completed LangGraph node: ${event.node}`, "success");
        } else if (event.event === "complete") {
          addLog("LangGraph workflow completed successfully.", "success");
          setAgentResult({
            via_langgraph: event.thread_id !== null,
            nodes_visited: event.nodes_visited,
            final_message: event.final_message,
            graph_status: "rejected",
          });
        } else if (event.event === "error") {
          addLog(`Error: ${event.message}`, "error");
        }
      });
      // Let the parent refresh the proposal list
      onReject(proposal.id);
    } catch (err) {
      console.error("Reject stream failed:", err);
      addLog(`Reject failed: ${err instanceof Error ? err.message : String(err)}`, "error");
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
                    <Loader2Icon className="w-3 h-3 animate-spin" />
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
              <ClockIcon className="w-3 h-3" />
              {timeAgo(proposal.created_at)}
            </p>
            {proposal.latency_ms && (
              <p className="text-xs text-slate-600 flex items-center gap-1 justify-end mt-0.5">
                <CpuIcon className="w-3 h-3" />
                {proposal.latency_ms}ms
              </p>
            )}
            {/* Day 4: show thread_id chip if available */}
            {proposal.thread_id && (
              <p className="text-xs text-indigo-600 flex items-center gap-1 justify-end mt-0.5 font-mono">
                <ZapIcon className="w-3 h-3" />
                {proposal.thread_id.slice(0, 8)}…
              </p>
            )}
            {/* Day 5: LangSmith trace link */}
            {proposal.trace_id && (
              <a
                href={proposal.trace_url ?? "https://smith.langchain.com"}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-violet-500 hover:text-violet-400 flex items-center gap-1 justify-end mt-0.5 transition-colors"
                title={`LangSmith run: ${proposal.trace_id}`}
              >
                <ExternalLinkIcon className="w-3 h-3" />
                View Trace
              </a>
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

        {/* Real-time Agent Terminal */}
        {showTerminal && logs.length > 0 && (
          <div className="mt-3 bg-slate-950/90 border border-slate-800 rounded-lg p-3 font-mono text-[10px] text-slate-300 shadow-inner flex flex-col h-40">
            {/* Terminal Header */}
            <div className="flex items-center justify-between border-b border-slate-900 pb-1.5 mb-2 text-slate-500 shrink-0 select-none">
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-red-500/80" />
                <span className="w-2 h-2 rounded-full bg-yellow-500/80" />
                <span className="w-2 h-2 rounded-full bg-green-500/80 animate-pulse" />
                <span className="ml-1 text-[9px] uppercase tracking-wider font-semibold text-slate-400">Agent Terminal</span>
              </div>
              <div className="flex items-center gap-2">
                <span className={`w-1.5 h-1.5 rounded-full ${isLoading ? "bg-emerald-500 animate-ping" : "bg-slate-600"}`} />
                <span className="text-[9px] text-slate-400">{isLoading ? "active session" : "session complete"}</span>
                {!isLoading && (
                  <button 
                    onClick={() => setShowTerminal(false)}
                    className="ml-2 text-[9px] text-indigo-400 hover:text-indigo-300 hover:underline cursor-pointer"
                  >
                    Hide
                  </button>
                )}
              </div>
            </div>
            {/* Terminal Body */}
            <div className="flex-1 overflow-y-auto space-y-1 pr-1 scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent scroll-smooth">
              {logs.map((log, i) => (
                <div key={i} className="flex items-start gap-1.5 leading-normal">
                  <span className="text-slate-600 shrink-0 select-none">[{log.timestamp}]</span>
                  <span className={
                    log.type === "success" ? "text-emerald-400 font-medium" :
                    log.type === "error" ? "text-red-400 font-semibold" :
                    log.type === "poll" ? "text-violet-400" :
                    "text-slate-300"
                  }>
                    {log.type === "success" && "✔ "}
                    {log.type === "error" && "✖ "}
                    {log.message}
                  </span>
                </div>
              ))}
              <div ref={terminalEndRef} />
            </div>
          </div>
        )}

        {/* Day 4: Agent execution result — shown after LangGraph resume completes */}
        {agentResult && (
          <div className={`mt-2 p-3 rounded-lg border text-xs ${
            agentResult.graph_status === "executed"
              ? "bg-emerald-500/5 border-emerald-500/20"
              : "bg-slate-800/40 border-slate-700/50"
          }`}>
            <div className="flex items-center gap-1.5 mb-1.5">
              <ZapIcon className="w-3 h-3 text-indigo-400" />
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
                <GitBranchIcon className="w-3 h-3" />
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
                        <span className="font-mono text-slate-400 flex items-center gap-2">
                          {po.po_number}
                          {po.jira_ticket_key && (
                            <a
                              href={`http://localhost:8003/api/dashboard/jira/browse/${po.jira_ticket_key}`}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center gap-1.5 px-1.5 py-0.5 rounded bg-sky-950/40 border border-sky-800/50 hover:bg-sky-900/40 hover:border-sky-700/50 text-[9px] font-mono text-sky-400 hover:text-sky-300 transition-all shadow-sm group"
                            >
                              <span className="w-1 h-1 rounded-full bg-sky-400 group-hover:scale-125 transition-transform animate-pulse"></span>
                              <span className="font-semibold uppercase tracking-wider text-[8px] text-sky-500/80">Jira</span>
                              <span className="text-slate-300 font-medium">{po.jira_ticket_key}</span>
                              <ExternalLinkIcon className="w-2 h-2 opacity-60 group-hover:opacity-100 transition-opacity" />
                            </a>
                          )}
                        </span>
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
                      <ArrowLeftRightIcon className="w-3 h-3 text-violet-400" />
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

            {/* Supplier config detail */}
            {proposal.supplier_config && (
              <div className="rounded-lg border border-slate-700 overflow-hidden">
                <div className="px-3 py-2 bg-slate-800/60 border-b border-slate-700">
                  <p className="text-xs font-semibold text-slate-300">Supplier Settings Update</p>
                </div>
                <div className="px-3 py-2.5">
                  <div className="grid grid-cols-3 gap-2 text-xs mb-2">
                    <span className="text-slate-500">Property</span>
                    <span className="text-slate-500">Current</span>
                    <span className="text-slate-500">Proposed</span>
                  </div>
                  {/* Lead Time Days */}
                  <div className={`grid grid-cols-3 gap-2 text-xs py-1 ${proposal.supplier_config.lead_time_days !== proposal.supplier_config.old_lead_time_days ? "text-amber-400" : "text-slate-400"}`}>
                    <span>Lead Time</span>
                    <span className={proposal.supplier_config.lead_time_days !== proposal.supplier_config.old_lead_time_days ? "line-through text-slate-600" : ""}>
                      {proposal.supplier_config.old_lead_time_days} days
                    </span>
                    <span className={proposal.supplier_config.lead_time_days !== proposal.supplier_config.old_lead_time_days ? "font-semibold" : ""}>
                      {proposal.supplier_config.lead_time_days} days
                    </span>
                  </div>
                  {/* Defect Rate */}
                  <div className={`grid grid-cols-3 gap-2 text-xs py-1 ${proposal.supplier_config.defect_rate !== proposal.supplier_config.old_defect_rate ? "text-amber-400" : "text-slate-400"}`}>
                    <span>Defect Rate</span>
                    <span className={proposal.supplier_config.defect_rate !== proposal.supplier_config.old_defect_rate ? "line-through text-slate-600" : ""}>
                      {((proposal.supplier_config.old_defect_rate || 0) * 100).toFixed(2)}%
                    </span>
                    <span className={proposal.supplier_config.defect_rate !== proposal.supplier_config.old_defect_rate ? "font-semibold" : ""}>
                      {(proposal.supplier_config.defect_rate * 100).toFixed(2)}%
                    </span>
                  </div>
                  {/* PR Details if already approved/created */}
                  {proposal.supplier_config.pr_url && (
                    <div className="mt-2 pt-2 border-t border-slate-700">
                      <a
                        href={proposal.supplier_config.pr_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-blue-400 hover:text-blue-300 font-semibold flex items-center gap-1"
                      >
                        <ExternalLinkIcon className="w-3 h-3" />
                        View Pull Request (Branch: {proposal.supplier_config.branch_name})
                      </a>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Trace info */}
            {proposal.nodes_visited && (
              <div className="flex items-center gap-2 text-xs text-slate-500 flex-wrap">
                <GitBranchIcon className="w-3 h-3" />
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
            {/* Day 5: LangSmith deep link in expanded section */}
            {proposal.trace_id && (
              <a
                href={proposal.trace_url ?? "https://smith.langchain.com"}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 text-xs text-violet-400 hover:text-violet-300 transition-colors w-fit"
                title={`LangSmith run ID: ${proposal.trace_id}`}
              >
                <ExternalLinkIcon className="w-3 h-3" />
                <span>View full trace in LangSmith</span>
                <span className="font-mono text-violet-600">{proposal.trace_id.slice(0, 8)}…</span>
              </a>
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
            {expanded ? <ChevronUpIcon className="w-3.5 h-3.5" /> : <ChevronDownIcon className="w-3.5 h-3.5" />}
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
                <XCircleIcon className="w-3.5 h-3.5" />
                Reject
              </button>
              <button
                onClick={handleApprove}
                className="btn-approve"
                disabled={isLoading}
              >
                <CheckCircle2Icon className="w-3.5 h-3.5" />
                Approve
              </button>
            </div>
          )}

          {/* Loading state */}
          {isLoading && (
            <div className="flex items-center gap-2 text-xs text-indigo-400">
              <Loader2Icon className="w-3.5 h-3.5 animate-spin" />
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
                ? <><CheckCircle2Icon className="w-3.5 h-3.5" /> Approved &amp; executed</>
                : <><XCircleIcon className="w-3.5 h-3.5" /> Rejected</>
              }
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
