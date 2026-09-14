'use client';

import type { Citation } from '@/lib/types';
import {
  FileText,
  ExternalLink,
  ShieldCheck,
  AlertCircle,
  AlertTriangle,
  type LucideIcon,
} from 'lucide-react';

/** Currency status drives the badge colour; tokens keep it theme-aware. */
const STATUS_STYLES: Record<string, { className: string; icon: LucideIcon }> = {
  CURRENT: { className: 'bg-ok-soft text-ok border-ok', icon: ShieldCheck },
  AMENDED: { className: 'bg-warn-soft text-warn border-warn', icon: AlertTriangle },
  SUPERSEDED: { className: 'bg-danger-soft text-danger border-danger', icon: AlertCircle },
  UNCERTAIN: { className: 'bg-brand-soft text-brand border-brand-border', icon: AlertCircle },
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
    <div className="rounded-card border border-line bg-surface p-3.5 text-sm transition-colors hover:border-brand-border">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <span className="w-5 h-5 rounded-md bg-surface-sunken flex items-center justify-center text-[10px] font-semibold text-ink-muted shrink-0 tabular">
            {index + 1}
          </span>
          {citation.source_url ? (
            <a
              href={citation.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-ink hover:text-brand hover:underline truncate text-xs font-semibold flex items-center gap-1 min-w-0"
            >
              <span className="truncate">{citation.document_title}</span>
              <ExternalLink className="w-3 h-3 opacity-60 shrink-0" />
            </a>
          ) : (
            <span className="truncate text-xs font-semibold text-ink">
              {citation.document_title}
            </span>
          )}
        </div>

        <span
          className={`shrink-0 inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${style.className}`}
        >
          <StatusIcon className="w-3 h-3" />
          <span>{status}</span>
        </span>
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-2xs text-ink-muted">
        <span className="bg-surface-sunken px-1.5 py-0.5 rounded font-medium text-ink-secondary">
          {citation.department.replace(/_/g, ' ')}
        </span>
        {citation.go_number && (
          <span className="font-mono text-ink-secondary bg-surface-sunken border border-line px-1.5 py-0.5 rounded tabular">
            {citation.go_number}
          </span>
        )}
        {citation.issue_date && <span className="tabular">Issued {citation.issue_date}</span>}
        <span className="tabular">Page {citation.page}</span>
        {citation.section && <span>§ {citation.section}</span>}
      </div>

      {citation.currency_banner && (
        <p className="mt-2 text-2xs text-warn bg-warn-soft border-l-2 border-warn px-2.5 py-1.5 rounded-r-md">
          {citation.currency_banner}
        </p>
      )}

      {citation.pdf_page_link && (
        <div className="mt-3 flex items-center justify-between gap-2">
          <a
            href={citation.pdf_page_link}
            target="_blank"
            rel="noopener noreferrer"
            data-bbox={citation.bbox ? JSON.stringify(citation.bbox) : undefined}
            className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface hover:bg-brand-soft hover:border-brand-border text-ink-secondary hover:text-brand px-2.5 py-1.5 text-2xs font-semibold transition-colors"
          >
            <FileText className="w-3 h-3" />
            <span>View source document</span>
          </a>
          <span className="text-[10px] text-ink-faint">Source pointer · not legal advice</span>
        </div>
      )}
    </div>
  );
}
