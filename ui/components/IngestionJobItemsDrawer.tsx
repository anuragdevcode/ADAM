'use client';

import { useState, useEffect, useCallback } from 'react';
import { X, CheckCircle2, AlertCircle, SkipForward, Clock, ChevronLeft, ChevronRight, Copy, Check, Search } from 'lucide-react';
import { fetchJobItems } from '@/lib/api';
import type { IngestionItemDetail, IngestionJobItemRecord } from '@/lib/types';

interface IngestionJobItemsDrawerProps {
  job: IngestionJobItemRecord | null;
  onClose: () => void;
}

export default function IngestionJobItemsDrawer({ job, onClose }: IngestionJobItemsDrawerProps) {
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize] = useState(15);
  const [items, setItems] = useState<IngestionItemDetail[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const loadItems = useCallback(
    async (p: number, stat = statusFilter) => {
      if (!job) return;
      setLoading(true);
      try {
        const res = await fetchJobItems(job.id, stat, p, pageSize);
        setItems(res.items);
        setTotal(res.total);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    },
    [job, statusFilter, pageSize]
  );

  useEffect(() => {
    if (job) {
      setPage(1);
      loadItems(1, statusFilter);
    }
  }, [job, statusFilter, loadItems]);

  if (!job) return null;

  const totalPages = Math.ceil(total / pageSize) || 1;

  const handleCopy = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(text);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const filteredItems = items.filter((it) =>
    searchQuery ? it.item_key.toLowerCase().includes(searchQuery.toLowerCase()) : true
  );

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-slate-950/40 dark:bg-black/60 backdrop-blur-xs animate-in fade-in duration-150">
      <div className="bg-white dark:bg-[#111726] w-full max-w-2xl h-full shadow-2xl border-l border-slate-200 dark:border-slate-800 flex flex-col animate-in slide-in-from-right duration-200">
        {/* Header */}
        <div className="p-5 border-b border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-[#131b2c]/50 flex items-center justify-between shrink-0">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-slate-900 dark:text-slate-100">Job Execution Items</h2>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-purple-50 dark:bg-purple-950/60 text-purple-700 dark:text-purple-300 font-semibold border border-purple-200 dark:border-purple-800">
                {job.id}
              </span>
            </div>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Source: <span className="font-medium text-slate-700 dark:text-slate-300">{job.source_name}</span> • Stage: {job.current_stage}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-all"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Filters & Search */}
        <div className="p-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between gap-3 bg-white dark:bg-[#111726] shrink-0">
          {/* Status Tabs */}
          <div className="flex items-center gap-1 bg-slate-100 dark:bg-slate-800 p-0.5 rounded-xl text-[11px] font-semibold text-slate-600 dark:text-slate-400">
            {['ALL', 'SUCCESS', 'SKIPPED', 'FAILED'].map((stat) => (
              <button
                key={stat}
                type="button"
                onClick={() => {
                  setStatusFilter(stat);
                  setPage(1);
                }}
                className={`px-2.5 py-1 rounded-lg transition-all ${
                  statusFilter === stat
                    ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-xs font-semibold'
                    : 'hover:text-slate-900 dark:hover:text-slate-200'
                }`}
              >
                {stat === 'ALL' ? 'All Items' : stat.charAt(0) + stat.slice(1).toLowerCase()}
              </button>
            ))}
          </div>

          {/* Search Box */}
          <div className="relative flex-1 max-w-xs">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search item URL or path…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 text-xs rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#131926] text-slate-800 dark:text-slate-100 focus:outline-none focus:border-purple-500"
            />
          </div>
        </div>

        {/* Items List / Table */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {loading ? (
            <div className="h-48 flex items-center justify-center text-xs text-slate-400">Loading items…</div>
          ) : filteredItems.length === 0 ? (
            <div className="h-48 flex flex-col items-center justify-center text-xs text-slate-400">
              <p>No items found for this filter.</p>
            </div>
          ) : (
            filteredItems.map((item) => {
              const isSuccess = item.status === 'SUCCESS';
              const isSkipped = item.status === 'SKIPPED';
              const isFailed = item.status === 'FAILED';

              return (
                <div
                  key={item.id}
                  className="p-3 rounded-2xl border border-slate-200/80 dark:border-slate-800 bg-white dark:bg-[#131926] hover:border-purple-300 dark:hover:border-purple-700 transition-all text-xs flex flex-col gap-1.5 shadow-2xs"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      {isSuccess && <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />}
                      {isSkipped && <SkipForward className="w-4 h-4 text-blue-500 dark:text-blue-400 shrink-0" />}
                      {isFailed && <AlertCircle className="w-4 h-4 text-red-500 dark:text-red-400 shrink-0" />}
                      {!isSuccess && !isSkipped && !isFailed && <Clock className="w-4 h-4 text-slate-400 shrink-0" />}
                      <span className="font-semibold text-slate-900 dark:text-slate-100 truncate" title={item.item_key}>
                        {item.title || item.item_key}
                      </span>
                    </div>

                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-bold shrink-0 ${
                        isSuccess
                          ? 'bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800'
                          : isSkipped
                          ? 'bg-blue-50 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800'
                          : isFailed
                          ? 'bg-red-50 dark:bg-red-950/60 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-800'
                          : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700'
                      }`}
                    >
                      {item.status}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono">
                    <span className="truncate max-w-[340px]" title={item.item_key}>
                      {item.item_key}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleCopy(item.item_key)}
                      className="p-1 rounded text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                      title="Copy URL/Key"
                    >
                      {copiedKey === item.item_key ? <Check className="w-3 h-3 text-emerald-600 dark:text-emerald-400" /> : <Copy className="w-3 h-3" />}
                    </button>
                  </div>

                  {item.duration_ms && (
                    <div className="text-[10px] text-slate-400">
                      Processing latency: {item.duration_ms.toFixed(1)}ms
                    </div>
                  )}

                  {isFailed && item.error_message && (
                    <div className="mt-1 p-2 rounded-xl bg-red-50/80 dark:bg-red-950/50 border border-red-100 dark:border-red-900/60 text-red-700 dark:text-red-300 text-[11px] font-mono break-all">
                      {item.error_message}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Pagination Footer */}
        <div className="p-3 border-t border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-[#131b2c]/50 flex items-center justify-between shrink-0 text-xs text-slate-500 dark:text-slate-400">
          <span>
            Showing page {page} of {totalPages} ({total} total items)
          </span>
          <div className="flex items-center gap-1">
            <button
              type="button"
              disabled={page <= 1 || loading}
              onClick={() => {
                const nextP = page - 1;
                setPage(nextP);
                loadItems(nextP);
              }}
              className="p-1.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#131926] hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-40"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
            <button
              type="button"
              disabled={page >= totalPages || loading}
              onClick={() => {
                const nextP = page + 1;
                setPage(nextP);
                loadItems(nextP);
              }}
              className="p-1.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#131926] hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-40"
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
