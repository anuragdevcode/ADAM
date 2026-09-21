'use client';

import {
  Home,
  MessageSquare,
  Bot,
  FolderClosed,
  Share2,
  Database,
  CheckSquare,
  Settings,
} from 'lucide-react';

export type NavTab = 'home' | 'docs' | 'network' | 'audit' | 'database' | 'review';

interface IconRailProps {
  activeTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  onToggleHistory: () => void;
  isHistoryOpen: boolean;
  onOpenSettings: () => void;
  userName: string;
  clearanceLevel: string;
}

export default function IconRail({
  activeTab,
  onSelectTab,
  onToggleHistory,
  isHistoryOpen,
  onOpenSettings,
  userName,
  clearanceLevel,
}: IconRailProps) {
  return (
    <aside className="w-[68px] h-full flex flex-col items-center justify-between py-5 border-r border-[#eaecf0] bg-[#fcfcfd] select-none z-20 shrink-0">
      {/* Top Brand Logo */}
      <div className="flex flex-col items-center gap-5 w-full">
        <button
          onClick={() => onSelectTab('home')}
          className="w-9 h-9 rounded-xl bg-[#1d2939] flex items-center justify-center text-white shadow-sm hover:bg-black transition-colors"
          title="ADAM — Uttarakhand Gov Records AI"
        >
          <svg
            className="w-5 h-5 text-white"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="12" cy="12" r="4" />
            <path d="M12 2v2" />
            <path d="M12 20v2" />
            <path d="m4.93 4.93 1.41 1.41" />
            <path d="m17.66 17.66 1.41 1.41" />
            <path d="M2 12h2" />
            <path d="M20 12h2" />
            <path d="m6.34 17.66-1.41 1.41" />
            <path d="m19.07 4.93-1.41 1.41" />
          </svg>
        </button>

        {/* Primary Navigation Icons */}
        <nav className="flex flex-col items-center gap-2.5 w-full">
          {/* Home / Chat Studio */}
          <div className="relative flex items-center justify-center w-full">
            {activeTab === 'home' && !isHistoryOpen && (
              <span className="absolute left-0 w-1 h-5 bg-purple-600 rounded-r-md" />
            )}
            <button
              onClick={() => onSelectTab('home')}
              className={`p-2.5 rounded-xl transition-all ${
                activeTab === 'home' && !isHistoryOpen
                  ? 'text-purple-600 bg-purple-50/80 shadow-xs'
                  : 'text-gray-400 hover:text-gray-700 hover:bg-gray-100/70'
              }`}
              title="Chat Studio"
            >
              <Home className="w-5 h-5" />
            </button>
          </div>

          {/* Chat Threads Drawer Toggle */}
          <button
            onClick={onToggleHistory}
            className={`p-2.5 rounded-xl transition-all ${
              isHistoryOpen
                ? 'text-purple-600 bg-purple-50/80 shadow-xs'
                : 'text-gray-400 hover:text-gray-700 hover:bg-gray-100/70'
            }`}
            title="Chat Sessions & Threads"
          >
            <MessageSquare className="w-5 h-5" />
          </button>

          {/* Document Repository */}
          <div className="relative flex items-center justify-center w-full">
            {activeTab === 'docs' && (
              <span className="absolute left-0 w-1 h-5 bg-purple-600 rounded-r-md" />
            )}
            <button
              onClick={() => onSelectTab('docs')}
              className={`p-2.5 rounded-xl transition-all ${
                activeTab === 'docs'
                  ? 'text-purple-600 bg-purple-50/80 shadow-xs'
                  : 'text-gray-400 hover:text-gray-700 hover:bg-gray-100/70'
              }`}
              title="Official Document Repository"
            >
              <FolderClosed className="w-5 h-5" />
            </button>
          </div>

          {/* Precedent Relationship Graph */}
          <div className="relative flex items-center justify-center w-full">
            {activeTab === 'network' && (
              <span className="absolute left-0 w-1 h-5 bg-purple-600 rounded-r-md" />
            )}
            <button
              onClick={() => onSelectTab('network')}
              className={`p-2.5 rounded-xl transition-all ${
                activeTab === 'network'
                  ? 'text-purple-600 bg-purple-50/80 shadow-xs'
                  : 'text-gray-400 hover:text-gray-700 hover:bg-gray-100/70'
              }`}
              title="Precedent Chains & Supersession"
            >
              <Share2 className="w-5 h-5" />
            </button>
          </div>

          {/* Agent State Machine Executions & Audit */}
          <div className="relative flex items-center justify-center w-full">
            {activeTab === 'audit' && (
              <span className="absolute left-0 w-1 h-5 bg-purple-600 rounded-r-md" />
            )}
            <button
              onClick={() => onSelectTab('audit')}
              className={`p-2.5 rounded-xl transition-all ${
                activeTab === 'audit'
                  ? 'text-purple-600 bg-purple-50/80 shadow-xs'
                  : 'text-gray-400 hover:text-gray-700 hover:bg-gray-100/70'
              }`}
              title="Agent Execution Audits"
            >
              <Bot className="w-5 h-5" />
            </button>
          </div>

          {/* Data Acquisition Sources */}
          <div className="relative flex items-center justify-center w-full">
            {activeTab === 'database' && (
              <span className="absolute left-0 w-1 h-5 bg-purple-600 rounded-r-md" />
            )}
            <button
              onClick={() => onSelectTab('database')}
              className={`p-2.5 rounded-xl transition-all ${
                activeTab === 'database'
                  ? 'text-purple-600 bg-purple-50/80 shadow-xs'
                  : 'text-gray-400 hover:text-gray-700 hover:bg-gray-100/70'
              }`}
              title="Data Acquisition Sources"
            >
              <Database className="w-5 h-5" />
            </button>
          </div>

          {/* Human QA Review Queue */}
          <div className="relative flex items-center justify-center w-full">
            {activeTab === 'review' && (
              <span className="absolute left-0 w-1 h-5 bg-purple-600 rounded-r-md" />
            )}
            <button
              onClick={() => onSelectTab('review')}
              className={`p-2.5 rounded-xl transition-all ${
                activeTab === 'review'
                  ? 'text-purple-600 bg-purple-50/80 shadow-xs'
                  : 'text-gray-400 hover:text-gray-700 hover:bg-gray-100/70'
              }`}
              title="Human-in-the-Loop Review QA"
            >
              <CheckSquare className="w-5 h-5" />
            </button>
          </div>
        </nav>
      </div>

      {/* Bottom Profile & Settings */}
      <div className="flex flex-col items-center gap-3 w-full">
        {/* Settings button */}
        <button
          onClick={onOpenSettings}
          className="p-2.5 rounded-xl text-gray-400 hover:text-gray-700 hover:bg-gray-100/70 transition-all"
          title="Officer Settings & Security Clearance"
        >
          <Settings className="w-5 h-5" />
        </button>

        {/* User Clearance Avatar Pill */}
        <button
          onClick={onOpenSettings}
          className="relative group p-0.5 rounded-full transition-transform hover:scale-105"
          title={`${userName} (${clearanceLevel} Clearance)`}
        >
          <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-purple-600 to-indigo-600 flex items-center justify-center text-white text-xs font-bold shadow-xs">
            {userName[0]?.toUpperCase() || 'O'}
          </div>
          {clearanceLevel !== 'PUBLIC' && (
            <span className="absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 bg-amber-500 rounded-full border-2 border-white flex items-center justify-center text-[8px] text-white font-bold" title={clearanceLevel}>
              ★
            </span>
          )}
        </button>
      </div>
    </aside>
  );
}
