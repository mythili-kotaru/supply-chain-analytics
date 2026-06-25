"use client";

import { useState, useRef, useEffect } from "react";
import { X, Send, Bot, User, Sparkles, Terminal, ArrowRight, Loader2, Check, AlertCircle } from "lucide-react";
import { api } from "@/lib/api";
import { useToast } from "./Toast";

const XIcon = X as any;
const SendIcon = Send as any;
const BotIcon = Bot as any;
const UserIcon = User as any;
const SparklesIcon = Sparkles as any;
const TerminalIcon = Terminal as any;
const ArrowRightIcon = ArrowRight as any;
const Loader2Icon = Loader2 as any;
const CheckIcon = Check as any;
const AlertCircleIcon = AlertCircle as any;

interface Message {
  id: string;
  sender: "user" | "bot";
  text: string;
  thoughts?: string[];
  nodesVisited?: string[];
  sqlResults?: any[];
  sqlQuery?: string;
  proposal?: {
    id: string;
    type: string;
    payload: any;
    status: "pending" | "approved" | "rejected";
  };
  error?: boolean;
}

interface CoPilotChatProps {
  isOpen: boolean;
  onClose: () => void;
  userRole: string;
}

export function CoPilotChat({ isOpen, onClose, userRole }: CoPilotChatProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      sender: "bot",
      text: "Hello! I am your AI Operations Co-Pilot. I can answer questions about inventory levels, run SQL insights, diagnose forecast accuracy model drift, or draft replenishment and region-allocation plans. How can I help you today?",
    },
  ]);
  const [input, setInput] = useState("");
  const [threadId, setThreadId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeThoughts, setActiveThoughts] = useState<string[]>([]);
  const [activeNodes, setActiveNodes] = useState<string[]>([]);

  const chatEndRef = useRef<HTMLDivElement>(null);
  const { addToast } = useToast();

  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages, activeThoughts, loading]);

  const handleSend = async (textToSend: string) => {
    if (!textToSend.trim() || loading) return;

    const userMsgId = Math.random().toString();
    const botMsgId = Math.random().toString();

    // Add user message to history
    setMessages((prev) => [
      ...prev,
      { id: userMsgId, sender: "user", text: textToSend },
    ]);
    setInput("");
    setLoading(true);
    setActiveThoughts([]);
    setActiveNodes([]);

    let thoughtsBuffer: string[] = [];
    let nodesVisited: string[] = [];
    let lastSummary = "";
    let status = "completed";
    let replenishmentResult: any = null;
    let allocationResult: any = null;
    let proposedTuning: any = null;

    try {
      await api.streamChat(textToSend, threadId, (event) => {
        if (event.event === "thought") {
          thoughtsBuffer.push(event.message);
          setActiveThoughts([...thoughtsBuffer]);
        } else if (event.event === "node_complete") {
          nodesVisited = event.nodes_visited || [];
          setActiveNodes([...nodesVisited]);
        } else if (event.event === "complete") {
          lastSummary = event.agent_summary;
          status = event.status;
          setThreadId(event.thread_id);
          replenishmentResult = event.replenishment_result;
          allocationResult = event.allocation_result;
          proposedTuning = event.proposed_tuning;
        } else if (event.event === "error") {
          throw new Error(event.message);
        }
      });

      // Assemble final bot message
      let proposal: any = null;
      if (status === "paused_at_hitl") {
        let payload = null;
        let type = "unknown";
        if (replenishmentResult) {
          payload = replenishmentResult;
          type = "replenishment";
        } else if (allocationResult) {
          payload = allocationResult;
          type = "allocation";
        } else if (proposedTuning) {
          payload = proposedTuning;
          type = "forecast_tuning";
        }

        proposal = {
          id: botMsgId, // we map inline proposal id to message ID
          type,
          payload,
          status: "pending",
        };
      }

      // Check if we have SQL outputs by querying thread state (or if it's formatted inline)
      // Since it's run via supervisor, we can parse or retrieve details.
      // If we got SQL results, we could show them in a table.
      setMessages((prev) => [
        ...prev,
        {
          id: botMsgId,
          sender: "bot",
          text: lastSummary || "I've completed my analysis.",
          thoughts: [...thoughtsBuffer],
          nodesVisited: [...nodesVisited],
          proposal,
        },
      ]);
    } catch (err: any) {
      console.error(err);
      setMessages((prev) => [
        ...prev,
        {
          id: botMsgId,
          sender: "bot",
          text: `An error occurred: ${err.message || "Failed to process chat query."}`,
          error: true,
        },
      ]);
      addToast(
        <div className="flex flex-col gap-0.5">
          <span className="font-semibold text-red-400">Chat Error</span>
          <span className="text-xs text-slate-300">{err.message || "Failed to communicate with supervisor agent."}</span>
        </div>,
        "error"
      );
    } finally {
      setLoading(false);
      setActiveThoughts([]);
      setActiveNodes([]);
    }
  };

  const handleInlineAction = async (msgId: string, approved: boolean) => {
    if (userRole !== "admin") {
      addToast(
        <div className="flex flex-col gap-0.5">
          <span className="font-semibold text-red-400">Access Denied</span>
          <span className="text-xs text-slate-300 font-normal">Only administrator role can approve proposals.</span>
        </div>,
        "error"
      );
      return;
    }

    setMessages((prev) =>
      prev.map((m) =>
        m.id === msgId && m.proposal
          ? {
              ...m,
              proposal: {
                ...m.proposal,
                status: approved ? "approved" : "rejected",
              },
            }
          : m
      )
    );

    addToast(
      <div className="flex flex-col gap-0.5">
        <span className={approved ? "font-semibold text-emerald-400" : "font-semibold text-slate-300"}>
          {approved ? "Proposal Approved" : "Proposal Rejected"}
        </span>
        <span className="text-xs text-slate-300 font-normal">
          {approved
            ? "Resuming supervisor workflow to write database changes..."
            : "Proposal rejected successfully."}
        </span>
      </div>,
      approved ? "success" : "info"
    );

    const isUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(msgId);

    if (threadId) {
      setLoading(true);
      let actionThoughts: string[] = [];
      let finalSummary = "";
      try {
        if (isUuid) {
          if (approved) {
            await api.streamProposalApprove(msgId, (event) => {
              if (event.event === "thought") {
                actionThoughts.push(event.message);
                setActiveThoughts([...actionThoughts]);
              }
            });
            finalSummary = "✅ Inventory actions executed successfully in live database.";
          } else {
            await api.streamProposalReject(msgId, (event) => {
              if (event.event === "thought") {
                actionThoughts.push(event.message);
                setActiveThoughts([...actionThoughts]);
              }
            });
            finalSummary = "❌ Proposal rejected and supervisor workflow completed.";
          }
        } else {
          // In-chat generated proposal, resume using streamChat
          await api.streamChat(approved ? "approve" : "reject", threadId, (event) => {
            if (event.event === "thought") {
              actionThoughts.push(event.message);
              setActiveThoughts([...actionThoughts]);
            } else if (event.event === "complete") {
              finalSummary = event.agent_summary;
            }
          });
          if (!finalSummary) {
            finalSummary = approved 
              ? "✅ Inventory actions executed successfully via chat conversation." 
              : "❌ Proposal rejected and supervisor workflow completed.";
          }
        }

        setMessages((prev) => [
          ...prev,
          {
            id: Math.random().toString(),
            sender: "bot",
            text: finalSummary,
            thoughts: [...actionThoughts],
          },
        ]);
      } catch (err: any) {
        addToast(
          <div className="flex flex-col gap-0.5">
            <span className="font-semibold text-red-400">Execution Error</span>
            <span className="text-xs text-slate-300">{err.message || "Failed to execute changes."}</span>
          </div>,
          "error"
        );
      } finally {
        setLoading(false);
        setActiveThoughts([]);
      }
    }
  };

  const suggestions = [
    { label: "Show low stock products", q: "Which products have low stock levels?" },
    { label: "Check model accuracy", q: "Which forecasting models have high MAPE?" },
    { label: "Plan Southeast transfers", q: "Propose inventory transfers for Southeast region" },
  ];

  if (!isOpen) return null;

  return (
    <div className="fixed inset-y-0 right-0 w-[420px] bg-slate-950/95 backdrop-blur-xl border-l border-slate-800 z-50 flex flex-col shadow-2xl transition-all duration-300">
      {/* Header */}
      <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/50">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white shadow-lg shadow-blue-500/20">
            <BotIcon size={18} />
          </div>
          <div>
            <h3 className="font-semibold text-sm text-slate-100 flex items-center gap-1.5">
              AI Co-Pilot
              <SparklesIcon size={12} className="text-blue-400 animate-pulse" />
            </h3>
            <span className="text-xs text-slate-400">LangGraph Supervisor</span>
          </div>
        </div>
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-slate-200 p-1.5 rounded-lg hover:bg-slate-800/60 transition"
        >
          <XIcon size={18} />
        </button>
      </div>

      {/* Message Feed */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((msg) => (
          <div key={msg.id} className={`flex flex-col ${msg.sender === "user" ? "items-end" : "items-start"}`}>
            <div className="flex items-center gap-1.5 mb-1 text-[11px] text-slate-500">
              {msg.sender === "user" ? (
                <>
                  <span>You ({userRole})</span>
                  <UserIcon size={10} />
                </>
              ) : (
                <>
                  <BotIcon size={10} />
                  <span>Operations Advisor</span>
                </>
              )}
            </div>

            <div
              className={`max-w-[90%] p-3 rounded-2xl text-sm leading-relaxed ${
                msg.sender === "user"
                  ? "bg-blue-600 text-white rounded-tr-none"
                  : msg.error
                  ? "bg-rose-950/40 border border-rose-900/60 text-rose-200 rounded-tl-none"
                  : "bg-slate-900/80 border border-slate-800 text-slate-200 rounded-tl-none"
              }`}
            >
              {msg.text}

              {/* Thoughts list inside bot message */}
              {msg.thoughts && msg.thoughts.length > 0 && (
                <div className="mt-2.5 pt-2 border-t border-slate-800/80">
                  <details className="group">
                    <summary className="text-[11px] text-blue-400 cursor-pointer flex items-center gap-1 select-none font-medium hover:text-blue-300">
                      <TerminalIcon size={10} />
                      View execution logs ({msg.thoughts.length} steps)
                    </summary>
                    <div className="mt-1.5 space-y-1 font-mono text-[10px] text-slate-400 bg-slate-950/80 p-2 rounded-lg max-h-40 overflow-y-auto border border-slate-900">
                      {msg.thoughts.map((t, idx) => (
                        <div key={idx} className="flex gap-1.5">
                          <span className="text-slate-600 select-none">&gt;</span>
                          <span>{t}</span>
                        </div>
                      ))}
                    </div>
                  </details>
                </div>
              )}

              {/* Inline proposal review block if any */}
              {msg.proposal && (
                <div className="mt-3 p-3 bg-slate-950/60 border border-slate-800 rounded-xl">
                  <div className="flex items-center gap-2 mb-2">
                    <AlertCircleIcon size={14} className="text-amber-500" />
                    <span className="font-semibold text-xs text-amber-500 uppercase tracking-wide">
                      Pending Action: {msg.proposal.type}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mb-3">
                    {msg.proposal.type === "replenishment"
                      ? "Replenishment agent generated purchase order drafts for deficient inventory."
                      : msg.proposal.type === "allocation"
                      ? "Allocation agent proposed inter-warehouse inventory transfers."
                      : "Forecasting analyst proposed hyperparameter model re-tuning."}
                  </p>

                  {msg.proposal.status === "pending" ? (
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleInlineAction(msg.id, true)}
                        className="flex-1 py-1.5 px-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-semibold flex items-center justify-center gap-1 transition"
                      >
                        <CheckIcon size={12} />
                        Approve
                      </button>
                      <button
                        onClick={() => handleInlineAction(msg.id, false)}
                        className="py-1.5 px-3 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-semibold transition"
                      >
                        Reject
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-1.5 text-xs text-slate-400 py-1 font-medium">
                      {msg.proposal.status === "approved" ? (
                        <>
                          <CheckIcon size={12} className="text-emerald-500" />
                          <span>Approved & Database updated.</span>
                        </>
                      ) : (
                        <>
                          <XIcon size={12} className="text-rose-500" />
                          <span>Proposal rejected.</span>
                        </>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}

        {/* Live Thought Streaming Feed */}
        {loading && activeThoughts.length > 0 && (
          <div className="flex flex-col items-start">
            <div className="flex items-center gap-1.5 mb-1 text-[11px] text-slate-500">
              <BotIcon size={10} />
              <span>Operations Advisor (Thinking...)</span>
            </div>
            <div className="max-w-[90%] p-3 rounded-2xl text-sm bg-slate-900/60 border border-slate-800/60 text-slate-400 rounded-tl-none flex flex-col gap-2">
              <div className="flex items-center gap-2">
                <Loader2Icon size={14} className="animate-spin text-blue-400" />
                <span className="text-xs font-medium text-slate-300">Agent executing steps...</span>
              </div>
              <div className="font-mono text-[10px] text-slate-400 bg-slate-950/80 p-2 rounded-lg border border-slate-900 max-h-32 overflow-y-auto">
                {activeThoughts.map((t, idx) => (
                  <div key={idx} className="flex gap-1.5">
                    <span className="text-slate-600 select-none">&gt;</span>
                    <span>{t}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Typing Loading Indicator */}
        {loading && activeThoughts.length === 0 && (
          <div className="flex items-center gap-2 text-slate-500 text-xs p-2">
            <Loader2Icon size={14} className="animate-spin text-blue-400" />
            <span>Consulting LangGraph supervisor...</span>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Suggested Questions */}
      {messages.length === 1 && !loading && (
        <div className="p-4 border-t border-slate-900 space-y-2 bg-slate-950/50">
          <p className="text-xs text-slate-500 font-medium px-1">Suggested inquiries:</p>
          <div className="flex flex-col gap-2">
            {suggestions.map((s, idx) => (
              <button
                key={idx}
                onClick={() => handleSend(s.q)}
                className="w-full text-left p-2 rounded-lg bg-slate-900/50 border border-slate-800/80 hover:bg-slate-800/50 hover:border-slate-700 text-xs text-slate-300 flex items-center justify-between group transition"
              >
                <span>{s.label}</span>
                <ArrowRightIcon size={12} className="text-slate-500 group-hover:text-blue-400 group-hover:translate-x-0.5 transition-all" />
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input Box */}
      <div className="p-4 border-t border-slate-800 bg-slate-950">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend(input);
          }}
          className="flex items-center gap-2 bg-slate-900 border border-slate-800 rounded-xl p-1.5 focus-within:border-blue-500/50 focus-within:ring-1 focus-within:ring-blue-500/20 transition"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            disabled={loading}
            placeholder="Ask a question or request a proposal..."
            className="flex-1 bg-transparent text-sm text-slate-100 placeholder-slate-500 px-2 py-1 outline-none disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="p-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white disabled:bg-slate-800 disabled:text-slate-600 transition"
          >
            <SendIcon size={14} />
          </button>
        </form>
      </div>
    </div>
  );
}
