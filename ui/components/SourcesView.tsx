'use client';

import { useState, useEffect } from 'react';
import { Database, Play, Pause, RefreshCw } from 'lucide-react';
import type { SourceItem } from '@/lib/types';
import { fetchSources, toggleSourceStatus } from '@/lib/api';

export default function SourcesView() {
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [togglingId, setTogglingId] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    const data = await fetchSources();
    setSources(data);
    setLoading(false);
  };

  useEffect(() => {
    load();
  }, []);

  const handleToggle = async (id: string) => {
    setTogglingId(id);
    try {
      const updated = await toggleSourceStatus(id);
      setSources((prev) =>
        prev.map((s) => (s.id === id ? { ...s, status: updated.status } : s)),
      );
    } catch (err) {
      console.error(err);
    } finally {
      setTogglingId(null);
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-[#fcfcfc] overflow-hidden">
      {/* Header */}
      <div className="p-6 border-b border-gray-100 flex items-center justify-between bg-white/70 backdrop-blur-xs shrink-0">
        <div>
          <div className="flex items-center gap-2">
            <Database className="w-5 h-5 text-purple-600" />
            <h1 className="text-base font-semibold text-gray-800">
              Government Data Sources &amp; Ingestion Connectors
            </h1>
            <span className="px-2 py-0.5 rounded-full bg-purple-50 text-purple-700 text-xs font-medium">
              {sources.length} Registered
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-0.5">
            Phase 01 Source Registry: Monitored portals, crawlers, and crawl governance controls
          </p>
        </div>

        <button
          onClick={load}
          className="p-2 rounded-xl border border-gray-200 bg-white hover:bg-gray-50 text-xs font-medium text-gray-600 flex items-center gap-1.5 shadow-xs"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Main List */}
      <div className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="h-64 flex items-center justify-center text-xs text-gray-400">
            Loading sources…
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {sources.map((src) => {
              const isApproved = src.status === 'APPROVED';
              const isToggling = togglingId === src.id;

              return (
                <div
                  key={src.id}
                  className="bg-white rounded-2xl border border-gray-100 p-5 shadow-xs flex flex-col justify-between"
                >
                  <div>
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-gray-100 text-gray-600">
                        {src.department_id.replace(/_/g, ' ')}
                      </span>
                      <span
                        className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold ${
                          isApproved
                            ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                            : 'bg-amber-50 text-amber-700 border border-amber-200'
                        }`}
                      >
                        {src.status}
                      </span>
                    </div>

                    <h3 className="text-xs font-semibold text-gray-800 line-clamp-1 mb-1">
                      {src.name}
                    </h3>

                    <div className="text-[11px] text-gray-400 space-y-1 mt-2">
                      <p className="truncate">
                        <span className="text-gray-500">Domains: </span>
                        {src.base_url || 'N/A'}
                      </p>
                      <p>
                        <span className="text-gray-500">Cadence: </span>
                        {src.refresh_cadence}
                      </p>
                      <p>
                        <span className="text-gray-500">Owner: </span>
                        {src.owner_name}
                      </p>
                    </div>
                  </div>

                  <div className="mt-4 pt-3 border-t border-gray-50 flex items-center justify-between">
                    <span className="text-xs font-semibold text-purple-700">
                      {src.document_count} docs ingested
                    </span>

                    <button
                      type="button"
                      disabled={isToggling}
                      onClick={() => handleToggle(src.id)}
                      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-all ${
                        isApproved
                          ? 'bg-amber-50 hover:bg-amber-100 text-amber-800'
                          : 'bg-emerald-50 hover:bg-emerald-100 text-emerald-800'
                      }`}
                    >
                      {isApproved ? (
                        <>
                          <Pause className="w-3.5 h-3.5" />
                          <span>Pause Ingestion</span>
                        </>
                      ) : (
                        <>
                          <Play className="w-3.5 h-3.5" />
                          <span>Approve Connector</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
