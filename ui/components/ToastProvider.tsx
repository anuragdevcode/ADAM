'use client';

import React, { createContext, useContext, useState, useCallback } from 'react';
import { CheckCircle2, AlertCircle, AlertTriangle, Info, X } from 'lucide-react';

export type ToastType = 'success' | 'error' | 'warning' | 'info';

export interface ToastItem {
  id: string;
  type: ToastType;
  message: string;
  duration?: number;
}

interface ToastContextType {
  toast: {
    success: (message: string, duration?: number) => void;
    error: (message: string, duration?: number) => void;
    warning: (message: string, duration?: number) => void;
    info: (message: string, duration?: number) => void;
  };
  dismiss: (id: string) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const addToast = useCallback((type: ToastType, message: string, duration = 3500) => {
    const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
    const newToast: ToastItem = { id, type, message, duration };

    setToasts((prev) => [...prev, newToast]);

    if (duration > 0) {
      setTimeout(() => {
        setToasts((prev) => prev.filter((t) => t.id !== id));
      }, duration);
    }
  }, []);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toastMethods = {
    success: (message: string, duration?: number) => addToast('success', message, duration),
    error: (message: string, duration?: number) => addToast('error', message, duration),
    warning: (message: string, duration?: number) => addToast('warning', message, duration),
    info: (message: string, duration?: number) => addToast('info', message, duration),
  };

  return (
    <ToastContext.Provider value={{ toast: toastMethods, dismiss }}>
      {children}
      <div
        aria-live="polite"
        className="fixed bottom-5 right-5 z-[9999] flex flex-col gap-2 max-w-sm w-full pointer-events-none px-4 sm:px-0"
      >
        {toasts.map((t) => {
          const isSuccess = t.type === 'success';
          const isError = t.type === 'error';
          const isWarning = t.type === 'warning';

          const IconComponent = isSuccess
            ? CheckCircle2
            : isError
            ? AlertCircle
            : isWarning
            ? AlertTriangle
            : Info;

          return (
            <div
              key={t.id}
              className={`pointer-events-auto flex items-start gap-3 p-3.5 rounded-xl border shadow-lg backdrop-blur-md transition-all duration-200 animate-in fade-in slide-in-from-bottom-3 ease-spring ${
                isSuccess
                  ? 'bg-white/95 dark:bg-[#151c28]/95 border-emerald-200 dark:border-emerald-800/60 text-slate-800 dark:text-slate-100 shadow-emerald-500/10'
                  : isError
                  ? 'bg-white/95 dark:bg-[#151c28]/95 border-rose-200 dark:border-rose-800/60 text-slate-800 dark:text-slate-100 shadow-rose-500/10'
                  : isWarning
                  ? 'bg-white/95 dark:bg-[#151c28]/95 border-amber-200 dark:border-amber-800/60 text-slate-800 dark:text-slate-100 shadow-amber-500/10'
                  : 'bg-white/95 dark:bg-[#151c28]/95 border-slate-200 dark:border-slate-800 text-slate-800 dark:text-slate-100'
              }`}
            >
              <div
                className={`w-6 h-6 rounded-lg flex items-center justify-center shrink-0 mt-0.5 ${
                  isSuccess
                    ? 'text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/50'
                    : isError
                    ? 'text-rose-600 dark:text-rose-400 bg-rose-50 dark:bg-rose-950/50'
                    : isWarning
                    ? 'text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/50'
                    : 'text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-950/50'
                }`}
              >
                <IconComponent className="w-4 h-4" />
              </div>
              <p className="text-xs font-medium leading-relaxed flex-1 pt-0.5">{t.message}</p>
              <button
                type="button"
                onClick={() => dismiss(t.id)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1 rounded-md hover:scale-110 active:scale-90 transition-all duration-150 cursor-pointer"
                title="Dismiss"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextType {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}
