'use client';

import React, { memo } from 'react';
import type { Citation } from '@/lib/types';
import { FileText, ExternalLink, ShieldCheck, AlertCircle, AlertTriangle, Globe, type LucideIcon } from 'lucide-react';

const STATUS_STYLES: Record<string, { bg: string; text: string; border: string; icon: LucideIcon }> = {
  CURRENT: {
    bg: 'bg-emerald-50 dark:bg-emerald-950/60',
    text: 'text-emerald-700 dark:text-emerald-300',
    border: 'border-emerald-200 dark:border-emerald-800',
    icon: ShieldCheck,
  },
  AMENDED: {
    bg: 'bg-amber-50 dark:bg-amber-950/60',
    text: 'text-amber-700 dark:text-amber-300',
    border: 'border-amber-200 dark:border-amber-800',
    icon: AlertTriangle,
  },
  SUPERSEDED: {
    bg: 'bg-rose-50 dark:bg-rose-950/60',
    text: 'text-rose-700 dark:text-rose-300',
    border: 'border-rose-200 dark:border-rose-800',
    icon: AlertCircle,
  },
  UNCERTAIN: {
    bg: 'bg-purple-50 dark:bg-purple-950/60',
    text: 'text-purple-700 dark:text-purple-300',
    border: 'border-purple-200 dark:border-purple-800',
    icon: AlertCircle,
  },
  EXTERNAL: {
    bg: 'bg-sky-50 dark:bg-sky-950/60',
    text: 'text-sky-700 dark:text-sky-300',
    border: 'border-sky-200 dark:border-sky-800',
    icon: Globe,
  },
};

function deriveStatus(citation: Citation): string {
  if (citation.is_external) return 'EXTERNAL';
  if (citation.currency_banner) {
    const b = citation.currency_banner.toUpperCase();
    if (b.includes('SUPERSED')) return 'SUPERSEDED';
    if (b.includes('AMEND')) return 'AMENDED';
    if (b.includes('UNCERTAIN') || b.includes('NOT CONCLUSIVE')) return 'UNCERTAIN';
  }
  return 'CURRENT';
}

interface CitationCardProps {
  citation: Citation;
  index: number;
}

function CitationCardComponent({ citation, index }: CitationCardProps) {
  const isExternal = !!citation.is_external;
  const status = deriveStatus(citation);
  const style = STATUS_STYLES[status] ?? STATUS_STYLES['CURRENT'];
  const StatusIcon = style.icon;
  const targetUrl = citation.external_url || citation.source_url;

  return (
    <div
      className={`rounded-2xl border p-4 shadow-xs my-2 text-xs sm:text-sm transition-all hover:shadow-md ${
        isExternal
          ? 'border-sky-100 dark:border-sky-900/60 bg-sky-50/30 dark:bg-sky-950/20 hover:border-sky-300 dark:hover:border-sky-700'
          : 'border-slate-200/80 dark:border-slate-800 bg-white dark:bg-[#131926] hover:border-purple-200 dark:hover:border-purple-800/80'
      }`}
    >
      {/* Header Row */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 font-medium text-slate-900 dark:text-slate-100 flex-1 min-w-0">
          <span
            className={`px-1.5 py-0.5 rounded-full flex items-center justify-center text-[10px] font-semibold shrink-0 font-mono ${
              isExternal
                ? 'bg-sky-100 dark:bg-sky-900/80 text-sky-700 dark:text-sky-300 border border-sky-200 dark:border-sky-700'
                : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400'
            }`}
          >
            {isExternal ? `WEB-${index + 1}` : index + 1}
          </span>
          {targetUrl ? (
            <a
              href={targetUrl}
              target="_blank"
              rel="noopener noreferrer"
              className={`hover:underline truncate font-semibold flex items-center gap-1.5 ${
                isExternal ? 'text-sky-900 dark:text-sky-200 hover:text-sky-700 dark:hover:text-sky-300' : 'hover:text-purple-600 dark:hover:text-purple-400'
              }`}
            >
              <span>{citation.document_title}</span>
              <ExternalLink className="w-3.5 h-3.5 opacity-60 shrink-0" />
            </a>
          ) : (
            <span className="truncate font-semibold">{citation.document_title}</span>
          )}
        </div>

        {/* Status Pill Badge */}
        <span
          className={`shrink-0 inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[10px] sm:text-[11px] font-semibold ${style.bg} ${style.text} ${style.border}`}
        >
          <StatusIcon className="w-3 h-3" />
          <span>{isExternal ? 'EXTERNAL WEB' : status}</span>
        </span>
      </div>

      {/* Metadata Row */}
      <div className="mt-2.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 text-[11px] text-slate-500 dark:text-slate-400">
        <span className="bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded-md font-medium text-slate-700 dark:text-slate-300">
          {citation.department.replace(/_/g, ' ')}
        </span>
        {citation.external_domain && (
          <span className="font-mono text-sky-700 dark:text-sky-300 bg-sky-50 dark:bg-sky-950/60 border border-sky-200 dark:border-sky-800 px-1.5 py-0.5 rounded">
            Domain: {citation.external_domain}
          </span>
        )}
        {citation.go_number && (
          <span className="font-mono text-slate-700 dark:text-slate-300 bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 px-1.5 py-0.5 rounded">
            GO: {citation.go_number}
          </span>
        )}
        {citation.issue_date && <span>Issued: {citation.issue_date}</span>}
        {!isExternal && <span>Page {citation.page}</span>}
        {citation.section && <span>§ {citation.section}</span>}
      </div>

      {/* Currency banner note if present */}
      {citation.currency_banner && (
        <p className="mt-2 text-xs text-amber-800 dark:text-amber-200 bg-amber-50/80 dark:bg-amber-950/40 border-l-2 border-amber-500 px-2.5 py-1 rounded-r-md">
          {citation.currency_banner}
        </p>
      )}

      {/* Source button */}
      <div className="mt-3 flex items-center justify-between">
        {isExternal && targetUrl ? (
          <a
            href={targetUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 rounded-xl bg-sky-600 hover:bg-sky-700 text-white px-3 py-1.5 text-xs font-semibold shadow-xs transition-all"
          >
            <Globe className="w-3.5 h-3.5" />
            <span>Visit External Web Source</span>
          </a>
        ) : citation.pdf_page_link ? (
          <a
            href={citation.pdf_page_link}
            target="_blank"
            rel="noopener noreferrer"
            data-bbox={citation.bbox ? JSON.stringify(citation.bbox) : undefined}
            className="inline-flex items-center gap-1.5 rounded-xl bg-purple-600 hover:bg-purple-700 text-white px-3 py-1.5 text-xs font-semibold shadow-xs transition-all"
          >
            <FileText className="w-3.5 h-3.5" />
            <span>View Source Document</span>
          </a>
        ) : null}
        <span className="text-[10px] text-slate-400 dark:text-slate-500 italic ml-auto">
          {isExternal ? 'External finding • rate-limited & SSRF-safe' : 'Source pointer • sovereign verified'}
        </span>
      </div>
    </div>
  );
}

export default memo(CitationCardComponent);
