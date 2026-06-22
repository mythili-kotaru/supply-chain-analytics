"use client";

import React, { createContext, useContext, useState, useCallback, ReactNode } from "react";
import { X, CheckCircle, AlertCircle, Info } from "lucide-react";
import clsx from "clsx";

type ToastType = "success" | "error" | "info";

interface Toast {
  id: string;
  message: React.ReactNode;
  type: ToastType;
}

interface ToastContextType {
  addToast: (message: React.ReactNode, type: ToastType) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((message: string, type: ToastType) => {
    const id = Math.random().toString(36).substring(2, 9);
    setToasts((prev) => [...prev, { id, message, type }]);

    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 5000);
  }, []);

  const removeToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  return (
    <ToastContext.Provider value={{ addToast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={clsx(
              "flex items-center gap-3 px-4 py-3 rounded-lg shadow-lg text-sm border animate-slide-up w-80",
              {
                "bg-emerald-950/80 border-emerald-900 text-emerald-200": toast.type === "success",
                "bg-red-950/80 border-red-900 text-red-200": toast.type === "error",
                "bg-slate-900/80 border-slate-800 text-slate-200": toast.type === "info",
              }
            )}
          >
            {toast.type === "success" && <CheckCircle className="w-5 h-5 text-emerald-500 flex-shrink-0" />}
            {toast.type === "error" && <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0" />}
            {toast.type === "info" && <Info className="w-5 h-5 text-slate-400 flex-shrink-0" />}
            <span className="flex-1">{toast.message}</span>
            <button
              onClick={() => removeToast(toast.id)}
              className="text-slate-500 hover:text-slate-300 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (context === undefined) {
    throw new Error("useToast must be used within a ToastProvider");
  }
  return context;
}
