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
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30 backdrop-blur-2xs animate-in fade-in duration-150">
      <div className="bg-white w-full max-w-2xl h-full shadow-2xl border-l border-gray-100 flex flex-col">
        {/* Header */}
        <div className="p-5 border-b border-gray-100 bg-gray-50/50 flex items-center justify-between shrink-0">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-gray-900">Job Execution Items</h2>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-purple-50 text-purple-700 font-semibold">
                {job.id}
              </span>
            </div>
            <p className="text-xs text-gray-500 mt-0.5">
              Source: <span className="font-medium text-gray-700">{job.source_name}</span> • Stage: {job.current_stage}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-all"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Filters & Search */}
        <div className="p-4 border-b border-gray-100 flex items-center justify-between gap-3 bg-white shrink-0">
          {/* Status Tabs */}
          <div className="flex items-center gap-1 bg-gray-100 p-0.5 rounded-xl text-[11px] font-medium text-gray-600">
            {['ALL', 'SUCCESS', 'SKIPPED', 'FAILED'].map((stat) => (
              <button
                key={stat}
                type="button"
                onClick={() => {
                  setStatusFilter(stat);
                  setPage(1);
                }}
                className={`px-2.5 py-1 rounded-lg transition-all ${
                  statusFilter === stat ? 'bg-white text-gray-900 shadow-xs font-semibold' : 'hover:text-gray-900'
                }`}
              >
                {stat === 'ALL' ? 'All Items' : stat.charAt(0) + stat.slice(1).toLowerCase()}
              </button>
            ))}
          </div>

          {/* Search Box */}
          <div className="relative flex-1 max-w-xs">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-gray-400" />
            <input
              type="text"
              placeholder="Search item URL or path..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 text-xs rounded-xl border border-gray-200 bg-white focus:outline-hidden focus:border-purple-500"
            />
          </div>
        </div>

        {/* Items List / Table */}
        <div className="flex-1 overflow-y-auto p-4 space-y-2">
          {loading ? (
            <div className="h-48 flex items-center justify-center text-xs text-gray-400">Loading items...</div>
          ) : filteredItems.length === 0 ? (
            <div className="h-48 flex flex-col items-center justify-center text-xs text-gray-400">
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
                  className="p-3 rounded-2xl border border-gray-100 bg-white hover:border-gray-200 transition-all text-xs flex flex-col gap-1.5 shadow-2xs"
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      {isSuccess && <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />}
                      {isSkipped && <SkipForward className="w-4 h-4 text-blue-500 shrink-0" />}
                      {isFailed && <AlertCircle className="w-4 h-4 text-red-500 shrink-0" />}
                      {!isSuccess && !isSkipped && !isFailed && <Clock className="w-4 h-4 text-gray-400 shrink-0" />}
                      <span className="font-medium text-gray-800 truncate" title={item.item_key}>
                        {item.title || item.item_key}
                      </span>
                    </div>

                    <span
                      className={`px-2 py-0.5 rounded-full text-[10px] font-bold shrink-0 ${
                        isSuccess
                          ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                          : isSkipped
                          ? 'bg-blue-50 text-blue-700 border border-blue-200'
                          : isFailed
                          ? 'bg-red-50 text-red-700 border border-red-200'
                          : 'bg-gray-50 text-gray-600 border border-gray-200'
                      }`}
                    >
                      {item.status}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-[11px] text-gray-400 font-mono">
                    <span className="truncate max-w-[340px]" title={item.item_key}>
                      {item.item_key}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleCopy(item.item_key)}
                      className="p-1 rounded text-gray-400 hover:text-gray-600"
                      title="Copy URL/Key"
                    >
                      {copiedKey === item.item_key ? <Check className="w-3 h-3 text-emerald-600" /> : <Copy className="w-3 h-3" />}
                    </button>
                  </div>

                  {item.duration_ms && (
                    <div className="text-[10px] text-gray-400">
                      Processing latency: {item.duration_ms.toFixed(1)}ms
                    </div>
                  )}

                  {isFailed && item.error_message && (
                    <div className="mt-1 p-2 rounded-xl bg-red-50/80 border border-red-100 text-red-700 text-[11px] font-mono break-all">
                      {item.error_message}
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Pagination Footer */}
        <div className="p-3 border-t border-gray-100 bg-gray-50/50 flex items-center justify-between shrink-0 text-xs text-gray-500">
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
              className="p-1.5 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 disabled:opacity-40"
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
              className="p-1.5 rounded-lg border border-gray-200 bg-white hover:bg-gray-50 disabled:opacity-40"
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
