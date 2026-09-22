'use client';

import type { Citation } from '@/lib/types';
import { FileText, ExternalLink, ShieldCheck, AlertCircle, AlertTriangle, Globe, type LucideIcon } from 'lucide-react';

const STATUS_STYLES: Record<string, { bg: string; text: string; border: string; icon: LucideIcon }> = {
  CURRENT: {
    bg: 'bg-emerald-50',
    text: 'text-emerald-700',
    border: 'border-emerald-200',
    icon: ShieldCheck,
  },
  AMENDED: {
    bg: 'bg-amber-50',
    text: 'text-amber-700',
    border: 'border-amber-200',
    icon: AlertTriangle,
  },
  SUPERSEDED: {
    bg: 'bg-rose-50',
    text: 'text-rose-700',
    border: 'border-rose-200',
    icon: AlertCircle,
  },
  UNCERTAIN: {
    bg: 'bg-purple-50',
    text: 'text-purple-700',
    border: 'border-purple-200',
    icon: AlertCircle,
  },
  EXTERNAL: {
    bg: 'bg-sky-50',
    text: 'text-sky-700',
    border: 'border-sky-200',
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

export default function CitationCard({ citation, index }: CitationCardProps) {
  const isExternal = !!citation.is_external;
  const status = deriveStatus(citation);
  const style = STATUS_STYLES[status] ?? STATUS_STYLES['CURRENT'];
  const StatusIcon = style.icon;
  const targetUrl = citation.external_url || citation.source_url;

  return (
    <div
      className={`rounded-2xl border p-4 shadow-xs my-2 text-sm backdrop-blur-xs transition-all hover:shadow-md ${
        isExternal
          ? 'border-sky-100 bg-sky-50/30 hover:border-sky-200'
          : 'border-gray-100 bg-white/95 hover:border-gray-200'
      }`}
    >
      {/* Header Row */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 font-medium text-gray-800 flex-1 min-w-0">
          <span
            className={`px-1.5 py-0.5 rounded-full flex items-center justify-center text-[10px] font-semibold shrink-0 font-mono ${
              isExternal
                ? 'bg-sky-100 text-sky-700 border border-sky-200'
                : 'bg-gray-100 text-gray-500'
            }`}
          >
            {isExternal ? `WEB-${index + 1}` : index + 1}
          </span>
          {targetUrl ? (
            <a
              href={targetUrl}
              target="_blank"
              rel="noopener noreferrer"
              className={`hover:underline truncate font-medium flex items-center gap-1 ${
                isExternal ? 'text-sky-900 hover:text-sky-700' : 'hover:text-purple-600'
              }`}
            >
              <span>{citation.document_title}</span>
              <ExternalLink className="w-3.5 h-3.5 opacity-60 shrink-0" />
            </a>
          ) : (
            <span className="truncate font-medium">{citation.document_title}</span>
          )}
        </div>

        {/* Status Pill Badge */}
        <span
          className={`shrink-0 inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-medium ${style.bg} ${style.text} ${style.border}`}
        >
          <StatusIcon className="w-3 h-3" />
          <span>{isExternal ? 'EXTERNAL WEB' : status}</span>
        </span>
      </div>

      {/* Metadata Row */}
      <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500">
        <span className="bg-gray-100/80 px-2 py-0.5 rounded-md font-medium text-gray-600">
          {citation.department.replace(/_/g, ' ')}
        </span>
        {citation.external_domain && (
          <span className="font-mono text-sky-700 bg-sky-50 border border-sky-100 px-1.5 py-0.5 rounded">
            Domain: {citation.external_domain}
          </span>
        )}
        {citation.go_number && (
          <span className="font-mono text-gray-700 bg-gray-50 border border-gray-100 px-1.5 py-0.5 rounded">
            GO: {citation.go_number}
          </span>
        )}
        {citation.issue_date && <span>Issued: {citation.issue_date}</span>}
        {!isExternal && <span>Page {citation.page}</span>}
        {citation.section && <span>§ {citation.section}</span>}
      </div>

      {/* Currency banner note if present */}
      {citation.currency_banner && (
        <p className="mt-2 text-xs text-amber-700 bg-amber-50/70 border-l-2 border-amber-400 px-2.5 py-1 rounded-r-md">
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
            className="inline-flex items-center gap-1.5 rounded-xl bg-sky-600 hover:bg-sky-700 text-white px-3 py-1.5 text-xs font-medium shadow-xs transition-all"
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
            className="inline-flex items-center gap-1.5 rounded-xl bg-purple-600 hover:bg-purple-700 text-white px-3 py-1.5 text-xs font-medium shadow-xs transition-all"
          >
            <FileText className="w-3.5 h-3.5" />
            <span>View Source Document</span>
          </a>
        ) : null}
        <span className="text-[10px] text-gray-400 italic">
          {isExternal ? 'External finding • rate-limited & SSRF-safe' : 'Source pointer • not legal advice'}
        </span>
      </div>
    </div>
  );
}
