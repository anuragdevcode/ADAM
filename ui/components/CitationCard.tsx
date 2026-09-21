'use client';

import type { Citation } from '@/lib/types';
import { FileText, ExternalLink, ShieldCheck, AlertCircle, AlertTriangle, type LucideIcon } from 'lucide-react';

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
};

function deriveStatus(citation: Citation): string {
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
  const status = deriveStatus(citation);
  const style = STATUS_STYLES[status] ?? STATUS_STYLES['CURRENT'];
  const StatusIcon = style.icon;

  return (
    <div className="rounded-2xl border border-gray-100 bg-white/95 p-4 shadow-sm my-2 text-sm backdrop-blur-sm transition-all hover:border-gray-200 hover:shadow-md">
      {/* Header Row */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 font-medium text-gray-800 flex-1 min-w-0">
          <span className="w-5 h-5 rounded-full bg-gray-100 flex items-center justify-center text-[10px] font-semibold text-gray-500 shrink-0">
            {index + 1}
          </span>
          {citation.source_url ? (
            <a
              href={citation.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-purple-600 hover:underline truncate font-medium flex items-center gap-1"
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
          <span>{status}</span>
        </span>
      </div>

      {/* Metadata Row */}
      <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500">
        <span className="bg-gray-100/80 px-2 py-0.5 rounded-md font-medium text-gray-600">
          {citation.department.replace(/_/g, ' ')}
        </span>
        {citation.go_number && (
          <span className="font-mono text-gray-700 bg-gray-50 border border-gray-100 px-1.5 py-0.5 rounded">
            GO: {citation.go_number}
          </span>
        )}
        {citation.issue_date && <span>Issued: {citation.issue_date}</span>}
        <span>Page {citation.page}</span>
        {citation.section && <span>§ {citation.section}</span>}
      </div>

      {/* Currency banner note if present */}
      {citation.currency_banner && (
        <p className="mt-2 text-xs text-amber-700 bg-amber-50/70 border-l-2 border-amber-400 px-2.5 py-1 rounded-r-md">
          {citation.currency_banner}
        </p>
      )}

      {/* Source button */}
      {citation.pdf_page_link && (
        <div className="mt-3 flex items-center justify-between">
          <a
            href={citation.pdf_page_link}
            target="_blank"
            rel="noopener noreferrer"
            data-bbox={citation.bbox ? JSON.stringify(citation.bbox) : undefined}
            className="inline-flex items-center gap-1.5 rounded-xl bg-purple-600 hover:bg-purple-700 text-white px-3 py-1.5 text-xs font-medium shadow-sm transition-all"
          >
            <FileText className="w-3.5 h-3.5" />
            <span>View Source Document</span>
          </a>
          <span className="text-[10px] text-gray-400 italic">
            Source pointer • not legal advice
          </span>
        </div>
      )}
    </div>
  );
}
