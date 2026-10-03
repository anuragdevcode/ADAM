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
  LogOut,
  Plus,
} from 'lucide-react';
import { useTheme } from './ThemeProvider';

export type NavTab = 'home' | 'docs' | 'network' | 'audit' | 'database' | 'review';

interface IconRailProps {
  activeTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  onToggleHistory: () => void;
  isHistoryOpen: boolean;
  onNewThread?: () => void;
  onOpenSettings: () => void;
  onOpenShortcuts?: () => void;
  onSignOut?: () => void;
  userName: string;
  clearanceLevel: string;
}

export default function IconRail({
  activeTab,
  onSelectTab,
  onToggleHistory,
  isHistoryOpen,
  onNewThread,
  onOpenSettings,
  onOpenShortcuts,
  onSignOut,
  userName,
  clearanceLevel,
}: IconRailProps) {
  const { resolvedTheme, toggleTheme } = useTheme();

  const handleNewChatClick = () => {
    if (onNewThread) {
      onNewThread();
    } else {
      onSelectTab('home');
    }
  };

  return (
    <aside className="w-[68px] h-full flex flex-col items-center justify-between py-4 border-r border-slate-200/80 dark:border-slate-800 bg-[#fbfcfe] dark:bg-[#0c111c] select-none z-20 shrink-0 transition-colors duration-200">
      {/* Top Utility Controls: Theme Toggle & Kinetic New Chat */}
      <div className="flex flex-col items-center gap-3 w-full">
        {/* Canonical Theme Toggle */}
        <button
          type="button"
          onClick={toggleTheme}
          className="group relative w-10 h-10 rounded-2xl bg-slate-100 hover:bg-slate-200/90 dark:bg-zinc-800 dark:hover:bg-zinc-700/90 border border-slate-200/80 dark:border-zinc-700/80 hover:border-purple-300/50 dark:hover:border-purple-500/40 hover:shadow-[0_0_18px_-2px_rgba(168,85,247,0.3)] flex items-center justify-center shadow-xs hover:scale-105 active:scale-90 transition-all duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] cursor-pointer"
          title={`Switch to ${resolvedTheme === 'dark' ? 'Light' : 'Dark'} Mode`}
          aria-label="Toggle theme"
        >
          {resolvedTheme === 'dark' ? (
            <Sun className="w-5 h-5 text-amber-400 group-hover:rotate-45 group-hover:scale-110 transition-transform duration-300 ease-out" />
          ) : (
            <Moon className="w-5 h-5 text-slate-700 group-hover:-rotate-45 group-hover:scale-110 transition-transform duration-300 ease-out" />
          )}
        </button>

        {/* Dedicated Kinetic New Chat (+) Button */}
        <button
          type="button"
          onClick={handleNewChatClick}
          className="group relative w-10 h-10 rounded-2xl bg-white dark:bg-zinc-800/80 hover:bg-purple-50/70 dark:hover:bg-purple-950/40 border border-slate-200/90 dark:border-zinc-700/80 hover:border-purple-300/60 dark:hover:border-purple-500/50 flex items-center justify-center text-purple-600 dark:text-purple-400 shadow-xs hover:shadow-[0_0_18px_-2px_rgba(168,85,247,0.35)] hover:scale-105 active:scale-90 transition-all duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] cursor-pointer"
          title="New Chat (⌘N)"
          aria-label="New Chat (⌘N)"
        >
          <Plus className="w-5 h-5 transition-transform duration-300 ease-out group-hover:rotate-90 group-hover:scale-110" />
        </button>

        {/* Subtle Horizontal Divider */}
        <div className="w-8 h-[1px] bg-gradient-to-r from-transparent via-slate-200 dark:via-slate-800 to-transparent my-0.5" />

        {/* Primary Navigation Icons & Secondary Drawer Action */}
        <nav className="flex flex-col items-center gap-1.5 w-full">
          {/* Home / Chat Studio (Primary Tab) */}
          <div className="relative flex items-center justify-center w-full">
            {activeTab === 'home' && (
              <span className="absolute left-0 w-1 h-6 bg-purple-600 dark:bg-purple-500 rounded-r-full shadow-[0_0_12px_rgba(168,85,247,0.85)] animate-rail-pill transition-all" />
            )}
            <button
              type="button"
              onClick={() => onSelectTab('home')}
              className={`group relative p-2.5 rounded-xl hover:scale-105 active:scale-95 transition-all duration-200 ease-[cubic-bezier(0.34,1.56,0.64,1)] ${
                activeTab === 'home'
                  ? 'text-purple-600 dark:text-purple-400 bg-purple-50/90 dark:bg-purple-950/60 font-semibold border border-purple-200/50 dark:border-purple-800/40 reflection-glow-subtle shadow-xs'
                  : 'text-slate-400 dark:text-slate-500 hover:text-purple-600 dark:hover:text-purple-300 hover:bg-purple-50/40 dark:hover:bg-purple-950/30 hover:shadow-[0_0_14px_-2px_rgba(168,85,247,0.22)] border border-transparent'
              }`}
              title="Chat Studio (⌘1)"
              aria-label="Chat Studio (⌘1)"
            >
              <Home className="w-5 h-5 transition-transform duration-200 ease-out group-hover:scale-110" />
            </button>
          </div>

          {/* Chat Threads Drawer Toggle (Secondary Drawer Action) */}
          <div className="relative flex items-center justify-center w-full">
            <button
              type="button"
              onClick={onToggleHistory}
              className={`group relative p-2.5 rounded-xl hover:scale-105 active:scale-95 transition-all duration-200 ease-[cubic-bezier(0.34,1.56,0.64,1)] ${
                isHistoryOpen
                  ? 'text-purple-600 dark:text-purple-300 bg-purple-500/10 dark:bg-purple-500/15 border border-purple-300/40 dark:border-purple-600/30 ring-1 ring-purple-400/20 shadow-xs'
                  : 'text-slate-400 dark:text-slate-500 hover:text-purple-600 dark:hover:text-purple-300 hover:bg-purple-50/40 dark:hover:bg-purple-950/30 hover:shadow-[0_0_14px_-2px_rgba(168,85,247,0.22)] border border-transparent'
              }`}
              title={isHistoryOpen ? 'Close Chat Threads (Esc)' : 'Chat History & Sessions'}
              aria-label="Chat History & Sessions"
            >
              <MessageSquare className="w-5 h-5 transition-transform duration-200 ease-out group-hover:scale-110" />
              {isHistoryOpen && (
                <span className="absolute top-1.5 right-1.5 w-1.5 h-1.5 bg-purple-500 dark:bg-purple-400 rounded-full shadow-[0_0_6px_rgba(168,85,247,0.85)] animate-pulse" />
              )}
            </button>
          </div>

          {/* Document Repository (Primary Tab) */}
          <div className="relative flex items-center justify-center w-full">
            {activeTab === 'docs' && (
              <span className="absolute left-0 w-1 h-6 bg-purple-600 dark:bg-purple-500 rounded-r-full shadow-[0_0_12px_rgba(168,85,247,0.85)] animate-rail-pill transition-all" />
            )}
            <button
              type="button"
              onClick={() => onSelectTab('docs')}
              className={`group relative p-2.5 rounded-xl hover:scale-105 active:scale-95 transition-all duration-200 ease-[cubic-bezier(0.34,1.56,0.64,1)] ${
                activeTab === 'docs'
                  ? 'text-purple-600 dark:text-purple-400 bg-purple-50/90 dark:bg-purple-950/60 font-semibold border border-purple-200/50 dark:border-purple-800/40 reflection-glow-subtle shadow-xs'
                  : 'text-slate-400 dark:text-slate-500 hover:text-purple-600 dark:hover:text-purple-300 hover:bg-purple-50/40 dark:hover:bg-purple-950/30 hover:shadow-[0_0_14px_-2px_rgba(168,85,247,0.22)] border border-transparent'
              }`}
              title="Official Document Repository (⌘2)"
              aria-label="Official Document Repository (⌘2)"
            >
              <FolderClosed className="w-5 h-5 transition-transform duration-200 ease-out group-hover:scale-110" />
            </button>
          </div>

          {/* Precedent Relationship Graph (Primary Tab) */}
          <div className="relative flex items-center justify-center w-full">
            {activeTab === 'network' && (
              <span className="absolute left-0 w-1 h-6 bg-purple-600 dark:bg-purple-500 rounded-r-full shadow-[0_0_12px_rgba(168,85,247,0.85)] animate-rail-pill transition-all" />
            )}
            <button
              type="button"
              onClick={() => onSelectTab('network')}
              className={`group relative p-2.5 rounded-xl hover:scale-105 active:scale-95 transition-all duration-200 ease-[cubic-bezier(0.34,1.56,0.64,1)] ${
                activeTab === 'network'
                  ? 'text-purple-600 dark:text-purple-400 bg-purple-50/90 dark:bg-purple-950/60 font-semibold border border-purple-200/50 dark:border-purple-800/40 reflection-glow-subtle shadow-xs'
                  : 'text-slate-400 dark:text-slate-500 hover:text-purple-600 dark:hover:text-purple-300 hover:bg-purple-50/40 dark:hover:bg-purple-950/30 hover:shadow-[0_0_14px_-2px_rgba(168,85,247,0.22)] border border-transparent'
              }`}
              title="Precedent Chains & Supersession (⌘3)"
              aria-label="Precedent Chains & Supersession (⌘3)"
            >
              <Share2 className="w-5 h-5 transition-transform duration-200 ease-out group-hover:scale-110" />
            </button>
          </div>

          {/* Agent State Machine Executions & Audit (Primary Tab) */}
          <div className="relative flex items-center justify-center w-full">
            {activeTab === 'audit' && (
              <span className="absolute left-0 w-1 h-6 bg-purple-600 dark:bg-purple-500 rounded-r-full shadow-[0_0_12px_rgba(168,85,247,0.85)] animate-rail-pill transition-all" />
            )}
            <button
              type="button"
              onClick={() => onSelectTab('audit')}
              className={`group relative p-2.5 rounded-xl hover:scale-105 active:scale-95 transition-all duration-200 ease-[cubic-bezier(0.34,1.56,0.64,1)] ${
                activeTab === 'audit'
                  ? 'text-purple-600 dark:text-purple-400 bg-purple-50/90 dark:bg-purple-950/60 font-semibold border border-purple-200/50 dark:border-purple-800/40 reflection-glow-subtle shadow-xs'
                  : 'text-slate-400 dark:text-slate-500 hover:text-purple-600 dark:hover:text-purple-300 hover:bg-purple-50/40 dark:hover:bg-purple-950/30 hover:shadow-[0_0_14px_-2px_rgba(168,85,247,0.22)] border border-transparent'
              }`}
              title="Agent Execution Audits & Benchmarks (⌘4)"
              aria-label="Agent Execution Audits & Benchmarks (⌘4)"
            >
              <Bot className="w-5 h-5 transition-transform duration-200 ease-out group-hover:scale-110" />
            </button>
          </div>

          {/* Data Acquisition Sources (Primary Tab) */}
          <div className="relative flex items-center justify-center w-full">
            {activeTab === 'database' && (
              <span className="absolute left-0 w-1 h-6 bg-purple-600 dark:bg-purple-500 rounded-r-full shadow-[0_0_12px_rgba(168,85,247,0.85)] animate-rail-pill transition-all" />
            )}
            <button
              type="button"
              onClick={() => onSelectTab('database')}
              className={`group relative p-2.5 rounded-xl hover:scale-105 active:scale-95 transition-all duration-200 ease-[cubic-bezier(0.34,1.56,0.64,1)] ${
                activeTab === 'database'
                  ? 'text-purple-600 dark:text-purple-400 bg-purple-50/90 dark:bg-purple-950/60 font-semibold border border-purple-200/50 dark:border-purple-800/40 reflection-glow-subtle shadow-xs'
                  : 'text-slate-400 dark:text-slate-500 hover:text-purple-600 dark:hover:text-purple-300 hover:bg-purple-50/40 dark:hover:bg-purple-950/30 hover:shadow-[0_0_14px_-2px_rgba(168,85,247,0.22)] border border-transparent'
              }`}
              title="Data Acquisition & Connectors (⌘5)"
              aria-label="Data Acquisition & Connectors (⌘5)"
            >
              <Database className="w-5 h-5 transition-transform duration-200 ease-out group-hover:scale-110" />
            </button>
          </div>

          {/* Human QA Review Queue (Primary Tab) */}
          <div className="relative flex items-center justify-center w-full">
            {activeTab === 'review' && (
              <span className="absolute left-0 w-1 h-6 bg-purple-600 dark:bg-purple-500 rounded-r-full shadow-[0_0_12px_rgba(168,85,247,0.85)] animate-rail-pill transition-all" />
            )}
            <button
              type="button"
              onClick={() => onSelectTab('review')}
              className={`group relative p-2.5 rounded-xl hover:scale-105 active:scale-95 transition-all duration-200 ease-[cubic-bezier(0.34,1.56,0.64,1)] ${
                activeTab === 'review'
                  ? 'text-purple-600 dark:text-purple-400 bg-purple-50/90 dark:bg-purple-950/60 font-semibold border border-purple-200/50 dark:border-purple-800/40 reflection-glow-subtle shadow-xs'
                  : 'text-slate-400 dark:text-slate-500 hover:text-purple-600 dark:hover:text-purple-300 hover:bg-purple-50/40 dark:hover:bg-purple-950/30 hover:shadow-[0_0_14px_-2px_rgba(168,85,247,0.22)] border border-transparent'
              }`}
              title="Human-in-the-Loop QA Queue (⌘6)"
              aria-label="Human-in-the-Loop QA Queue (⌘6)"
            >
              <CheckSquare className="w-5 h-5 transition-transform duration-200 ease-out group-hover:scale-110" />
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
            className="group p-2 rounded-xl text-slate-400 dark:text-slate-500 hover:text-purple-600 dark:hover:text-purple-300 hover:bg-purple-50/40 dark:hover:bg-purple-950/30 hover:shadow-[0_0_14px_-2px_rgba(168,85,247,0.22)] hover:scale-105 active:scale-95 transition-all duration-200 cursor-pointer"
            title="Keyboard Shortcuts (⌘/)"
            aria-label="Keyboard Shortcuts (⌘/)"
          >
            <HelpCircle className="w-4 h-4 transition-transform duration-200 ease-out group-hover:scale-110 group-hover:rotate-12" />
          </button>
        )}

        {/* Settings button */}
        <button
          type="button"
          onClick={onOpenSettings}
          className="group p-2 rounded-xl text-slate-400 dark:text-slate-500 hover:text-purple-600 dark:hover:text-purple-300 hover:bg-purple-50/40 dark:hover:bg-purple-950/30 hover:shadow-[0_0_14px_-2px_rgba(168,85,247,0.22)] hover:scale-105 active:scale-95 transition-all duration-200 cursor-pointer"
          title="Officer Settings & Security Clearance (⌘,)"
          aria-label="Settings & Security Clearance"
        >
          <Settings className="w-4 h-4 transition-transform duration-300 ease-out group-hover:rotate-45 group-hover:scale-110" />
        </button>

        {/* User Clearance Avatar Pill */}
        <button
          type="button"
          onClick={onOpenSettings}
          className="relative group p-0.5 rounded-full hover:scale-110 active:scale-95 transition-all duration-300 ease-[cubic-bezier(0.34,1.56,0.64,1)] mt-1 cursor-pointer"
          title={`${userName} (${clearanceLevel} Clearance)`}
          aria-label={`Officer profile: ${userName}`}
        >
          <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-purple-600 via-indigo-600 to-purple-500 group-hover:shadow-[0_0_20px_rgba(168,85,247,0.6)] flex items-center justify-center text-white text-xs font-bold shadow-xs transition-shadow duration-300">
            {userName[0]?.toUpperCase() || 'O'}
          </div>
          {clearanceLevel !== 'PUBLIC' && (
            <span
              className="absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 bg-amber-500 rounded-full border-2 border-white dark:border-[#0c111c] flex items-center justify-center text-[8px] text-white font-bold shadow-xs group-hover:scale-110 transition-transform duration-200"
              title={clearanceLevel}
            >
              ★
            </span>
          )}
        </button>

        {/* Sign Out Trigger */}
        {onSignOut && (
          <button
            type="button"
            onClick={onSignOut}
            className="group p-2 rounded-xl text-slate-400 hover:text-rose-600 dark:text-slate-500 dark:hover:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/40 hover:scale-105 active:scale-95 transition-all duration-200 cursor-pointer"
            title="Sign Out / Switch Officer"
            aria-label="Sign Out"
          >
            <LogOut className="w-3.5 h-3.5 transition-transform duration-200 ease-out group-hover:translate-x-0.5 group-hover:scale-110" />
          </button>
        )}
      </div>
    </aside>
  );
}
