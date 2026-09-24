'use client';

import React from 'react';
import {
  Home,
  MessageSquare,
  Bot,
  FolderClosed,
  Share2,
  Database,
  CheckSquare,
  Settings,
  Sun,
  Moon,
  HelpCircle,
} from 'lucide-react';
import { useTheme } from './ThemeProvider';

export type NavTab = 'home' | 'docs' | 'network' | 'audit' | 'database' | 'review';

interface IconRailProps {
  activeTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  onToggleHistory: () => void;
  isHistoryOpen: boolean;
  onOpenSettings: () => void;
  onOpenShortcuts?: () => void;
  userName: string;
  clearanceLevel: string;
}

export default function IconRail({
  activeTab,
  onSelectTab,
  onToggleHistory,
  isHistoryOpen,
  onOpenSettings,
  onOpenShortcuts,
  userName,
  clearanceLevel,
}: IconRailProps) {
  const { resolvedTheme, toggleTheme } = useTheme();

  return (
    <aside className="w-[68px] h-full flex flex-col items-center justify-between py-4 border-r border-slate-200/80 dark:border-slate-800 bg-[#fbfcfe] dark:bg-[#0c111c] select-none z-20 shrink-0 transition-colors duration-150">
      {/* Top Canonical Theme Toggle */}
      <div className="flex flex-col items-center gap-4 w-full">
        <button
          type="button"
          onClick={toggleTheme}
          className="w-10 h-10 rounded-2xl bg-slate-100 hover:bg-slate-200 dark:bg-zinc-800 dark:hover:bg-zinc-700 border border-slate-200/80 dark:border-zinc-700/80 flex items-center justify-center shadow-xs hover:scale-[1.04] active:scale-95 transition-all group"
          title={`Switch to ${resolvedTheme === 'dark' ? 'Light' : 'Dark'} Mode`}
        >
          {resolvedTheme === 'dark' ? (
            <Sun className="w-5 h-5 text-amber-400 group-hover:rotate-45 transition-transform" />
          ) : (
            <Moon className="w-5 h-5 text-slate-700 group-hover:-rotate-12 transition-transform" />
          )}
        </button>

        {/* Primary Navigation Icons */}
        <nav className="flex flex-col items-center gap-1.5 w-full">
          {/* Home / Chat Studio */}
          <div className="relative flex items-center justify-center w-full">
            {activeTab === 'home' && !isHistoryOpen && (
              <span className="absolute left-0 w-1 h-5 bg-purple-600 dark:bg-purple-500 rounded-r-md" />
            )}
            <button
              type="button"
              onClick={() => onSelectTab('home')}
              className={`p-2.5 rounded-xl transition-all ${
                activeTab === 'home' && !isHistoryOpen
                  ? 'text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-950/50 shadow-xs font-semibold'
                  : 'text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800/60'
              }`}
              title="Chat Studio (⌘1)"
            >
              <Home className="w-5 h-5" />
            </button>
          </div>

          {/* Chat Threads Drawer Toggle */}
          <button
            type="button"
            onClick={onToggleHistory}
            className={`p-2.5 rounded-xl transition-all ${
              isHistoryOpen
                ? 'text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-950/50 shadow-xs'
                : 'text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800/60'
            }`}
            title="Chat History & Sessions"
          >
            <MessageSquare className="w-5 h-5" />
          </button>

          {/* Document Repository */}
          <div className="relative flex items-center justify-center w-full">
            {activeTab === 'docs' && (
              <span className="absolute left-0 w-1 h-5 bg-purple-600 dark:bg-purple-500 rounded-r-md" />
            )}
            <button
              type="button"
              onClick={() => onSelectTab('docs')}
              className={`p-2.5 rounded-xl transition-all ${
                activeTab === 'docs'
                  ? 'text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-950/50 shadow-xs'
                  : 'text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800/60'
              }`}
              title="Official Document Repository (⌘2)"
            >
              <FolderClosed className="w-5 h-5" />
            </button>
          </div>

          {/* Precedent Relationship Graph */}
          <div className="relative flex items-center justify-center w-full">
            {activeTab === 'network' && (
              <span className="absolute left-0 w-1 h-5 bg-purple-600 dark:bg-purple-500 rounded-r-md" />
            )}
            <button
              type="button"
              onClick={() => onSelectTab('network')}
              className={`p-2.5 rounded-xl transition-all ${
                activeTab === 'network'
                  ? 'text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-950/50 shadow-xs'
                  : 'text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800/60'
              }`}
              title="Precedent Chains & Supersession (⌘3)"
            >
              <Share2 className="w-5 h-5" />
            </button>
          </div>

          {/* Agent State Machine Executions & Audit */}
          <div className="relative flex items-center justify-center w-full">
            {activeTab === 'audit' && (
              <span className="absolute left-0 w-1 h-5 bg-purple-600 dark:bg-purple-500 rounded-r-md" />
            )}
            <button
              type="button"
              onClick={() => onSelectTab('audit')}
              className={`p-2.5 rounded-xl transition-all ${
                activeTab === 'audit'
                  ? 'text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-950/50 shadow-xs'
                  : 'text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800/60'
              }`}
              title="Agent Execution Audits & Benchmarks (⌘4)"
            >
              <Bot className="w-5 h-5" />
            </button>
          </div>

          {/* Data Acquisition Sources */}
          <div className="relative flex items-center justify-center w-full">
            {activeTab === 'database' && (
              <span className="absolute left-0 w-1 h-5 bg-purple-600 dark:bg-purple-500 rounded-r-md" />
            )}
            <button
              type="button"
              onClick={() => onSelectTab('database')}
              className={`p-2.5 rounded-xl transition-all ${
                activeTab === 'database'
                  ? 'text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-950/50 shadow-xs'
                  : 'text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800/60'
              }`}
              title="Data Acquisition & Connectors (⌘5)"
            >
              <Database className="w-5 h-5" />
            </button>
          </div>

          {/* Human QA Review Queue */}
          <div className="relative flex items-center justify-center w-full">
            {activeTab === 'review' && (
              <span className="absolute left-0 w-1 h-5 bg-purple-600 dark:bg-purple-500 rounded-r-md" />
            )}
            <button
              type="button"
              onClick={() => onSelectTab('review')}
              className={`p-2.5 rounded-xl transition-all ${
                activeTab === 'review'
                  ? 'text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-950/50 shadow-xs'
                  : 'text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800/60'
              }`}
              title="Human-in-the-Loop QA Queue (⌘6)"
            >
              <CheckSquare className="w-5 h-5" />
            </button>
          </div>
        </nav>
      </div>

      {/* Bottom Profile, Shortcuts & Settings */}
      <div className="flex flex-col items-center gap-2.5 w-full">
        {/* Keyboard Shortcuts Trigger */}
        {onOpenShortcuts && (
          <button
            type="button"
            onClick={onOpenShortcuts}
            className="p-2 rounded-xl text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800/60 transition-all"
            title="Keyboard Shortcuts (⌘/)"
          >
            <HelpCircle className="w-4 h-4" />
          </button>
        )}

        {/* Settings button */}
        <button
          type="button"
          onClick={onOpenSettings}
          className="p-2 rounded-xl text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800/60 transition-all"
          title="Officer Settings & Security Clearance"
        >
          <Settings className="w-4 h-4" />
        </button>

        {/* User Clearance Avatar Pill */}
        <button
          type="button"
          onClick={onOpenSettings}
          className="relative group p-0.5 rounded-full transition-transform hover:scale-105 mt-1"
          title={`${userName} (${clearanceLevel} Clearance)`}
        >
          <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-purple-600 to-indigo-600 flex items-center justify-center text-white text-xs font-bold shadow-xs">
            {userName[0]?.toUpperCase() || 'O'}
          </div>
          {clearanceLevel !== 'PUBLIC' && (
            <span
              className="absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 bg-amber-500 rounded-full border-2 border-white dark:border-[#0c111c] flex items-center justify-center text-[8px] text-white font-bold"
              title={clearanceLevel}
            >
              ★
            </span>
          )}
        </button>
      </div>
    </aside>
  );
}
