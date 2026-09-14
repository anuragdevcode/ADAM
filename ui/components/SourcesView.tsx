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
      <div className="p-6 border-b border-line flex items-center justify-between bg-surface backdrop-blur-xs shrink-0">
        <div>
          <div className="flex items-center gap-2">
            <Database className="w-5 h-5 text-brand" />
            <h1 className="text-base font-semibold text-ink">
              Government Data Sources &amp; Ingestion Connectors
            </h1>
            <span className="px-2 py-0.5 rounded-full bg-brand-soft text-brand text-xs font-medium">
              {sources.length} Registered
            </span>
          </div>
          <p className="text-xs text-ink-faint mt-0.5">
            Phase 01 Source Registry: Monitored portals, crawlers, and crawl governance controls
          </p>
        </div>

        <button
          onClick={load}
          className="p-2 rounded-xl border border-line bg-surface hover:bg-surface-subtle text-xs font-medium text-ink-secondary flex items-center gap-1.5 shadow-xs"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Main List */}
      <div className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="h-64 flex items-center justify-center text-xs text-ink-faint">
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
                  className="bg-surface rounded-2xl border border-line p-5 shadow-xs flex flex-col justify-between"
                >
                  <div>
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <span className="px-2 py-0.5 rounded-md text-[10px] font-semibold bg-surface-sunken text-ink-secondary">
                        {src.department_id.replace(/_/g, ' ')}
                      </span>
                      <span
                        className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold ${
                          isApproved
                            ? 'bg-ok-soft text-ok border border-ok'
                            : 'bg-warn-soft text-warn border border-warn'
                        }`}
                      >
                        {src.status}
                      </span>
                    </div>

                    <h3 className="text-xs font-semibold text-ink line-clamp-1 mb-1">
                      {src.name}
                    </h3>

                    <div className="text-[11px] text-ink-faint space-y-1 mt-2">
                      <p className="truncate">
                        <span className="text-ink-muted">Domains: </span>
                        {src.base_url || 'N/A'}
                      </p>
                      <p>
                        <span className="text-ink-muted">Cadence: </span>
                        {src.refresh_cadence}
                      </p>
                      <p>
                        <span className="text-ink-muted">Owner: </span>
                        {src.owner_name}
                      </p>
                    </div>
                  </div>

                  <div className="mt-4 pt-3 border-t border-line flex items-center justify-between">
                    <span className="text-xs font-semibold text-brand">
                      {src.document_count} docs ingested
                    </span>

                    <button
                      type="button"
                      disabled={isToggling}
                      onClick={() => handleToggle(src.id)}
                      className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-medium transition-all ${
                        isApproved
                          ? 'bg-warn-soft hover:bg-warn-soft text-warn'
                          : 'bg-ok-soft hover:bg-ok-soft text-ok'
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
