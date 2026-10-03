'use client';

import { useEffect, useState, useCallback } from 'react';
import { listSessions, deleteSession } from '@/lib/api';
import type { SessionInfo } from '@/lib/types';
import { MessageSquare, Trash2, RefreshCw, X, Search, Calendar, ChevronRight } from 'lucide-react';
import { useToast } from './ToastProvider';

function timeAgo(isoDate: string): string {
  const diff = Date.now() - new Date(isoDate).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

interface ConversationHistoryProps {
  userId: string;
  activeSessionId: string | null;
  onSelectSession: (sessionId: string) => void;
  onClose?: () => void;
  searchFilter?: string;
}

export default function ConversationHistory({
  userId,
  activeSessionId,
  onSelectSession,
  onClose,
  searchFilter = '',
}: ConversationHistoryProps) {
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterText, setFilterText] = useState(searchFilter);
  const { toast } = useToast();

  const load = useCallback(async () => {
    setLoading(true);
    const data = await listSessions(userId);
    setSessions(data);
    setLoading(false);
  }, [userId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleDelete = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    if (!confirm('Delete this conversation?')) return;
    await deleteSession(sessionId, userId);
    setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
    toast.info('Conversation thread deleted');
  };

  const filteredSessions = sessions.filter((s) => {
    if (!filterText.trim()) return true;
    return (
      s.session_id.toLowerCase().includes(filterText.toLowerCase()) ||
      s.created_at.includes(filterText)
    );
  });

  return (
    <aside className="w-72 h-full flex flex-col border-r border-slate-200/80 dark:border-slate-800 bg-white/95 dark:bg-[#0c111c]/95 select-none shrink-0 z-10 transition-colors animate-drawer-slide-in shadow-[8px_0_24px_-4px_rgba(0,0,0,0.06)] dark:shadow-[8px_0_30px_-4px_rgba(0,0,0,0.4)] backdrop-blur-sm">
      {/* Top Header */}
      <div className="flex items-center justify-between px-4 py-3.5 border-b border-slate-200/80 dark:border-slate-800">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-4 h-4 text-purple-600 dark:text-purple-400" />
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-700 dark:text-slate-300">
            Chat Threads
          </h2>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={load}
            title="Refresh threads"
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              title="Close panel"
              className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Search Input Filter */}
      <div className="p-3 border-b border-slate-100 dark:border-slate-800/80">
        <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-[#131926] text-xs text-slate-600 dark:text-slate-300 focus-within:border-purple-300/50 dark:focus-within:border-purple-500/40 focus-within:reflection-glow-subtle transition-all">
          <Search className="w-3.5 h-3.5 text-slate-400 shrink-0" />
          <input
            type="text"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            placeholder="Filter threads…"
            className="bg-transparent outline-none w-full placeholder-slate-400 dark:placeholder-slate-500"
          />
          {filterText && (
            <button type="button" onClick={() => setFilterText('')} className="text-slate-400 hover:text-slate-600">
              <X className="w-3 h-3" />
            </button>
          )}
        </div>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {loading ? (
          <div className="p-6 text-center text-xs text-slate-400 dark:text-slate-500">Loading threads…</div>
        ) : filteredSessions.length === 0 ? (
          <div className="p-6 text-center text-xs text-slate-400 dark:text-slate-500">
            {filterText ? 'No matching threads found.' : 'No threads yet. Ask a question to start!'}
          </div>
        ) : (
          filteredSessions.map((s) => {
            const isSelected = activeSessionId === s.session_id;
            return (
              <div
                key={s.session_id}
                onClick={() => onSelectSession(s.session_id)}
                className={`group flex items-center justify-between px-3 py-2.5 rounded-xl cursor-pointer text-xs transition-all ${
                  isSelected
                    ? 'bg-purple-50/90 dark:bg-purple-950/60 text-purple-900 dark:text-purple-200 font-medium border border-purple-200/50 dark:border-purple-800/40 reflection-glow-subtle'
                    : 'text-slate-700 dark:text-slate-300 hover:bg-slate-100/80 dark:hover:bg-slate-800/50 hover:shadow-[0_0_14px_-2px_rgba(168,85,247,0.18)] border border-transparent'
                }`}
              >
                <div className="min-w-0 flex-1 pr-2">
                  <div className="flex items-center gap-1.5">
                    <Calendar className="w-3 h-3 text-slate-400 shrink-0" />
                    <span className="truncate">{timeAgo(s.created_at)}</span>
                  </div>
                  <p className="text-[11px] text-slate-400 dark:text-slate-500 mt-0.5 font-normal">
                    {s.turn_count} {s.turn_count === 1 ? 'turn' : 'turns'}
                  </p>
                </div>

                <div className="flex items-center gap-1 shrink-0">
                  <button
                    type="button"
                    onClick={(e) => handleDelete(e, s.session_id)}
                    title="Delete conversation"
                    className="opacity-0 group-hover:opacity-100 p-1 rounded-lg text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-950/40 transition-all"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                  <ChevronRight className="w-3.5 h-3.5 text-slate-300 dark:text-slate-600 opacity-0 group-hover:opacity-100" />
                </div>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}
