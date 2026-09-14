'use client';

import { useState, useEffect } from 'react';
import { Share2, Search, ArrowRight, FileText } from 'lucide-react';
import type { PrecedentItem } from '@/lib/types';
import { fetchPrecedents } from '@/lib/api';

const RELATION_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  SUPERSEDES: { bg: 'bg-danger-soft', text: 'text-danger', border: 'border-danger' },
  AMENDS: { bg: 'bg-warn-soft', text: 'text-warn', border: 'border-warn' },
  IN_CONTINUATION_OF: { bg: 'bg-blue-50', text: 'text-blue-700', border: 'border-blue-200' },
  READ_WITH: { bg: 'bg-brand-soft', text: 'text-brand', border: 'border-brand-border' },
  REFERS_TO: { bg: 'bg-surface-subtle', text: 'text-ink-secondary', border: 'border-line' },
};

export default function PrecedentsView() {
  const [precedents, setPrecedents] = useState<PrecedentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [relationFilter, setRelationFilter] = useState('ALL');
  const [search, setSearch] = useState('');

  useEffect(() => {
    setLoading(true);
    fetchPrecedents(relationFilter, search).then((data) => {
      setPrecedents(data);
      setLoading(false);
    });
  }, [relationFilter, search]);

  return (
    <div className="flex-1 flex flex-col h-full bg-[#fcfcfc] overflow-hidden">
      {/* Header */}
      <div className="p-6 border-b border-line flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-surface backdrop-blur-xs shrink-0">
        <div>
          <div className="flex items-center gap-2">
            <Share2 className="w-5 h-5 text-brand" />
            <h1 className="text-base font-semibold text-ink">
              Precedent &amp; Supersession Chains
            </h1>
            <span className="px-2 py-0.5 rounded-full bg-brand-soft text-brand text-xs font-medium">
              {precedents.length} Links
            </span>
          </div>
          <p className="text-xs text-ink-faint mt-0.5">
            Verified legal and administrative relationships between Uttarakhand Government Orders
          </p>
        </div>
      </div>

      {/* Filter Row */}
      <div className="px-6 py-3 border-b border-line bg-surface-subtle/50 flex flex-wrap items-center gap-3 shrink-0">
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-line bg-surface text-xs text-ink-secondary focus-within:border-brand-border min-w-[220px]">
          <Search className="w-3.5 h-3.5 text-ink-faint" />
          <input
            type="text"
            placeholder="Search citation or GO..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-transparent outline-none w-full placeholder-ink-faint"
          />
        </div>

        <select
          value={relationFilter}
          onChange={(e) => setRelationFilter(e.target.value)}
          className="px-3 py-1.5 rounded-xl border border-line bg-surface text-xs text-ink-secondary outline-none focus:border-brand-border"
        >
          <option value="ALL">All Relationships</option>
          <option value="SUPERSEDES">SUPERSEDES</option>
          <option value="AMENDS">AMENDS</option>
          <option value="IN_CONTINUATION_OF">IN CONTINUATION OF</option>
          <option value="READ_WITH">READ WITH</option>
          <option value="REFERS_TO">REFERS TO</option>
        </select>
      </div>

      {/* Main List */}
      <div className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="h-64 flex items-center justify-center text-xs text-ink-faint">
            Loading precedent chains…
          </div>
        ) : precedents.length === 0 ? (
          <div className="h-64 flex flex-col items-center justify-center text-center p-6 text-ink-faint">
            <Share2 className="w-10 h-10 stroke-[1.5] text-ink-faint mb-2" />
            <p className="text-sm font-medium text-ink-secondary">No precedent relationships found</p>
            <p className="text-xs text-ink-faint mt-1">
              As orders are extracted, citations and supersession clauses will appear here.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {precedents.map((pr) => {
              const style = RELATION_STYLES[pr.relation_type] || RELATION_STYLES['REFERS_TO'];
              return (
                <div
                  key={pr.id}
                  className="bg-surface rounded-2xl border border-line p-4 shadow-xs hover:border-brand-border transition-all"
                >
                  <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                    {/* Source Document */}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 text-xs font-semibold text-ink mb-1">
                        <FileText className="w-3.5 h-3.5 text-brand shrink-0" />
                        <span className="truncate">{pr.source_title}</span>
                      </div>
                      {pr.source_go_number && (
                        <span className="font-mono text-[11px] text-ink-muted bg-surface-subtle px-1.5 py-0.5 rounded">
                          GO: {pr.source_go_number}
                        </span>
                      )}
                    </div>

                    {/* Relation Badge */}
                    <div className="flex items-center gap-2 shrink-0 my-1 sm:my-0">
                      <span
                        className={`inline-flex items-center px-2.5 py-1 rounded-full border text-[11px] font-bold ${style.bg} ${style.text} ${style.border}`}
                      >
                        {pr.relation_type}
                      </span>
                      <ArrowRight className="w-4 h-4 text-ink-faint shrink-0" />
                    </div>

                    {/* Target / Cited Reference */}
                    <div className="min-w-0 flex-1 sm:text-right">
                      <p className="text-xs font-semibold text-ink truncate">
                        {pr.target_title || pr.cited_act_or_rule || pr.raw_citation_text}
                      </p>
                      {pr.cited_order_number && (
                        <span className="font-mono text-[11px] text-ink-muted bg-surface-subtle px-1.5 py-0.5 rounded">
                          Ref: {pr.cited_order_number}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="mt-3 pt-2.5 border-t border-line text-[11px] text-ink-muted flex items-center justify-between">
                    <span className="italic truncate pr-4">&quot;{pr.raw_citation_text}&quot;</span>
                    {pr.created_at && (
                      <span className="shrink-0 text-ink-faint">
                        {new Date(pr.created_at).toLocaleDateString()}
                      </span>
                    )}
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
