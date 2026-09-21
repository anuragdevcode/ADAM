'use client';

import React, { useState } from 'react';
import type { OperationalStatusEvent, StateTransitionTrailItem } from '@/lib/types';
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
  ArrowRight,
  Activity,
  Gauge,
  BarChart2,
  Info,
} from 'lucide-react';

interface ExecutionStatusProps {
  events?: OperationalStatusEvent[];
  stateHistory?: StateTransitionTrailItem[];
  perStageLatency?: Record<string, number>;
  abstentionReason?: string | null;
  latencyMs?: number;
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

const STATE_META: Record<
  string,
  { label: string; stageNumber?: number; icon: React.ComponentType<{ className?: string }> }
> = {
  AUTHENTICATE: { label: 'Identity & Classification Clearance', stageNumber: 1, icon: ShieldCheck },
  CLASSIFY_REQUEST: { label: 'Query Intent & Jurisdiction Routing', stageNumber: 2, icon: Layers },
  RETRIEVE: { label: 'Single Authorized Hybrid Retrieval', stageNumber: 3, icon: Search },
  EVIDENCE_CURRENCY_CHECKS: { label: 'Evidence Packet & Currency Checks', stageNumber: 4, icon: Clock },
  GENERATE_OR_ABSTAIN: { label: 'Governed Model Synthesis / Abstain', stageNumber: 5, icon: Sparkles },
  VALIDATE_CITATIONS: { label: 'Citation & Claim Grounding Check', stageNumber: 6, icon: CheckCircle2 },
  AUDIT: { label: 'Governance Audit & Redaction', stageNumber: 7, icon: Fingerprint },
  COMPLETED: { label: 'Pipeline Completed Successfully', icon: CheckCircle2 },
  ABSTAINED: { label: 'Deterministic Policy Abstention', icon: AlertTriangle },
  FAILED: { label: 'Security / Execution Termination', icon: XCircle },
};

function formatStageName(stage: string): string {
  return STAGE_CONFIG[stage]?.label || stage.charAt(0).toUpperCase() + stage.slice(1);
}

function getStageIcon(stage: string) {
  return STAGE_CONFIG[stage]?.icon || Sparkles;
}

function getStateInfo(stateName: string) {
  return STATE_META[stateName] || {
    label: stateName.replace(/_/g, ' '),
    icon: Sparkles,
  };
}

export default function ExecutionStatus({
  events = [],
  stateHistory = [],
  perStageLatency = {},
  abstentionReason,
  latencyMs,
  isStreaming = false,
  hasError = false,
  isNoAnswer = false,
}: ExecutionStatusProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [activeTab, setActiveTab] = useState<'trail' | 'telemetry'>('trail');

  const hasEvents = events && events.length > 0;
  const hasTrail = stateHistory && stateHistory.length > 0;

  if (!hasEvents && !hasTrail) {
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

  // Deduplicate and group operational events
  const sortedEvents = [...events].sort((a, b) => a.sequence - b.sequence);
  const eventsDurationMs = sortedEvents.reduce((acc, ev) => acc + (ev.duration_ms || 0), 0);
  const lastEvent = sortedEvents[sortedEvents.length - 1] || null;

  // Grounding or completion summary metrics
  const evidenceEvent = sortedEvents.find(
    (e) => e.type === 'evidence.completed' || e.stage === 'evidence',
  );
  const groundingEvent = sortedEvents.find(
    (e) => e.type === 'answer.grounded' || e.type === 'answer.abstained',
  );
  const selectedCount = evidenceEvent?.data?.selected_count;
  const citationCount = groundingEvent?.data?.citation_count;

  // Derive per-stage latency metrics
  const stageEntries: { stage: string; duration: number }[] = [];
  if (perStageLatency && Object.keys(perStageLatency).length > 0) {
    for (const [st, dur] of Object.entries(perStageLatency)) {
      stageEntries.push({ stage: st, duration: Number(dur) || 0 });
    }
  } else if (hasTrail) {
    for (const t of stateHistory) {
      if (t.duration_ms != null && t.duration_ms > 0) {
        stageEntries.push({
          stage: t.stage || t.from || 'STAGE',
          duration: t.duration_ms,
        });
      }
    }
  }

  const totalCalculatedLatency = latencyMs || (
    stageEntries.length > 0
      ? stageEntries.reduce((acc, s) => acc + s.duration, 0)
      : eventsDurationMs
  );

  const activeStageCount = stageEntries.length > 0 ? stageEntries.length : (hasTrail ? stateHistory.length : 1);
  const avgStageLatency = activeStageCount > 0 ? totalCalculatedLatency / activeStageCount : 0;

  // Find bottleneck stage (highest latency)
  const bottleneckStage = stageEntries.length > 0
    ? [...stageEntries].sort((a, b) => b.duration - a.duration)[0]
    : null;

  // Determine effective abstention
  const isAbstained = isNoAnswer || (lastEvent && lastEvent.type === 'answer.abstained') || (
    hasTrail && stateHistory.some((t) => t.to === 'ABSTAINED' || t.abstention_reason)
  );

  const effectiveAbstentionReason = abstentionReason || (
    hasTrail
      ? stateHistory.find((t) => t.abstention_reason)?.abstention_reason
      : null
  );

  // If streaming, render live animated progression checklist
  if (isStreaming) {
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
          {lastEvent && (
            <span className="text-[10px] text-slate-400 font-mono">
              step {lastEvent.sequence}
            </span>
          )}
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

  // Completed or stopped state badge
  let badgeTitle = 'Grounded Response';
  let badgeColor = 'bg-purple-50/80 text-purple-800 border-purple-200 dark:bg-purple-950/30 dark:text-purple-300 dark:border-purple-800/40';

  if (hasError || (lastEvent && lastEvent.status === 'failed')) {
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
      {/* Collapsed Badge with reasoning trail toggle */}
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className={`inline-flex items-center gap-2 px-2.5 py-1 text-xs rounded-lg border transition-colors hover:brightness-95 select-none focus:outline-none focus:ring-1 focus:ring-purple-400 ${badgeColor}`}
        aria-expanded={isExpanded}
        title="Click to inspect the state-transition reasoning trail and per-stage latency"
      >
        {hasError ? (
          <XCircle className="w-3.5 h-3.5 text-red-500" />
        ) : isAbstained ? (
          <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
        ) : (
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
        )}

        <span className="font-medium">{badgeTitle}</span>

        {totalCalculatedLatency > 0 && (
          <span className="text-[10px] opacity-75 font-mono border-l border-current/20 pl-1.5 ml-0.5">
            {totalCalculatedLatency > 1000 ? `${(totalCalculatedLatency / 1000).toFixed(2)}s` : `${Math.round(totalCalculatedLatency)}ms`}
          </span>
        )}

        <span className="flex items-center gap-0.5 text-[11px] opacity-90 ml-1 font-semibold underline decoration-dotted underline-offset-2">
          {isExpanded ? 'Hide reasoning trail' : 'Show reasoning trail'}
          {isExpanded ? (
            <ChevronUp className="w-3 h-3 ml-0.5" />
          ) : (
            <ChevronDown className="w-3 h-3 ml-0.5" />
          )}
        </span>
      </button>

      {/* Expandable Reasoning Trail & Latency Dashboard */}
      {isExpanded && (
        <div className="mt-2.5 p-3.5 bg-slate-900/5 dark:bg-slate-900/90 border border-slate-200 dark:border-slate-800 rounded-2xl text-xs space-y-3 animate-in fade-in duration-150 shadow-xs">
          
          {/* Header & Tabs */}
          <div className="flex items-center justify-between pb-2 border-b border-slate-200 dark:border-slate-800 flex-wrap gap-2">
            <div className="flex items-center gap-2">
              <span className="font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-1.5 text-xs">
                <Activity className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                Administrative Reasoning Trail
              </span>
              <span className="text-[10px] text-slate-400 bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 rounded font-mono">
                7-Stage State Machine
              </span>
            </div>

            {hasEvents && hasTrail && (
              <div className="flex items-center p-0.5 bg-slate-200/60 dark:bg-slate-800/80 rounded-lg text-[11px]">
                <button
                  type="button"
                  onClick={() => setActiveTab('trail')}
                  className={`px-2.5 py-0.5 rounded-md font-medium transition-colors ${
                    activeTab === 'trail'
                      ? 'bg-white dark:bg-slate-700 text-purple-700 dark:text-purple-300 shadow-xs'
                      : 'text-slate-600 dark:text-slate-400 hover:text-slate-900'
                  }`}
                >
                  Stage Trail &amp; Latency
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('telemetry')}
                  className={`px-2.5 py-0.5 rounded-md font-medium transition-colors ${
                    activeTab === 'telemetry'
                      ? 'bg-white dark:bg-slate-700 text-purple-700 dark:text-purple-300 shadow-xs'
                      : 'text-slate-600 dark:text-slate-400 hover:text-slate-900'
                  }`}
                >
                  Telemetry Events ({sortedEvents.length})
                </button>
              </div>
            )}
          </div>

          {/* Average Response Time & Latency Metrics Bar */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-left">
            <div className="p-2 bg-white/70 dark:bg-slate-800/50 border border-slate-200/70 dark:border-slate-700/60 rounded-xl">
              <div className="text-[10px] font-medium text-slate-400 uppercase tracking-wider flex items-center gap-1">
                <Clock className="w-3 h-3 text-purple-500" />
                <span>Response Time</span>
              </div>
              <div className="text-sm font-semibold font-mono text-slate-800 dark:text-slate-100 mt-0.5">
                {totalCalculatedLatency > 1000 ? `${(totalCalculatedLatency / 1000).toFixed(2)}s` : `${Math.round(totalCalculatedLatency)}ms`}
              </div>
            </div>

            <div className="p-2 bg-white/70 dark:bg-slate-800/50 border border-slate-200/70 dark:border-slate-700/60 rounded-xl">
              <div className="text-[10px] font-medium text-slate-400 uppercase tracking-wider flex items-center gap-1">
                <Gauge className="w-3 h-3 text-emerald-500" />
                <span>Avg Stage Time</span>
              </div>
              <div className="text-sm font-semibold font-mono text-slate-800 dark:text-slate-100 mt-0.5">
                {avgStageLatency.toFixed(1)}ms
              </div>
            </div>

            <div className="p-2 bg-white/70 dark:bg-slate-800/50 border border-slate-200/70 dark:border-slate-700/60 rounded-xl">
              <div className="text-[10px] font-medium text-slate-400 uppercase tracking-wider flex items-center gap-1">
                <BarChart2 className="w-3 h-3 text-blue-500" />
                <span>Active Stages</span>
              </div>
              <div className="text-sm font-semibold font-mono text-slate-800 dark:text-slate-100 mt-0.5">
                {activeStageCount} of 7
              </div>
            </div>

            <div className="p-2 bg-white/70 dark:bg-slate-800/50 border border-slate-200/70 dark:border-slate-700/60 rounded-xl">
              <div className="text-[10px] font-medium text-slate-400 uppercase tracking-wider flex items-center gap-1">
                <Activity className="w-3 h-3 text-amber-500" />
                <span>Bottleneck</span>
              </div>
              <div className="text-xs font-semibold truncate font-mono text-slate-800 dark:text-slate-100 mt-0.5" title={bottleneckStage ? `${bottleneckStage.stage} (${Math.round(bottleneckStage.duration)}ms)` : 'N/A'}>
                {bottleneckStage ? `${bottleneckStage.duration.toFixed(0)}ms (${bottleneckStage.stage})` : 'N/A'}
              </div>
            </div>
          </div>

          {/* Abstention Rationale Callout Card */}
          {isAbstained && (
            <div className="p-2.5 rounded-xl border border-amber-200/80 bg-amber-50/70 dark:bg-amber-950/20 dark:border-amber-800/50 text-left">
              <div className="flex items-center gap-1.5 text-amber-900 dark:text-amber-200 font-semibold text-xs">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                <span>Administrative Abstention Rationale</span>
              </div>
              <p className="mt-1 text-xs text-amber-800/90 dark:text-amber-300/90 leading-relaxed">
                {effectiveAbstentionReason || 'The query cannot be substantiated from approved Uttarakhand Public Records within the current user clearance boundary.'}
              </p>
              <div className="mt-1.5 flex items-center gap-2 text-[10px] text-amber-700 dark:text-amber-400">
                <span className="inline-flex items-center gap-1">
                  <ShieldCheck className="w-3 h-3" /> Non-hallucinatory guarantee
                </span>
                <span>•</span>
                <span>Deterministic Model Controls (Phase 04)</span>
              </div>
            </div>
          )}

          {/* Tab Content 1: State-Transition Reasoning Trail */}
          {activeTab === 'trail' && (
            <div className="space-y-2 pt-1 text-left">
              <div className="text-[11px] font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider flex items-center justify-between">
                <span>Deterministic State Transitions</span>
                <span className="text-[10px] text-slate-400 font-normal">Per-Stage Latency &amp; Bounds</span>
              </div>

              {hasTrail ? (
                <div className="space-y-1.5">
                  {stateHistory.map((trans, idx) => {
                    const fromInfo = getStateInfo(trans.from);
                    const StageIcon = fromInfo.icon;
                    const duration = trans.duration_ms || 0;
                    const percent = totalCalculatedLatency > 0 ? Math.min(100, Math.round((duration / totalCalculatedLatency) * 100)) : 0;
                    const isAbstainTrans = trans.to === 'ABSTAINED' || !!trans.abstention_reason;
                    const isFailTrans = trans.to === 'FAILED';

                    return (
                      <div
                        key={`${trans.from}-${trans.to}-${idx}`}
                        className={`p-2 rounded-xl border transition-all ${
                          isAbstainTrans
                            ? 'bg-amber-50/40 border-amber-200 dark:bg-amber-950/20 dark:border-amber-800/40'
                            : isFailTrans
                            ? 'bg-red-50/40 border-red-200 dark:bg-red-950/20 dark:border-red-800/40'
                            : 'bg-white/80 dark:bg-slate-800/60 border-slate-200/80 dark:border-slate-700/60'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2 flex-wrap">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="w-5 h-5 rounded-md bg-purple-50 dark:bg-purple-950/60 text-purple-700 dark:text-purple-300 flex items-center justify-center">
                              <StageIcon className="w-3 h-3" />
                            </span>
                            <span className="font-semibold text-xs text-slate-800 dark:text-slate-200">
                              {fromInfo.label}
                            </span>
                            <ArrowRight className="w-3 h-3 text-slate-400 shrink-0" />
                            <span className={`font-medium text-[11px] px-1.5 py-0.5 rounded ${
                              isAbstainTrans
                                ? 'bg-amber-100 text-amber-800 dark:bg-amber-900/60 dark:text-amber-200'
                                : isFailTrans
                                ? 'bg-red-100 text-red-800 dark:bg-red-900/60 dark:text-red-200'
                                : 'bg-slate-100 text-slate-700 dark:bg-slate-700 dark:text-slate-300'
                            }`}>
                              {trans.to}
                            </span>
                          </div>

                          <div className="flex items-center gap-2 shrink-0 ml-auto font-mono text-[11px]">
                            {duration > 0 && (
                              <span className="font-semibold text-slate-700 dark:text-slate-300">
                                {duration.toFixed(1)}ms
                              </span>
                            )}
                            <span className="text-[10px] text-slate-400">
                              ({percent}%)
                            </span>
                          </div>
                        </div>

                        {/* Latency proportion bar */}
                        {duration > 0 && totalCalculatedLatency > 0 && (
                          <div className="w-full h-1 bg-slate-100 dark:bg-slate-700 rounded-full mt-1.5 overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all duration-300 ${
                                isAbstainTrans ? 'bg-amber-500' : isFailTrans ? 'bg-red-500' : 'bg-purple-600 dark:bg-purple-400'
                              }`}
                              style={{ width: `${Math.max(4, percent)}%` }}
                            />
                          </div>
                        )}

                        {trans.notes && (
                          <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-1 leading-normal">
                            {trans.notes}
                          </div>
                        )}

                        {trans.abstention_reason && (
                          <div className="text-[10px] font-medium text-amber-700 dark:text-amber-300 mt-1 flex items-center gap-1">
                            <Info className="w-3 h-3 shrink-0" />
                            <span>Abstention: {trans.abstention_reason}</span>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="p-3 text-center text-slate-400 text-xs">
                  Reasoning transitions will be displayed as steps execute.
                </div>
              )}
            </div>
          )}

          {/* Tab Content 2: Telemetry Events Timeline */}
          {activeTab === 'telemetry' && hasEvents && (
            <div className="relative pl-3 space-y-2 border-l border-purple-200 dark:border-purple-900/50 my-1 text-left">
              {sortedEvents.map((ev) => {
                const Icon = getStageIcon(ev.stage);
                const isWarning = ev.status === 'warning';
                const isFailed = ev.status === 'failed';

                return (
                  <div key={`${ev.sequence}-${ev.type}`} className="relative group">
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
          )}

          {/* Footer */}
          <div className="text-[10px] text-slate-400 pt-2 border-t border-slate-200/50 dark:border-slate-800/50 flex items-center justify-between">
            <span>Uttarakhand Public Records System • Bounded Agent Orchestration</span>
            <span>Deterministic Grounding</span>
          </div>
        </div>
      )}
    </div>
  );
}
