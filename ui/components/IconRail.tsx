'use client';

import { useEffect, useState } from 'react';
import {
  Home,
  MessageSquare,
  Bot,
  FolderClosed,
  Share2,
  Database,
  CheckSquare,
  Settings,
  Moon,
  Sun,
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

/** Nav entries are data so the markup stays one loop instead of seven copies. */
const NAV_ITEMS: { tab: NavTab; icon: typeof Home; label: string }[] = [
  { tab: 'home', icon: Home, label: 'Chat Studio' },
  { tab: 'docs', icon: FolderClosed, label: 'Document Repository' },
  { tab: 'network', icon: Share2, label: 'Precedent Chains' },
  { tab: 'audit', icon: Bot, label: 'Agent Execution Audits' },
  { tab: 'database', icon: Database, label: 'Acquisition Sources' },
  { tab: 'review', icon: CheckSquare, label: 'Review Queue' },
];

/** Tooltip that reads out to the right of the rail on hover and focus. */
function RailButton({
  icon: Icon,
  label,
  active,
  onClick,
  badge,
}: {
  icon: typeof Home;
  label: string;
  active?: boolean;
  onClick: () => void;
  badge?: React.ReactNode;
}) {
  return (
    <div className="relative w-full flex items-center justify-center group">
      {active && (
        <span className="absolute left-0 w-[3px] h-6 rounded-r-full bg-brand" aria-hidden />
      )}
      <button
        type="button"
        onClick={onClick}
        aria-label={label}
        aria-current={active ? 'page' : undefined}
        className={`relative p-2.5 rounded-xl transition-colors duration-150 ${
          active
            ? 'text-brand bg-brand-soft'
            : 'text-ink-faint hover:text-ink-secondary hover:bg-surface-sunken'
        }`}
      >
        <Icon className="w-[18px] h-[18px]" strokeWidth={active ? 2.2 : 1.9} />
        {badge}
      </button>

      <span
        role="tooltip"
        className="pointer-events-none absolute left-[calc(100%+8px)] top-1/2 -translate-y-1/2 z-50
                   whitespace-nowrap rounded-lg bg-surface-inverted px-2.5 py-1.5 text-2xs font-medium
                   text-[var(--surface)] opacity-0 shadow-lg transition-opacity duration-150
                   group-hover:opacity-100 group-focus-within:opacity-100"
      >
        {label}
      </span>
    </div>
  );
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
  const [isDark, setIsDark] = useState(false);

  // Mirror whatever the pre-paint bootstrap in layout.tsx already applied.
  useEffect(() => {
    setIsDark(document.documentElement.getAttribute('data-theme') === 'dark');
  }, []);

  const toggleTheme = () => {
    const next = isDark ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try {
      localStorage.setItem('adam-theme', next);
    } catch {
      /* private mode — the theme simply won't persist */
    }
    setIsDark(!isDark);
  };

  return (
    <aside className="w-[64px] h-full flex flex-col items-center justify-between py-4 border-r border-line bg-surface-subtle select-none z-20 shrink-0">
      <div className="flex flex-col items-center gap-4 w-full">
        {/* Brand mark */}
        <button
          onClick={() => onSelectTab('home')}
          className="w-9 h-9 rounded-xl bg-brand flex items-center justify-center text-ink-onBrand shadow-sm hover:bg-brand-hover transition-colors"
          title="ADAM — Uttarakhand Government Records"
          aria-label="ADAM home"
        >
          <svg
            className="w-[18px] h-[18px]"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden
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

        <div className="w-7 h-px bg-line" aria-hidden />

        <nav className="flex flex-col items-center gap-1 w-full" aria-label="Primary">
          <RailButton
            icon={Home}
            label="Chat Studio"
            active={activeTab === 'home' && !isHistoryOpen}
            onClick={() => onSelectTab('home')}
          />
          <RailButton
            icon={MessageSquare}
            label="Chat Threads"
            active={isHistoryOpen}
            onClick={onToggleHistory}
          />

          <div className="w-7 h-px bg-line my-1.5" aria-hidden />

          {NAV_ITEMS.filter((item) => item.tab !== 'home').map((item) => (
            <RailButton
              key={item.tab}
              icon={item.icon}
              label={item.label}
              active={activeTab === item.tab}
              onClick={() => onSelectTab(item.tab)}
            />
          ))}
        </nav>
      </div>

      <div className="flex flex-col items-center gap-1.5 w-full">
        <RailButton
          icon={isDark ? Sun : Moon}
          label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
          onClick={toggleTheme}
        />
        <RailButton icon={Settings} label="Officer Settings" onClick={onOpenSettings} />

        <button
          onClick={onOpenSettings}
          className="relative mt-1 rounded-full transition-transform hover:scale-105 focus-visible:scale-105"
          title={`${userName} — ${clearanceLevel} clearance`}
          aria-label={`${userName}, ${clearanceLevel} clearance. Open settings`}
        >
          <div className="w-8 h-8 rounded-full bg-brand flex items-center justify-center text-ink-onBrand text-xs font-semibold shadow-sm ring-1 ring-inset ring-white/15">
            {userName[0]?.toUpperCase() || 'O'}
          </div>
          {clearanceLevel !== 'PUBLIC' && (
            <span
              className="absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 rounded-full bg-seal border-2 border-[var(--surface-subtle)]"
              title={`${clearanceLevel} clearance`}
              aria-hidden
            />
          )}
        </button>
      </div>
    </aside>
  );
}
