'use client';

import React from 'react';
import { X, Keyboard } from 'lucide-react';

interface KeyboardShortcutsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface ShortcutRow {
  keys: string[];
  description: string;
}

const SHORTCUT_GROUPS: { title: string; shortcuts: ShortcutRow[] }[] = [
  {
    title: 'General & Productivity',
    shortcuts: [
      { keys: ['⌘', 'K'], description: 'Open Command Palette & Global Search' },
      { keys: ['⌘', 'N'], description: 'Start a new conversation thread' },
      { keys: ['⌘', '/'], description: 'Open keyboard shortcuts cheat-sheet' },
      { keys: ['Esc'], description: 'Close active modal, drawer, or palette' },
    ],
  },
  {
    title: 'Chat & Composer',
    shortcuts: [
      { keys: ['Enter'], description: 'Submit current query' },
      { keys: ['Shift', 'Enter'], description: 'Insert a new line in composer' },
      { keys: ['Hold Space'], description: 'Push-to-talk voice recording (in text mode)' },
    ],
  },
  {
    title: 'Navigation Quick Keys',
    shortcuts: [
      { keys: ['⌘', '1'], description: 'Switch to Chat Studio' },
      { keys: ['⌘', '2'], description: 'Switch to Document Repository' },
      { keys: ['⌘', '3'], description: 'Switch to Precedent & Supersession Chains' },
      { keys: ['⌘', '4'], description: 'Switch to Agent Audits & Benchmarks' },
      { keys: ['⌘', '5'], description: 'Switch to Data Connectors & Ingestion' },
      { keys: ['⌘', '6'], description: 'Switch to Human QA Review Queue' },
    ],
  },
];

export default function KeyboardShortcutsModal({ isOpen, onClose }: KeyboardShortcutsModalProps) {
  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard Shortcuts"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/40 dark:bg-black/60 backdrop-blur-sm animate-in fade-in duration-100"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-lg bg-white dark:bg-[#111726] rounded-2xl border border-slate-200 dark:border-slate-800 shadow-2xl overflow-hidden animate-in zoom-in-95 duration-100"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-[#131b2c]/50">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-purple-50 dark:bg-purple-950/60 text-purple-600 dark:text-purple-400 flex items-center justify-center">
              <Keyboard className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Keyboard Shortcuts</h2>
              <p className="text-[11px] text-slate-400 dark:text-slate-500">Accelerate administrative research workflows</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6 max-h-[70vh] overflow-y-auto">
          {SHORTCUT_GROUPS.map((group) => (
            <div key={group.title}>
              <h3 className="text-xs uppercase tracking-wider font-semibold text-slate-400 dark:text-slate-500 mb-3">
                {group.title}
              </h3>
              <div className="space-y-2">
                {group.shortcuts.map((sc, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between py-1.5 border-b border-slate-100 dark:border-slate-800/60 last:border-0 text-xs"
                  >
                    <span className="text-slate-700 dark:text-slate-300 font-medium">{sc.description}</span>
                    <div className="flex items-center gap-1 shrink-0">
                      {sc.keys.map((k, ki) => (
                        <kbd
                          key={ki}
                          className="px-2 py-0.5 rounded text-[11px] font-mono bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700 shadow-xs"
                        >
                          {k}
                        </kbd>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-[#131b2c]/50 flex items-center justify-between text-[11px] text-slate-400 dark:text-slate-500">
          <span>Press <kbd className="px-1.5 py-0.5 rounded bg-slate-200/80 dark:bg-slate-800 font-mono text-[10px]">esc</kbd> to exit anytime</span>
          <span className="text-purple-600 dark:text-purple-400 font-medium">ADAM AI Sovereign</span>
        </div>
      </div>
    </div>
  );
}
