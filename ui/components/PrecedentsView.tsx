'use client';

import { useState, useEffect } from 'react';
import { Share2, Search, ArrowRight, FileText } from 'lucide-react';
import type { PrecedentItem } from '@/lib/types';
import { fetchPrecedents } from '@/lib/api';

const RELATION_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  SUPERSEDES: {
    bg: 'bg-rose-50 dark:bg-rose-950/60',
    text: 'text-rose-700 dark:text-rose-300',
    border: 'border-rose-200 dark:border-rose-800',
  },
  AMENDS: {
    bg: 'bg-amber-50 dark:bg-amber-950/60',
    text: 'text-amber-700 dark:text-amber-300',
    border: 'border-amber-200 dark:border-amber-800',
  },
  IN_CONTINUATION_OF: {
    bg: 'bg-blue-50 dark:bg-blue-950/60',
    text: 'text-blue-700 dark:text-blue-300',
    border: 'border-blue-200 dark:border-blue-800',
  },
  READ_WITH: {
    bg: 'bg-purple-50 dark:bg-purple-950/60',
    text: 'text-purple-700 dark:text-purple-300',
    border: 'border-purple-200 dark:border-purple-800',
  },
  REFERS_TO: {
    bg: 'bg-slate-50 dark:bg-slate-800',
    text: 'text-slate-700 dark:text-slate-300',
    border: 'border-slate-200 dark:border-slate-700',
  },
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
    <div className="flex-1 flex flex-col h-full bg-[#f8fafc] dark:bg-[#090d16] overflow-hidden transition-colors">
      {/* Header */}
      <div className="p-6 border-b border-slate-200/80 dark:border-slate-800 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-white/70 dark:bg-[#0d121e]/70 backdrop-blur-xs shrink-0">
        <div>
          <div className="flex items-center gap-2">
            <Share2 className="w-5 h-5 text-purple-600 dark:text-purple-400" />
            <h1 className="text-base font-semibold text-slate-900 dark:text-slate-100">
              Precedent &amp; Supersession Chains
            </h1>
            <span className="px-2 py-0.5 rounded-full bg-purple-50 dark:bg-purple-950/60 text-purple-700 dark:text-purple-300 text-xs font-semibold border border-purple-200/80 dark:border-purple-800">
              {precedents.length} Links
            </span>
          </div>
          <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5">
            Verified legal and administrative relationships between Uttarakhand Government Orders
          </p>
        </div>
      </div>

      {/* Filter Row */}
      <div className="px-6 py-3 border-b border-slate-200/80 dark:border-slate-800 bg-slate-50/50 dark:bg-[#0c111c] flex flex-wrap items-center gap-3 shrink-0">
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#131926] text-xs text-slate-700 dark:text-slate-200 focus-within:border-purple-400 min-w-[220px]">
          <Search className="w-3.5 h-3.5 text-slate-400" />
          <input
            type="text"
            placeholder="Search citation or GO…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-transparent outline-none w-full placeholder-slate-400 dark:placeholder-slate-500"
          />
        </div>

        <select
          value={relationFilter}
          onChange={(e) => setRelationFilter(e.target.value)}
          className="px-3 py-1.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#131926] text-xs text-slate-700 dark:text-slate-200 outline-none focus:border-purple-400"
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
          <div className="h-64 flex items-center justify-center text-xs text-slate-400 dark:text-slate-500">
            Loading precedent chains…
          </div>
        ) : precedents.length === 0 ? (
          <div className="h-64 flex flex-col items-center justify-center text-center p-6 text-slate-400 dark:text-slate-500">
            <Share2 className="w-10 h-10 stroke-[1.5] text-slate-300 dark:text-slate-600 mb-2" />
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">No precedent relationships found</p>
            <p className="text-xs text-slate-400 dark:text-slate-500 mt-1">
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
                  className="bg-white dark:bg-[#111726] rounded-2xl border border-slate-200/80 dark:border-slate-800 p-4 shadow-xs hover:border-purple-300 dark:hover:border-purple-700 transition-all"
                >
                  <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
                    {/* Source Document */}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-900 dark:text-slate-100 mb-1">
                        <FileText className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400 shrink-0" />
                        <span className="truncate">{pr.source_title}</span>
                      </div>
                      {pr.source_go_number && (
                        <span className="font-mono text-[11px] text-slate-600 dark:text-slate-400 bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded">
                          GO: {pr.source_go_number}
                        </span>
                      )}
                    </div>

                    {/* Relation Badge */}
                    <div className="flex items-center gap-2 shrink-0 my-1 sm:my-0">
                      <span
                        className={`inline-flex items-center px-2.5 py-1 rounded-full border text-[10px] font-bold ${style.bg} ${style.text} ${style.border}`}
                      >
                        {pr.relation_type}
                      </span>
                      <ArrowRight className="w-4 h-4 text-slate-400 shrink-0" />
                    </div>

                    {/* Target / Cited Reference */}
                    <div className="min-w-0 flex-1 sm:text-right">
                      <p className="text-xs font-semibold text-slate-900 dark:text-slate-100 truncate">
                        {pr.target_title || pr.cited_act_or_rule || pr.raw_citation_text}
                      </p>
                      {pr.cited_order_number && (
                        <span className="font-mono text-[11px] text-slate-600 dark:text-slate-400 bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded">
                          Ref: {pr.cited_order_number}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="mt-3 pt-2.5 border-t border-slate-100 dark:border-slate-800/80 text-[11px] text-slate-500 dark:text-slate-400 flex items-center justify-between">
                    <span className="italic truncate pr-4">&quot;{pr.raw_citation_text}&quot;</span>
                    {pr.created_at && (
                      <span className="shrink-0 text-slate-400 dark:text-slate-500">
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
