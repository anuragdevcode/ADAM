'use client';

import { useEffect, useState, useCallback } from 'react';
import { listSessions, deleteSession } from '@/lib/api';
import type { SessionInfo } from '@/lib/types';
import { MessageSquare, Trash2, RefreshCw, X, Search, Calendar } from 'lucide-react';

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
  };

  const filteredSessions = sessions.filter((s) => {
    if (!filterText.trim()) return true;
    return (
      s.session_id.toLowerCase().includes(filterText.toLowerCase()) ||
      s.created_at.includes(filterText)
    );
  });

  return (
    <aside className="w-72 h-full flex flex-col border-r border-gray-100 bg-[#fafafa]/95 backdrop-blur-md select-none shrink-0 z-10">
      {/* Top Header */}
      <div className="flex items-center justify-between px-4 py-3.5 border-b border-gray-100">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-4 h-4 text-purple-600" />
          <h2 className="text-xs font-semibold uppercase tracking-wider text-gray-700">
            Chat Threads
          </h2>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={load}
            title="Refresh threads"
            className="p-1 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-200/50 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
          {onClose && (
            <button
              onClick={onClose}
              title="Close panel"
              className="p-1 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-200/50 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Search Input Filter */}
      <div className="p-3 border-b border-gray-100">
        <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-xl border border-gray-200/80 bg-white text-xs text-gray-600 focus-within:border-purple-400 focus-within:ring-1 focus-within:ring-purple-400">
          <Search className="w-3.5 h-3.5 text-gray-400 shrink-0" />
          <input
            type="text"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            placeholder="Filter threads..."
            className="bg-transparent outline-none w-full placeholder-gray-400"
          />
          {filterText && (
            <button onClick={() => setFilterText('')} className="text-gray-400 hover:text-gray-600">
              <X className="w-3 h-3" />
            </button>
          )}
        </div>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {loading ? (
          <div className="p-4 text-center text-xs text-gray-400">Loading threads…</div>
        ) : filteredSessions.length === 0 ? (
          <div className="p-6 text-center text-xs text-gray-400">
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
                    ? 'bg-purple-50 text-purple-900 font-medium shadow-xs border border-purple-200/60'
                    : 'text-gray-700 hover:bg-gray-100/80 border border-transparent'
                }`}
              >
                <div className="min-w-0 flex-1 pr-2">
                  <div className="flex items-center gap-1.5">
                    <Calendar className="w-3 h-3 text-gray-400 shrink-0" />
                    <span className="truncate">{timeAgo(s.created_at)}</span>
                  </div>
                  <p className="text-[11px] text-gray-400 mt-0.5 font-normal">
                    {s.turn_count} {s.turn_count === 1 ? 'interaction' : 'interactions'}
                  </p>
                </div>

                <button
                  onClick={(e) => handleDelete(e, s.session_id)}
                  title="Delete conversation"
                  className="opacity-0 group-hover:opacity-100 p-1 rounded-lg text-gray-400 hover:text-rose-600 hover:bg-rose-50 transition-all"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}
