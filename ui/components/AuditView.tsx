'use client';

import { useState, useEffect } from 'react';
import { Bot, Clock, ShieldAlert, ChevronDown, ChevronRight, Zap, RefreshCw } from 'lucide-react';
import type { AuditRecord } from '@/lib/types';
import { fetchExecutionAudits } from '@/lib/api';

export default function AuditView() {
  const [audits, setAudits] = useState<AuditRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    const data = await fetchExecutionAudits(50);
    setAudits(data);
    setLoading(false);
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="flex-1 flex flex-col h-full bg-[#fcfcfc] overflow-hidden">
      {/* Header */}
      <div className="p-6 border-b border-line flex items-center justify-between bg-surface backdrop-blur-xs shrink-0">
        <div>
          <div className="flex items-center gap-2">
            <Bot className="w-5 h-5 text-brand" />
            <h1 className="text-base font-semibold text-ink">
              Agent State Machine Execution Audit
            </h1>
            <span className="px-2 py-0.5 rounded-full bg-brand-soft text-brand text-xs font-medium">
              {audits.length} Executions Logged
            </span>
          </div>
          <p className="text-xs text-ink-faint mt-0.5">
            Phase 04 Bounded Orchestrator: Immutable latency, token consumption, and state transition logs
          </p>
        </div>

        <button
          onClick={load}
          className="p-2 rounded-xl border border-line bg-surface hover:bg-surface-subtle text-xs font-medium text-ink-secondary flex items-center gap-1.5 shadow-xs transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Main List */}
      <div className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="h-64 flex items-center justify-center text-xs text-ink-faint">
            Loading audit records…
          </div>
        ) : audits.length === 0 ? (
          <div className="h-64 flex flex-col items-center justify-center text-center p-6 text-ink-faint">
            <Bot className="w-10 h-10 stroke-[1.5] text-ink-faint mb-2" />
            <p className="text-sm font-medium text-ink-secondary">No agent executions logged yet</p>
            <p className="text-xs text-ink-faint mt-1">
              Ask questions in the Chat Studio to inspect real-time orchestration metrics.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {audits.map((a) => {
              const isExpanded = expandedId === a.id;
              return (
                <div
                  key={a.id}
                  className="bg-surface rounded-2xl border border-line p-4 shadow-xs hover:border-brand-border transition-all"
                >
                  <div
                    onClick={() => setExpandedId(isExpanded ? null : a.id)}
                    className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 cursor-pointer select-none"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-semibold text-xs text-ink truncate">
                          &quot;{a.query_text}&quot;
                        </span>
                        {a.is_high_risk && (
                          <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-warn-soft text-warn flex items-center gap-1">
                            <ShieldAlert className="w-3 h-3" />
                            <span>HIGH RISK</span>
                          </span>
                        )}
                        {a.is_no_answer && (
                          <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-surface-sunken text-ink-secondary">
                            ABSTENTION
                          </span>
                        )}
                      </div>
                      <div className="flex flex-wrap items-center gap-3 text-[11px] text-ink-faint">
                        <span>User: {a.user_id}</span>
                        <span>Model: {a.model_id || 'qwen3-4b-instruct-q4'}</span>
                        {a.created_at && (
                          <span>{new Date(a.created_at).toLocaleTimeString()}</span>
                        )}
                      </div>
                    </div>

                    {/* Metrics Badges */}
                    <div className="flex items-center gap-2.5 text-xs shrink-0">
                      <div className="flex items-center gap-1 bg-surface-subtle border border-line px-2.5 py-1 rounded-xl text-ink-secondary font-mono">
                        <Clock className="w-3 h-3 text-brand" />
                        <span>{a.latency_ms} ms</span>
                      </div>
                      <div className="flex items-center gap-1 bg-surface-subtle border border-line px-2.5 py-1 rounded-xl text-ink-secondary font-mono">
                        <Zap className="w-3 h-3 text-warn" />
                        <span>{a.prompt_tokens + a.completion_tokens} tok</span>
                      </div>
                      {isExpanded ? (
                        <ChevronDown className="w-4 h-4 text-ink-faint" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-ink-faint" />
                      )}
                    </div>
                  </div>

                  {/* Expanded Diagnostics Drawer */}
                  {isExpanded && (
                    <div className="mt-4 pt-3 border-t border-line text-xs space-y-3">
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                        <div className="p-2.5 rounded-xl bg-surface-subtle text-[11px]">
                          <span className="text-ink-faint block">Retrieval Passes</span>
                          <span className="font-semibold text-ink-secondary font-mono">{a.retrieval_pass_count}</span>
                        </div>
                        <div className="p-2.5 rounded-xl bg-surface-subtle text-[11px]">
                          <span className="text-ink-faint block">Answer Passes</span>
                          <span className="font-semibold text-ink-secondary font-mono">{a.answer_pass_count}</span>
                        </div>
                        <div className="p-2.5 rounded-xl bg-surface-subtle text-[11px]">
                          <span className="text-ink-faint block">Prompt Tokens</span>
                          <span className="font-semibold text-ink-secondary font-mono">{a.prompt_tokens}</span>
                        </div>
                        <div className="p-2.5 rounded-xl bg-surface-subtle text-[11px]">
                          <span className="text-ink-faint block">Completion Tokens</span>
                          <span className="font-semibold text-ink-secondary font-mono">{a.completion_tokens}</span>
                        </div>
                      </div>

                      {/* State transitions */}
                      {a.state_transitions && a.state_transitions.length > 0 && (
                        <div>
                          <p className="text-[11px] font-semibold text-ink-muted mb-1">State Transitions:</p>
                          <div className="flex flex-wrap gap-1">
                            {a.state_transitions.map((st, i) => (
                              <span
                                key={i}
                                className="px-2 py-0.5 rounded-md bg-brand-soft text-brand-active text-[10px] font-mono"
                              >
                                {st.from_state} → {st.to_state}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
