'use client';

import React, { useState } from 'react';
import type { OperationalStatusEvent } from '@/lib/types';
import {
  ShieldCheck,
  Search,
  FileText,
  Clock,
  Cpu,
  Sparkles,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ChevronDown,
  ChevronUp,
  Layers,
  Fingerprint,
} from 'lucide-react';

interface ExecutionStatusProps {
  events?: OperationalStatusEvent[];
  isStreaming?: boolean;
  hasError?: boolean;
  isNoAnswer?: boolean;
}

const STAGE_CONFIG: Record<
  string,
  { label: string; icon: React.ComponentType<{ className?: string }> }
> = {
  security: { label: 'Security & Clearance', icon: ShieldCheck },
  query: { label: 'Intent Classification', icon: Layers },
  retrieval: { label: 'Repository Search', icon: Search },
  evidence: { label: 'Evidence Packet', icon: FileText },
  currency: { label: 'Currency Verification', icon: Clock },
  model: { label: 'Model Runtime', icon: Cpu },
  generation: { label: 'Governed Synthesis', icon: Sparkles },
  grounding: { label: 'Answer Grounding', icon: CheckCircle2 },
  execution: { label: 'Pipeline Lifecycle', icon: CheckCircle2 },
};

function formatStageName(stage: string): string {
  return STAGE_CONFIG[stage]?.label || stage.charAt(0).toUpperCase() + stage.slice(1);
}

function getStageIcon(stage: string) {
  return STAGE_CONFIG[stage]?.icon || Sparkles;
}

export default function ExecutionStatus({
  events = [],
  isStreaming = false,
  hasError = false,
  isNoAnswer = false,
}: ExecutionStatusProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (!events || events.length === 0) {
    if (isStreaming) {
      return (
        <div className="flex items-center gap-2 px-3 py-1.5 mb-2 text-xs font-medium text-purple-700 bg-purple-50/70 border border-purple-100 rounded-lg w-fit animate-pulse">
          <span className="w-2 h-2 rounded-full bg-purple-600 animate-ping" />
          <span>Initializing governed administrative pipeline...</span>
        </div>
      );
    }
    return null;
  }

  // Deduplicate and group into canonical progression
  const sortedEvents = [...events].sort((a, b) => a.sequence - b.sequence);
  const totalDurationMs = sortedEvents.reduce((acc, ev) => acc + (ev.duration_ms || 0), 0);
  const lastEvent = sortedEvents[sortedEvents.length - 1];

  // Grounding or completion summary metrics
  const evidenceEvent = sortedEvents.find(
    (e) => e.type === 'evidence.completed' || e.stage === 'evidence',
  );
  const groundingEvent = sortedEvents.find(
    (e) => e.type === 'answer.grounded' || e.type === 'answer.abstained',
  );
  const selectedCount = evidenceEvent?.data?.selected_count;
  const citationCount = groundingEvent?.data?.citation_count;

  // If streaming, render live animated progression checklist
  if (isStreaming) {
    // Show only the most recent 4 events to keep chat uncluttered
    const displayEvents = sortedEvents.slice(-4);

    return (
      <div className="mb-3 px-3 py-2 bg-slate-900/5 dark:bg-slate-900/60 border border-purple-200/60 dark:border-purple-900/40 rounded-xl text-xs space-y-1.5 transition-all">
        <div className="flex items-center justify-between text-[11px] font-semibold tracking-wider text-purple-800 dark:text-purple-300 uppercase">
          <div className="flex items-center gap-1.5">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-purple-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-purple-600"></span>
            </span>
            <span>Governance Execution Pipeline</span>
          </div>
          <span className="text-[10px] text-slate-400 font-mono">
            step {lastEvent.sequence}
          </span>
        </div>

        <div className="space-y-1 pt-0.5">
          {displayEvents.map((ev, idx) => {
            const isLast = idx === displayEvents.length - 1;

            return (
              <div
                key={`${ev.sequence}-${ev.type}`}
                className={`flex items-center gap-2 text-xs transition-opacity duration-200 ${
                  isLast
                    ? 'text-slate-900 dark:text-slate-100 font-medium'
                    : 'text-slate-500 dark:text-slate-400'
                }`}
              >
                {ev.status === 'failed' ? (
                  <XCircle className="w-3.5 h-3.5 text-red-500 shrink-0" />
                ) : ev.status === 'warning' ? (
                  <AlertTriangle className="w-3.5 h-3.5 text-amber-500 shrink-0" />
                ) : isLast ? (
                  <span className="w-3.5 h-3.5 flex items-center justify-center">
                    <span className="w-1.5 h-1.5 rounded-full bg-purple-600 animate-pulse" />
                  </span>
                ) : (
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400 shrink-0" />
                )}

                <span className="truncate">{ev.message}</span>

                {ev.duration_ms != null && (
                  <span className="text-[10px] text-slate-400 font-mono ml-auto">
                    {ev.duration_ms.toFixed(0)}ms
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // Completed or stopped state: show collapsed summary badge with expandable drawer
  const isAbstained = isNoAnswer || lastEvent.type === 'answer.abstained';

  let badgeTitle = 'Grounded Response';
  let badgeColor = 'bg-purple-50/80 text-purple-800 border-purple-200 dark:bg-purple-950/30 dark:text-purple-300 dark:border-purple-800/40';

  if (hasError || lastEvent.status === 'failed') {
    badgeTitle = 'Pipeline Interrupted';
    badgeColor = 'bg-red-50/80 text-red-700 border-red-200 dark:bg-red-950/30 dark:text-red-400 dark:border-red-900/40';
  } else if (isAbstained) {
    badgeTitle = 'Repository Boundary Abstained';
    badgeColor = 'bg-amber-50/80 text-amber-800 border-amber-200 dark:bg-amber-950/30 dark:text-amber-300 dark:border-amber-800/40';
  } else if (citationCount != null && citationCount > 0) {
    badgeTitle = `Grounded in ${citationCount} official ${citationCount === 1 ? 'source' : 'sources'}`;
  } else if (selectedCount != null && selectedCount > 0) {
    badgeTitle = `Grounded in ${selectedCount} official ${selectedCount === 1 ? 'record' : 'records'}`;
  }

  return (
    <div className="mb-3">
      {/* Collapsed Badge */}
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className={`inline-flex items-center gap-2 px-2.5 py-1 text-xs rounded-lg border transition-colors hover:brightness-95 select-none focus:outline-none focus:ring-1 focus:ring-purple-400 ${badgeColor}`}
        aria-expanded={isExpanded}
        title="Click to view detailed governance audit trail"
      >
        {hasError ? (
          <XCircle className="w-3.5 h-3.5 text-red-500" />
        ) : isAbstained ? (
          <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
        ) : (
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
        )}

        <span className="font-medium">{badgeTitle}</span>

        {totalDurationMs > 0 && (
          <span className="text-[10px] opacity-70 font-mono border-l border-current/20 pl-1.5 ml-0.5">
            {totalDurationMs > 1000 ? `${(totalDurationMs / 1000).toFixed(1)}s` : `${Math.round(totalDurationMs)}ms`}
          </span>
        )}

        <span className="flex items-center gap-0.5 text-[11px] opacity-80 ml-1 underline decoration-dotted underline-offset-2">
          {isExpanded ? 'Hide audit' : 'How this was produced'}
          {isExpanded ? (
            <ChevronUp className="w-3 h-3 ml-0.5" />
          ) : (
            <ChevronDown className="w-3 h-3 ml-0.5" />
          )}
        </span>
      </button>

      {/* Expandable Audit Timeline Drawer */}
      {isExpanded && (
        <div className="mt-2 p-3 bg-slate-900/5 dark:bg-slate-900/80 border border-slate-200 dark:border-slate-800 rounded-xl text-xs space-y-2 animate-in fade-in duration-150">
          <div className="flex items-center justify-between pb-1.5 border-b border-slate-200 dark:border-slate-800">
            <span className="font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
              <Fingerprint className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400" />
              Administrative Governance Audit Trail
            </span>
            {lastEvent.trace_id && (
              <span className="font-mono text-[10px] text-slate-400">
                trace: {lastEvent.trace_id}
              </span>
            )}
          </div>

          <div className="relative pl-3 space-y-2 border-l border-purple-200 dark:border-purple-900/50 my-1">
            {sortedEvents.map((ev) => {
              const Icon = getStageIcon(ev.stage);
              const isWarning = ev.status === 'warning';
              const isFailed = ev.status === 'failed';

              return (
                <div key={`${ev.sequence}-${ev.type}`} className="relative group">
                  {/* Timeline dot */}
                  <div
                    className={`absolute -left-[19px] top-0.5 w-3 h-3 rounded-full border-2 bg-white dark:bg-slate-900 ${
                      isFailed
                        ? 'border-red-500'
                        : isWarning
                        ? 'border-amber-500'
                        : 'border-purple-500'
                    }`}
                  />

                  <div className="flex items-start justify-between gap-2">
                    <div className="space-y-0.5">
                      <div className="flex items-center gap-1.5 font-medium text-slate-800 dark:text-slate-200">
                        <Icon className="w-3 h-3 text-slate-500" />
                        <span>{formatStageName(ev.stage)}</span>
                        {isWarning && (
                          <span className="px-1.5 py-0.2 rounded text-[10px] bg-amber-100 dark:bg-amber-950 text-amber-800 dark:text-amber-300 font-normal">
                            Warning
                          </span>
                        )}
                        {isFailed && (
                          <span className="px-1.5 py-0.2 rounded text-[10px] bg-red-100 dark:bg-red-950 text-red-800 dark:text-red-300 font-normal">
                            Failed
                          </span>
                        )}
                      </div>
                      <div className="text-slate-600 dark:text-slate-400 text-[11px] leading-relaxed">
                        {ev.message}
                      </div>

                      {/* Safe context pills */}
                      {ev.data && Object.keys(ev.data).length > 0 && (
                        <div className="flex flex-wrap gap-1.5 pt-1">
                          {ev.data.records_considered != null && (
                            <span className="px-1.5 py-0.5 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 rounded text-[10px] font-mono">
                              {ev.data.records_considered} evaluated
                            </span>
                          )}
                          {ev.data.selected_count != null && (
                            <span className="px-1.5 py-0.5 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 rounded text-[10px] font-mono">
                              {ev.data.selected_count} passages selected
                            </span>
                          )}
                          {ev.data.model_name && (
                            <span className="px-1.5 py-0.5 bg-purple-50 dark:bg-purple-950/40 text-purple-700 dark:text-purple-300 rounded text-[10px] font-mono">
                              runtime: {ev.data.model_name}
                            </span>
                          )}
                          {ev.data.query_language && (
                            <span className="px-1.5 py-0.5 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 rounded text-[10px]">
                              lang: {ev.data.query_language}
                            </span>
                          )}
                        </div>
                      )}
                    </div>

                    {ev.duration_ms != null && (
                      <span className="text-[10px] text-slate-400 font-mono shrink-0">
                        {ev.duration_ms.toFixed(0)}ms
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="text-[10px] text-slate-400 pt-1 border-t border-slate-200/50 dark:border-slate-800/50 flex items-center justify-between">
            <span>Uttarakhand Public Records System • Governance Phase 06</span>
            <span>Deterministic Grounding</span>
          </div>
        </div>
      )}
    </div>
  );
}
