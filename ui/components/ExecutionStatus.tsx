'use client';

import React, { useState } from 'react';
import type {
  OperationalStatusEvent,
  StateTransitionTrailItem,
  AgentExecutionPlan,
  ComputationResultRecord,
  SubagentRecord,
} from '@/lib/types';
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
  Calculator,
  Globe,
  Database,
  Bot,
  GitCompare,
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
  plan?: AgentExecutionPlan | null;
  computationResults?: ComputationResultRecord[];
  researchSummary?: string | null;
  subagents?: SubagentRecord[];
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
  PLAN: { label: 'Dynamic Problem Formulation & Planning', icon: Layers },
  EXECUTE_STEP: { label: 'Bounded Multi-Step Action Execution', icon: Activity },
  VERIFY_INTERMEDIATE: { label: 'Intermediate Result Verification', icon: CheckCircle2 },
  SYNTHESIZE: { label: 'Multi-Source Grounded Synthesis', icon: Sparkles },
  COMPLETED: { label: 'Pipeline Completed Successfully', icon: CheckCircle2 },
  ABSTAINED: { label: 'Deterministic Policy Abstention', icon: AlertTriangle },
  FAILED: { label: 'Security / Execution Termination', icon: XCircle },
};

const STAGE_SHORT_NAMES: Record<string, string> = {
  AUTHENTICATE: 'Auth',
  CLASSIFY_REQUEST: 'Routing',
  RETRIEVE: 'Retrieval',
  EVIDENCE_CURRENCY_CHECKS: 'Evidence',
  GENERATE_OR_ABSTAIN: 'Synthesis',
  VALIDATE_CITATIONS: 'Validation',
  AUDIT: 'Audit',
  PLAN: 'Plan',
  EXECUTE_STEP: 'Step',
  VERIFY_INTERMEDIATE: 'Verify',
  SYNTHESIZE: 'Synthesize',
  security: 'Security',
  query: 'Routing',
  retrieval: 'Retrieval',
  evidence: 'Evidence',
  currency: 'Currency',
  model: 'Model Init',
  generation: 'Synthesis',
  grounding: 'Grounding',
  execution: 'Execution',
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
  plan,
  computationResults = [],
  researchSummary,
  subagents = [],
}: ExecutionStatusProps) {
  const isAgentic = !!plan && !plan.is_direct_lookup;
  const hasCalculations = computationResults && computationResults.length > 0;
  const hasSubagents = subagents && subagents.length > 0;
  const hasResearch = !!researchSummary || hasSubagents;
  const [isExpanded, setIsExpanded] = useState(false);
  const [activeTab, setActiveTab] = useState<'plan' | 'trail' | 'telemetry'>('plan');
  const effectiveTab = (activeTab === 'plan' && !isAgentic) ? 'trail' : activeTab;

  const hasEvents = events && events.length > 0;
  const hasTrail = stateHistory && stateHistory.length > 0;

  if (!hasEvents && !hasTrail && !isAgentic && !hasCalculations && !hasResearch) {
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
  } else if (isAgentic && plan) {
    badgeTitle = `Reasoning Plan: ${plan.complexity.replace(/_/g, ' ')} (${plan.steps.length} steps)`;
    badgeColor = 'bg-indigo-50/80 text-indigo-800 border-indigo-200 dark:bg-indigo-950/30 dark:text-indigo-300 dark:border-indigo-800/40';
  } else if (citationCount != null && citationCount > 0) {
    badgeTitle = `Grounded in ${citationCount} official ${citationCount === 1 ? 'source' : 'sources'}`;
  } else if (selectedCount != null && selectedCount > 0) {
    badgeTitle = `Grounded in ${selectedCount} official ${selectedCount === 1 ? 'record' : 'records'}`;
  }

  return (
    <div className="mb-3">
      {/* Collapsed Badge with reasoning trail toggle */}
      <div className="flex flex-wrap items-center gap-2">
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

        {hasCalculations && (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-lg bg-emerald-50/80 text-emerald-800 border border-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-300 dark:border-emerald-800/40">
            <Calculator className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
            <span>{computationResults.length} Verified {computationResults.length === 1 ? 'Calculation' : 'Calculations'}</span>
          </span>
        )}
      </div>

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
                {isAgentic ? 'Agentic Problem Solver' : '7-Stage State Machine'}
              </span>
            </div>

            <div className="flex items-center p-0.5 bg-slate-200/60 dark:bg-slate-800/80 rounded-lg text-[11px]">
              {isAgentic && (
                <button
                  type="button"
                  onClick={() => setActiveTab('plan')}
                  className={`px-2.5 py-0.5 rounded-md font-medium transition-colors ${
                    effectiveTab === 'plan'
                      ? 'bg-white dark:bg-slate-700 text-indigo-700 dark:text-indigo-300 shadow-xs'
                      : 'text-slate-600 dark:text-slate-400 hover:text-slate-900'
                  }`}
                >
                  Reasoning Plan ({plan?.steps.length ?? 0} Steps)
                </button>
              )}
              <button
                type="button"
                onClick={() => setActiveTab('trail')}
                className={`px-2.5 py-0.5 rounded-md font-medium transition-colors ${
                  effectiveTab === 'trail'
                    ? 'bg-white dark:bg-slate-700 text-purple-700 dark:text-purple-300 shadow-xs'
                    : 'text-slate-600 dark:text-slate-400 hover:text-slate-900'
                }`}
              >
                Stage Trail &amp; Latency
              </button>
              {hasEvents && (
                <button
                  type="button"
                  onClick={() => setActiveTab('telemetry')}
                  className={`px-2.5 py-0.5 rounded-md font-medium transition-colors ${
                    effectiveTab === 'telemetry'
                      ? 'bg-white dark:bg-slate-700 text-purple-700 dark:text-purple-300 shadow-xs'
                      : 'text-slate-600 dark:text-slate-400 hover:text-slate-900'
                  }`}
                >
                  Telemetry Events ({sortedEvents.length})
                </button>
              )}
            </div>
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
              <div
                className="text-xs font-semibold truncate font-mono text-slate-800 dark:text-slate-100 mt-0.5"
                title={bottleneckStage ? `${getStateInfo(bottleneckStage.stage).label || bottleneckStage.stage} (${Math.round(bottleneckStage.duration)}ms)` : 'Optimal execution'}
              >
                {bottleneckStage ? (
                  bottleneckStage.duration < 5 ? (
                    '< 5ms (Optimal)'
                  ) : (
                    `${bottleneckStage.duration.toFixed(0)}ms (${STAGE_SHORT_NAMES[bottleneckStage.stage] || bottleneckStage.stage})`
                  )
                ) : (
                  'None'
                )}
              </div>
            </div>
          </div>

          {/* Abstention Rationale Callout Card */}
          {isAbstained && (
            <div className="p-3 bg-amber-50/80 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/50 rounded-xl space-y-1.5 text-left">
              <div className="flex items-center gap-2 text-amber-800 dark:text-amber-300 font-semibold text-xs">
                <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
                <span>Air-Gapped Repository Boundary Protection</span>
              </div>
              <div className="text-amber-900 dark:text-amber-200 text-xs leading-relaxed">
                {effectiveAbstentionReason ||
                  'The request cannot be verified against official Uttarakhand Government Orders, Rules, or Gazette notifications in the authorised repository.'}
              </div>
              <div className="flex items-center gap-3 pt-1 text-[11px] text-amber-700 dark:text-amber-400 font-medium">
                <span className="inline-flex items-center gap-1">
                  <ShieldCheck className="w-3 h-3" /> Non-hallucinatory guarantee
                </span>
                <span>•</span>
                <span>Deterministic Model Controls (Phase 04)</span>
              </div>
            </div>
          )}

          {/* Tab Content: Agentic Plan & Proof */}
          {effectiveTab === 'plan' && plan && (
            <div className="space-y-3 pt-1 text-left">
              {/* Strategy & Goal Card */}
              <div className="p-3 bg-indigo-50/70 dark:bg-indigo-950/40 border border-indigo-200/80 dark:border-indigo-900/60 rounded-xl space-y-1.5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 font-semibold text-indigo-900 dark:text-indigo-200 text-xs">
                    <Sparkles className="w-3.5 h-3.5 text-indigo-600 dark:text-indigo-400" />
                    <span>Autonomous Problem Decomposition</span>
                  </div>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-indigo-100 dark:bg-indigo-900/60 text-indigo-800 dark:text-indigo-300 uppercase tracking-wide">
                    {plan.complexity.replace(/_/g, ' ')}
                  </span>
                </div>
                {(plan.plan_summary || plan.summary) && (
                  <p className="text-xs text-indigo-900/80 dark:text-indigo-300/90 leading-relaxed">
                    {plan.plan_summary || plan.summary}
                  </p>
                )}
                {plan.subproblems && plan.subproblems.length > 0 && (
                  <div className="pt-1 border-t border-indigo-200/50 dark:border-indigo-900/40 space-y-1">
                    <span className="text-[10px] font-semibold text-indigo-700 dark:text-indigo-400 uppercase tracking-wider">
                      Sub-problems ({plan.subproblems.length})
                    </span>
                    <ul className="space-y-0.5 pl-3 list-disc text-[11px] text-indigo-800 dark:text-indigo-300">
                      {plan.subproblems.map((sub, i) => (
                        <li key={i}>{sub}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {/* Verified Mathematical Proofs */}
              {hasCalculations && (
                <div className="p-3 bg-emerald-50/60 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800/60 rounded-xl space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-900 dark:text-emerald-200">
                      <Calculator className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                      <span>Verified Sandbox Proof ({computationResults.length})</span>
                    </div>
                    <span className="text-[10px] px-2 py-0.5 bg-emerald-100 dark:bg-emerald-900/50 text-emerald-800 dark:text-emerald-300 rounded font-mono">
                      Isolated AST Sandbox
                    </span>
                  </div>

                  <div className="space-y-2">
                    {computationResults.map((calc, cIdx) => {
                      const displayCode = calc.expression_or_code || calc.code || '';
                      const displayVal = calc.result !== undefined ? calc.result : (calc.value !== undefined ? calc.value : calc.output);
                      const execTime = calc.execution_time_ms != null ? calc.execution_time_ms.toFixed(1) : '0.0';

                      return (
                        <div key={cIdx} className="bg-slate-900 text-slate-100 rounded-lg p-2.5 font-mono text-[11px] space-y-1 shadow-xs">
                          <div className="flex items-center justify-between text-[10px] text-slate-400 pb-1 border-b border-slate-800">
                            <span className="flex items-center gap-1 text-emerald-400 font-semibold">
                              <CheckCircle2 className="w-3 h-3" /> Proof #{cIdx + 1}
                            </span>
                            <span>{execTime}ms execution</span>
                          </div>
                          <div className="text-slate-300 whitespace-pre-wrap pt-1 select-all font-mono text-[11px]">
                            {displayCode}
                          </div>
                          <div className="pt-1.5 mt-1 border-t border-slate-800 flex items-center justify-between text-xs">
                            <span className="text-slate-400 font-sans text-[10px] uppercase tracking-wider">Deterministic Output</span>
                            <span className="text-emerald-400 font-bold font-mono">
                              {typeof displayVal === 'object' && displayVal !== null ? JSON.stringify(displayVal) : String(displayVal ?? '')}
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Research & Subagent Orchestration Card */}
              {hasResearch && (
                <div className="p-3 bg-sky-50/70 dark:bg-sky-950/40 border border-sky-200 dark:border-sky-800/60 rounded-xl space-y-2.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 text-xs font-semibold text-sky-900 dark:text-sky-200">
                      <Globe className="w-4 h-4 text-sky-600 dark:text-sky-400" />
                      <span>Research &amp; Tool Orchestration</span>
                    </div>
                    <span className="text-[10px] px-2 py-0.5 bg-sky-100 dark:bg-sky-900/50 text-sky-800 dark:text-sky-300 rounded font-medium flex items-center gap-1">
                      <ShieldCheck className="w-3 h-3 text-sky-600" /> Local Verification First
                    </span>
                  </div>

                  {researchSummary && (
                    <div className="text-xs text-sky-950 dark:text-sky-100 bg-white/90 dark:bg-slate-900/60 p-2.5 rounded-lg border border-sky-200/60 dark:border-sky-900/40 font-mono leading-relaxed">
                      {researchSummary}
                    </div>
                  )}

                  {hasSubagents && (
                    <div className="space-y-1.5 pt-1">
                      <div className="text-[10px] font-semibold text-sky-800 dark:text-sky-300 uppercase tracking-wider flex items-center gap-1">
                        <Bot className="w-3.5 h-3.5 text-sky-600" />
                        <span>Specialized Subagents Dispatched ({subagents.length})</span>
                      </div>
                      <div className="grid grid-cols-1 gap-2">
                        {subagents.map((sub, sIdx) => (
                          <div
                            key={sIdx}
                            className="bg-white/95 dark:bg-slate-900/70 border border-sky-100 dark:border-sky-900/40 rounded-lg p-2.5 text-xs space-y-1.5 shadow-xs"
                          >
                            <div className="flex items-center justify-between text-[11px]">
                              <span className="font-semibold text-slate-800 dark:text-slate-100 flex items-center gap-1">
                                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                                {sub.subagent_type}
                              </span>
                              <span className="font-mono text-[10px] text-slate-400">
                                {sub.execution_time_ms.toFixed(1)}ms
                              </span>
                            </div>
                            <p className="text-slate-600 dark:text-slate-300 text-[11px]">
                              {sub.task_goal}
                            </p>
                            {sub.findings && sub.findings.length > 0 && (
                              <div className="bg-slate-50 dark:bg-slate-800/50 p-2 rounded text-[11px] text-slate-700 dark:text-slate-300 space-y-0.5">
                                {sub.findings.map((f, fIdx) => (
                                  <div key={fIdx} className="flex items-start gap-1.5">
                                    <span className="text-sky-600 font-bold">•</span>
                                    <span>{f}</span>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Execution Steps Timeline */}
              <div className="space-y-2 pt-1">
                <div className="text-[11px] font-semibold text-slate-600 dark:text-slate-400 uppercase tracking-wider flex items-center justify-between">
                  <span>Action Execution Steps</span>
                  <span className="text-[10px] text-slate-400 font-normal">{plan.steps.length} Bounded Steps</span>
                </div>

                <div className="space-y-2">
                  {plan.steps.map((step) => {
                    const statusLower = (step.status || '').toLowerCase();
                    const isCompleted = statusLower === 'completed' || statusLower === 'verified';
                    const isFailed = statusLower === 'failed';
                    const isInProgress = statusLower === 'in_progress';
                    const toolLabel = step.tool_name || step.action_type;
                    const resultText = step.result_summary || step.computation_result;

                    return (
                      <div
                        key={step.step_id}
                        className={`p-2.5 rounded-xl border transition-all ${
                          isFailed
                            ? 'bg-red-50/50 dark:bg-red-950/20 border-red-200 dark:border-red-900/50'
                            : isCompleted
                            ? 'bg-white/80 dark:bg-slate-800/60 border-slate-200/80 dark:border-slate-700/60'
                            : isInProgress
                            ? 'bg-indigo-50/50 dark:bg-indigo-950/30 border-indigo-300 dark:border-indigo-800 animate-pulse'
                            : 'bg-slate-50/40 dark:bg-slate-900/30 border-slate-200/50 dark:border-slate-800/40 opacity-70'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex items-start gap-2">
                            <div className="mt-0.5 shrink-0">
                              {isCompleted ? (
                                <CheckCircle2 className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
                              ) : isFailed ? (
                                <XCircle className="w-4 h-4 text-red-500" />
                              ) : isInProgress ? (
                                <Activity className="w-4 h-4 text-indigo-600 dark:text-indigo-400 animate-spin" />
                              ) : (
                                <div className="w-4 h-4 rounded-full border border-slate-300 dark:border-slate-600 flex items-center justify-center text-[9px] text-slate-500 font-mono">
                                  {step.step_id}
                                </div>
                              )}
                            </div>
                            <div>
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <span className="font-semibold text-slate-800 dark:text-slate-100 text-xs">
                                  Step {step.step_id}: {step.title || step.description}
                                </span>
                                {toolLabel && (
                                  toolLabel.includes('database') ? (
                                    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200/60 dark:border-emerald-800/40">
                                      <Database className="w-2.5 h-2.5" /> {toolLabel}
                                    </span>
                                  ) : toolLabel.includes('web') || toolLabel.includes('fetch') ? (
                                    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono bg-sky-50 dark:bg-sky-950/60 text-sky-700 dark:text-sky-300 border border-sky-200/60 dark:border-sky-800/40">
                                      <Globe className="w-2.5 h-2.5" /> {toolLabel}
                                    </span>
                                  ) : toolLabel.includes('compare') ? (
                                    <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono bg-violet-50 dark:bg-violet-950/60 text-violet-700 dark:text-violet-300 border border-violet-200/60 dark:border-violet-800/40">
                                      <GitCompare className="w-2.5 h-2.5" /> {toolLabel}
                                    </span>
                                  ) : (
                                    <span className="px-1.5 py-0.2 rounded text-[10px] font-mono bg-purple-50 dark:bg-purple-950/60 text-purple-700 dark:text-purple-300 border border-purple-200/50 dark:border-purple-800/40">
                                      {toolLabel}
                                    </span>
                                  )
                                )}
                                {(step.requires_verification || step.action_type === 'verify') && (
                                  <span className="px-1.5 py-0.2 rounded text-[10px] font-medium bg-amber-50 dark:bg-amber-950/60 text-amber-700 dark:text-amber-300 border border-amber-200/50">
                                    Verification Active
                                  </span>
                                )}
                              </div>

                              {step.title && step.description && step.title !== step.description && (
                                <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5 leading-normal">
                                  {step.description}
                                </div>
                              )}

                              {resultText && (
                                <div className="mt-1.5 text-[11px] text-slate-600 dark:text-slate-300 bg-slate-100/70 dark:bg-slate-900/50 rounded-lg p-1.5 font-mono leading-relaxed">
                                  {resultText}
                                </div>
                              )}
                            </div>
                          </div>

                          <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wide shrink-0">
                            {step.status}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* Tab Content 1: State-Transition Reasoning Trail */}
          {effectiveTab === 'trail' && (
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
                            {ev.data.is_cached && (
                              <span className="px-1.5 py-0.5 bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 rounded text-[10px] font-mono">
                                cached response
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
