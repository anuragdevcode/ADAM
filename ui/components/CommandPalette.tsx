'use client';

import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  Search,
  MessageSquare,
  FolderClosed,
  Share2,
  Bot,
  Database,
  CheckSquare,
  Sparkles,
  Plus,
  Shield,
  Key,
  Activity,
  SlidersHorizontal,
  Sun,
  Moon,
  Laptop,
  ArrowRight,
  HelpCircle,
  X,
} from 'lucide-react';
import type { NavTab } from './IconRail';
import type { ModelInfo, DepartmentItem } from '@/lib/types';
import { useTheme } from './ThemeProvider';

interface CommandPaletteProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectNav: (tab: NavTab) => void;
  onNewThread: () => void;
  models: ModelInfo[];
  selectedModel: ModelInfo | null;
  onSelectModel: (model: ModelInfo) => void;
  departments: DepartmentItem[];
  selectedDept?: string;
  onSelectDept?: (deptId: string) => void;
  onOpenSettings: (tab?: 'general' | 'inference' | 'providers' | 'hardware' | 'telemetry') => void;
  onOpenApiKey?: () => void;
  onOpenIntrospection?: () => void;
  onOpenAdvancedSettings?: () => void;
  onOpenShortcuts: () => void;
}

interface PaletteAction {
  id: string;
  category: 'Navigation' | 'Actions' | 'Models' | 'Scope' | 'Theme & Governance';
  title: string;
  subtitle?: string;
  icon: React.ComponentType<{ className?: string }>;
  shortcut?: string;
  badge?: string;
  action: () => void;
}

export default function CommandPalette({
  isOpen,
  onClose,
  onSelectNav,
  onNewThread,
  models,
  selectedModel,
  onSelectModel,
  departments,
  selectedDept,
  onSelectDept,
  onOpenSettings,
  onOpenApiKey,
  onOpenIntrospection,
  onOpenAdvancedSettings,
  onOpenShortcuts,
}: CommandPaletteProps) {
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const { theme, setTheme, resolvedTheme } = useTheme();

  // Reset query and focus on open
  useEffect(() => {
    if (isOpen) {
      setQuery('');
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  // Construct comprehensive action registry
  const allActions: PaletteAction[] = useMemo(() => {
    const actions: PaletteAction[] = [
      // Primary Actions
      {
        id: 'new-thread',
        category: 'Actions',
        title: 'New Chat Thread',
        subtitle: 'Start a fresh conversation session with sovereign verification',
        icon: Plus,
        shortcut: '⌘N',
        action: () => {
          onNewThread();
          onClose();
        },
      },
      {
        id: 'nav-home',
        category: 'Navigation',
        title: 'Chat Studio',
        subtitle: 'Interactive Q&A for Uttarakhand Government Orders and circulars',
        icon: MessageSquare,
        shortcut: '1',
        action: () => {
          onSelectNav('home');
          onClose();
        },
      },
      {
        id: 'nav-docs',
        category: 'Navigation',
        title: 'Official Document Repository',
        subtitle: 'Browse, search, and verify ingested government orders',
        icon: FolderClosed,
        shortcut: '2',
        action: () => {
          onSelectNav('docs');
          onClose();
        },
      },
      {
        id: 'nav-network',
        category: 'Navigation',
        title: 'Precedents & Supersession Chains',
        subtitle: 'View legal chains, amendments, and superseding relationships',
        icon: Share2,
        shortcut: '3',
        action: () => {
          onSelectNav('network');
          onClose();
        },
      },
      {
        id: 'nav-audit',
        category: 'Navigation',
        title: 'Agent Execution Audits & Benchmarks',
        subtitle: 'Immutable latency, token telemetry, and Pilot Gate scorecard',
        icon: Bot,
        shortcut: '4',
        action: () => {
          onSelectNav('audit');
          onClose();
        },
      },
      {
        id: 'nav-database',
        category: 'Navigation',
        title: 'Data Acquisition & Connectors',
        subtitle: 'Manage eKosh, UKRD, eGazette, and automated crawler jobs',
        icon: Database,
        shortcut: '5',
        action: () => {
          onSelectNav('database');
          onClose();
        },
      },
      {
        id: 'nav-review',
        category: 'Navigation',
        title: 'Human-in-the-Loop QA Queue',
        subtitle: 'Review low-confidence transcripts and perform corrections',
        icon: CheckSquare,
        shortcut: '6',
        action: () => {
          onSelectNav('review');
          onClose();
        },
      },

      // Theme Toggles
      {
        id: 'theme-toggle',
        category: 'Theme & Governance',
        title: resolvedTheme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode',
        subtitle: `Currently using ${theme} theme (${resolvedTheme} active)`,
        icon: resolvedTheme === 'dark' ? Sun : Moon,
        action: () => {
          setTheme(resolvedTheme === 'dark' ? 'light' : 'dark');
          onClose();
        },
      },
      {
        id: 'theme-system',
        category: 'Theme & Governance',
        title: 'Use System Theme Preference',
        subtitle: 'Automatically match your operating system appearance',
        icon: Laptop,
        action: () => {
          setTheme('system');
          onClose();
        },
      },

      // Governance & Settings
      {
        id: 'gov-settings',
        category: 'Theme & Governance',
        title: 'Officer Context & Security Clearance',
        subtitle: 'Manage identity, classification clearance, and memory governance',
        icon: Shield,
        action: () => {
          onOpenSettings('general');
          onClose();
        },
      },
      {
        id: 'api-key-config',
        category: 'Theme & Governance',
        title: 'Configure Google Gemini API Key',
        subtitle: 'Set or update cloud inference and voice API keys',
        icon: Key,
        action: () => {
          if (onOpenApiKey) onOpenApiKey();
          else onOpenSettings('providers');
          onClose();
        },
      },
      {
        id: 'sys-introspection',
        category: 'Theme & Governance',
        title: 'System Introspection & Self-Model',
        subtitle: 'View live runtime diagnostics, security bounds, and pipeline graph',
        icon: Activity,
        action: () => {
          if (onOpenIntrospection) onOpenIntrospection();
          else onOpenSettings('telemetry');
          onClose();
        },
      },
      {
        id: 'adv-settings',
        category: 'Theme & Governance',
        title: 'Advanced Settings & Profile Tuner',
        subtitle: 'Tune retrieval weights, agent depth, and response styles',
        icon: SlidersHorizontal,
        action: () => {
          if (onOpenAdvancedSettings) onOpenAdvancedSettings();
          else onOpenSettings('inference');
          onClose();
        },
      },
      {
        id: 'view-shortcuts',
        category: 'Actions',
        title: 'Keyboard Shortcuts Cheat-sheet',
        subtitle: 'View all keyboard commands available in ADAM',
        icon: HelpCircle,
        shortcut: '⌘/',
        action: () => {
          onOpenShortcuts();
          onClose();
        },
      },
    ];

    // Add Models
    models.forEach((m) => {
      const isSelected = selectedModel?.id === m.id;
      actions.push({
        id: `model-${m.id}`,
        category: 'Models',
        title: `Model: ${m.name}`,
        subtitle: `${m.is_cloud ? 'Remote Google Cloud' : 'Local Sovereign Host'} • ${m.quantization || 'Q4'}`,
        icon: Sparkles,
        badge: isSelected ? 'Active' : m.is_cloud ? 'Cloud' : 'Local',
        action: () => {
          onSelectModel(m);
          onClose();
        },
      });
    });

    // Add Department Scopes
    if (onSelectDept) {
      actions.push({
        id: 'dept-all',
        category: 'Scope',
        title: 'Scope: All Uttarakhand Departments',
        subtitle: 'Broad administrative search across all sectors',
        icon: Database,
        badge: selectedDept === 'ALL' ? 'Active' : undefined,
        action: () => {
          onSelectDept('ALL');
          onClose();
        },
      });

      departments.forEach((d) => {
        actions.push({
          id: `dept-${d.id}`,
          category: 'Scope',
          title: `Scope: ${d.label}`,
          subtitle: `Filter queries specifically to ${d.label}`,
          icon: Database,
          badge: selectedDept === d.id ? 'Active' : undefined,
          action: () => {
            onSelectDept(d.id);
            onClose();
          },
        });
      });
    }

    return actions;
  }, [
    models,
    selectedModel,
    departments,
    selectedDept,
    theme,
    resolvedTheme,
    onNewThread,
    onSelectNav,
    onClose,
    onSelectModel,
    onSelectDept,
    onOpenSettings,
    onOpenApiKey,
    onOpenIntrospection,
    onOpenAdvancedSettings,
    onOpenShortcuts,
    setTheme,
  ]);

  // Filter actions based on query
  const filteredActions = useMemo(() => {
    if (!query.trim()) return allActions;
    const q = query.toLowerCase();
    return allActions.filter(
      (a) =>
        a.title.toLowerCase().includes(q) ||
        (a.subtitle && a.subtitle.toLowerCase().includes(q)) ||
        a.category.toLowerCase().includes(q),
    );
  }, [allActions, query]);

  // Handle keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev + 1) % (filteredActions.length || 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev - 1 + filteredActions.length) % (filteredActions.length || 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (filteredActions[selectedIndex]) {
        filteredActions[selectedIndex].action();
      }
    } else if (e.key === 'Escape') {
      e.preventDefault();
      onClose();
    }
  };

  // Keep selected item scrolled into view
  useEffect(() => {
    if (listRef.current) {
      const selectedEl = listRef.current.querySelector(`[data-index="${selectedIndex}"]`) as HTMLElement;
      if (selectedEl) {
        selectedEl.scrollIntoView({ block: 'nearest' });
      }
    }
  }, [selectedIndex]);

  if (!isOpen) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Command Palette"
      className="fixed inset-0 z-50 flex items-start justify-center pt-20 px-4 bg-slate-950/40 dark:bg-black/60 backdrop-blur-sm animate-in fade-in duration-100"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-2xl bg-white dark:bg-[#111726] rounded-2xl border border-slate-200 dark:border-slate-800 shadow-2xl overflow-hidden flex flex-col max-h-[75vh] animate-in zoom-in-95 duration-100"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search Input Bar */}
        <div className="flex items-center gap-3 px-4 py-3.5 border-b border-slate-100 dark:border-slate-800/80 bg-slate-50/50 dark:bg-[#131b2c]/50">
          <Search className="w-5 h-5 text-slate-400 dark:text-slate-500 shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedIndex(0);
            }}
            onKeyDown={handleKeyDown}
            placeholder="Type a command, search views, models, departments…"
            className="w-full bg-transparent text-sm text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 outline-none"
          />
          {query && (
            <button
              type="button"
              onClick={() => {
                setQuery('');
                setSelectedIndex(0);
                inputRef.current?.focus();
              }}
              className="p-1 rounded-md text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
            >
              <X className="w-4 h-4" />
            </button>
          )}
          <kbd className="hidden sm:inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-200/80 dark:bg-slate-800 text-slate-500 dark:text-slate-400 border border-slate-300 dark:border-slate-700">
            ESC
          </kbd>
        </div>

        {/* Results List */}
        <div ref={listRef} className="flex-1 overflow-y-auto p-2 divide-y divide-slate-100 dark:divide-slate-800/50">
          {filteredActions.length === 0 ? (
            <div className="py-12 text-center text-xs text-slate-400 dark:text-slate-500">
              No matching commands or actions found for &quot;{query}&quot;.
            </div>
          ) : (
            (() => {
              let lastCat: string | null = null;
              return filteredActions.map((item, idx) => {
                const IconComponent = item.icon;
                const isSelected = idx === selectedIndex;
                const showCatHeader = item.category !== lastCat;
                lastCat = item.category;

                return (
                  <div key={item.id} className="pt-1">
                    {showCatHeader && (
                      <div className="px-3 pt-2 pb-1 text-[10px] uppercase tracking-wider font-semibold text-slate-400 dark:text-slate-500">
                        {item.category}
                      </div>
                    )}
                    <button
                      type="button"
                      data-index={idx}
                      onClick={() => item.action()}
                      onMouseEnter={() => setSelectedIndex(idx)}
                      className={`w-full flex items-center justify-between px-3 py-2.5 rounded-xl text-left text-xs transition-colors ${
                        isSelected
                          ? 'bg-purple-50 dark:bg-purple-950/40 text-purple-950 dark:text-purple-200'
                          : 'text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800/40'
                      }`}
                    >
                      <div className="flex items-center gap-3 min-w-0 pr-2">
                        <div
                          className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${
                            isSelected
                              ? 'bg-purple-600 text-white'
                              : 'bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400'
                          }`}
                        >
                          <IconComponent className="w-3.5 h-3.5" />
                        </div>
                        <div className="min-w-0">
                          <p className="font-medium truncate text-slate-900 dark:text-slate-100">{item.title}</p>
                          {item.subtitle && (
                            <p className="text-[11px] text-slate-400 dark:text-slate-500 truncate mt-0.5">
                              {item.subtitle}
                            </p>
                          )}
                        </div>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        {item.badge && (
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-semibold ${
                              item.badge === 'Active'
                                ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800'
                                : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400'
                            }`}
                          >
                            {item.badge}
                          </span>
                        )}
                        {item.shortcut && (
                          <kbd className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 border border-slate-200 dark:border-slate-700">
                            {item.shortcut}
                          </kbd>
                        )}
                        {isSelected && <ArrowRight className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400" />}
                      </div>
                    </button>
                  </div>
                );
              });
            })()
          )}
        </div>

        {/* Footer Hints */}
        <div className="px-4 py-2.5 border-t border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-[#131b2c]/50 flex items-center justify-between text-[11px] text-slate-400 dark:text-slate-500">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 rounded bg-slate-200/80 dark:bg-slate-800 text-[10px] font-mono">↑↓</kbd> navigate
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 rounded bg-slate-200/80 dark:bg-slate-800 text-[10px] font-mono">↵</kbd> select
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-1 py-0.5 rounded bg-slate-200/80 dark:bg-slate-800 text-[10px] font-mono">esc</kbd> close
            </span>
          </div>
          <span className="font-medium text-purple-700 dark:text-purple-400">ADAM Command OS</span>
        </div>
      </div>
    </div>
  );
}
