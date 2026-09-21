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
      <div className="p-6 border-b border-gray-100 flex items-center justify-between bg-white/70 backdrop-blur-xs shrink-0">
        <div>
          <div className="flex items-center gap-2">
            <Bot className="w-5 h-5 text-purple-600" />
            <h1 className="text-base font-semibold text-gray-800">
              Agent State Machine Execution Audit
            </h1>
            <span className="px-2 py-0.5 rounded-full bg-purple-50 text-purple-700 text-xs font-medium">
              {audits.length} Executions Logged
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-0.5">
            Phase 04 Bounded Orchestrator: Immutable latency, token consumption, and state transition logs
          </p>
        </div>

        <button
          onClick={load}
          className="p-2 rounded-xl border border-gray-200 bg-white hover:bg-gray-50 text-xs font-medium text-gray-600 flex items-center gap-1.5 shadow-xs transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Main List */}
      <div className="flex-1 overflow-y-auto p-6">
        {loading ? (
          <div className="h-64 flex items-center justify-center text-xs text-gray-400">
            Loading audit records…
          </div>
        ) : audits.length === 0 ? (
          <div className="h-64 flex flex-col items-center justify-center text-center p-6 text-gray-400">
            <Bot className="w-10 h-10 stroke-[1.5] text-gray-300 mb-2" />
            <p className="text-sm font-medium text-gray-600">No agent executions logged yet</p>
            <p className="text-xs text-gray-400 mt-1">
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
                  className="bg-white rounded-2xl border border-gray-100 p-4 shadow-xs hover:border-purple-200 transition-all"
                >
                  <div
                    onClick={() => setExpandedId(isExpanded ? null : a.id)}
                    className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 cursor-pointer select-none"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="font-semibold text-xs text-gray-800 truncate">
                          &quot;{a.query_text}&quot;
                        </span>
                        {a.is_high_risk && (
                          <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-amber-100 text-amber-800 flex items-center gap-1">
                            <ShieldAlert className="w-3 h-3" />
                            <span>HIGH RISK</span>
                          </span>
                        )}
                        {a.is_no_answer && (
                          <span className="px-2 py-0.5 rounded-md text-[10px] font-bold bg-gray-100 text-gray-700">
                            ABSTENTION
                          </span>
                        )}
                      </div>
                      <div className="flex flex-wrap items-center gap-3 text-[11px] text-gray-400">
                        <span>User: {a.user_id}</span>
                        <span>Model: {a.model_id || 'qwen3-4b-instruct-q4'}</span>
                        {a.created_at && (
                          <span>{new Date(a.created_at).toLocaleTimeString()}</span>
                        )}
                      </div>
                    </div>

                    {/* Metrics Badges */}
                    <div className="flex items-center gap-2.5 text-xs shrink-0">
                      <div className="flex items-center gap-1 bg-gray-50 border border-gray-100 px-2.5 py-1 rounded-xl text-gray-600 font-mono">
                        <Clock className="w-3 h-3 text-purple-600" />
                        <span>{a.latency_ms} ms</span>
                      </div>
                      <div className="flex items-center gap-1 bg-gray-50 border border-gray-100 px-2.5 py-1 rounded-xl text-gray-600 font-mono">
                        <Zap className="w-3 h-3 text-amber-500" />
                        <span>{a.prompt_tokens + a.completion_tokens} tok</span>
                      </div>
                      {isExpanded ? (
                        <ChevronDown className="w-4 h-4 text-gray-400" />
                      ) : (
                        <ChevronRight className="w-4 h-4 text-gray-400" />
                      )}
                    </div>
                  </div>

                  {/* Expanded Diagnostics Drawer */}
                  {isExpanded && (
                    <div className="mt-4 pt-3 border-t border-gray-100 text-xs space-y-3">
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                        <div className="p-2.5 rounded-xl bg-gray-50 text-[11px]">
                          <span className="text-gray-400 block">Retrieval Passes</span>
                          <span className="font-semibold text-gray-700 font-mono">{a.retrieval_pass_count}</span>
                        </div>
                        <div className="p-2.5 rounded-xl bg-gray-50 text-[11px]">
                          <span className="text-gray-400 block">Answer Passes</span>
                          <span className="font-semibold text-gray-700 font-mono">{a.answer_pass_count}</span>
                        </div>
                        <div className="p-2.5 rounded-xl bg-gray-50 text-[11px]">
                          <span className="text-gray-400 block">Prompt Tokens</span>
                          <span className="font-semibold text-gray-700 font-mono">{a.prompt_tokens}</span>
                        </div>
                        <div className="p-2.5 rounded-xl bg-gray-50 text-[11px]">
                          <span className="text-gray-400 block">Completion Tokens</span>
                          <span className="font-semibold text-gray-700 font-mono">{a.completion_tokens}</span>
                        </div>
                      </div>

                      {/* State transitions */}
                      {a.state_transitions && a.state_transitions.length > 0 && (
                        <div>
                          <p className="text-[11px] font-semibold text-gray-500 mb-1">State Transitions:</p>
                          <div className="flex flex-wrap gap-1">
                            {a.state_transitions.map((st, i) => (
                              <span
                                key={i}
                                className="px-2 py-0.5 rounded-md bg-purple-50 text-purple-800 text-[10px] font-mono"
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
