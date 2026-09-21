'use client';

import React, { useState, useEffect, useCallback } from 'react';
import type { SystemSnapshot } from '@/lib/types';
import { fetchSystemIntrospection } from '@/lib/api';
import {
  Cpu,
  Shield,
  ShieldAlert,
  Lock,
  CheckCircle2,
  AlertTriangle,
  Database,
  RefreshCw,
  X,
  Gauge,
  Activity,
  Server,
  FileText,
  Ban,
} from 'lucide-react';

interface SystemIntrospectionModalProps {
  isOpen: boolean;
  onClose: () => void;
  sessionId?: string | null;
  userId: string;
  clearanceLevel: string;
}

type TabKey = 'overview' | 'model' | 'tools' | 'sources' | 'execution';

export default function SystemIntrospectionModal({
  isOpen,
  onClose,
  sessionId,
  userId,
  clearanceLevel,
}: SystemIntrospectionModalProps) {
  const [snapshot, setSnapshot] = useState<SystemSnapshot | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<TabKey>('overview');

  const loadData = useCallback(() => {
    setLoading(true);
    fetchSystemIntrospection(sessionId, {
      userId,
      clearanceLevel,
    })
      .then((data) => {
        setSnapshot(data);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [sessionId, userId, clearanceLevel]);

  useEffect(() => {
    if (isOpen) {
      loadData();
    }
  }, [isOpen, loadData]);

  if (!isOpen) return null;

  const isAirGapped = clearanceLevel === 'RESTRICTED' || clearanceLevel === 'CONFIDENTIAL';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-black/50 backdrop-blur-xs animate-in fade-in duration-150">
      <div className="relative w-full max-w-4xl max-h-[90vh] bg-white rounded-2xl shadow-2xl border border-gray-100 flex flex-col overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-100 flex items-center justify-between bg-gradient-to-r from-gray-50 to-white">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-purple-600 text-white flex items-center justify-center shadow-xs">
              <Activity className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-gray-900">
                  System Introspection & Self-Model
                </h2>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-100 text-purple-700 font-semibold uppercase">
                  v{snapshot?.system_info?.version || '1.0.0'}
                </span>
                {isAirGapped && (
                  <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-red-100 text-red-700 font-semibold uppercase">
                    <ShieldAlert className="w-3 h-3" /> Air-Gapped Active
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-500">
                Authoritative ground-truth state across runtime, tools, data catalogs, and execution audits
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={loadData}
              disabled={loading}
              className="p-2 rounded-xl text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
              title="Refresh telemetry"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-purple-600' : ''}`} />
            </button>
            <button
              onClick={onClose}
              className="p-2 rounded-xl text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
              title="Close"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="px-6 pt-2 border-b border-gray-100 flex items-center gap-1 bg-white select-none">
          <button
            onClick={() => setActiveTab('overview')}
            className={`px-3 py-2 text-xs font-semibold rounded-t-lg transition-colors border-b-2 ${
              activeTab === 'overview'
                ? 'text-purple-600 border-purple-600 bg-purple-50/50'
                : 'text-gray-500 border-transparent hover:text-gray-800'
            }`}
          >
            Overview
          </button>
          <button
            onClick={() => setActiveTab('model')}
            className={`px-3 py-2 text-xs font-semibold rounded-t-lg transition-colors border-b-2 ${
              activeTab === 'model'
                ? 'text-purple-600 border-purple-600 bg-purple-50/50'
                : 'text-gray-500 border-transparent hover:text-gray-800'
            }`}
          >
            Active Model & Harness
          </button>
          <button
            onClick={() => setActiveTab('tools')}
            className={`px-3 py-2 text-xs font-semibold rounded-t-lg transition-colors border-b-2 ${
              activeTab === 'tools'
                ? 'text-purple-600 border-purple-600 bg-purple-50/50'
                : 'text-gray-500 border-transparent hover:text-gray-800'
            }`}
          >
            Tools & Guardrails
          </button>
          <button
            onClick={() => setActiveTab('sources')}
            className={`px-3 py-2 text-xs font-semibold rounded-t-lg transition-colors border-b-2 ${
              activeTab === 'sources'
                ? 'text-purple-600 border-purple-600 bg-purple-50/50'
                : 'text-gray-500 border-transparent hover:text-gray-800'
            }`}
          >
            Data Sources
          </button>
          <button
            onClick={() => setActiveTab('execution')}
            className={`px-3 py-2 text-xs font-semibold rounded-t-lg transition-colors border-b-2 ${
              activeTab === 'execution'
                ? 'text-purple-600 border-purple-600 bg-purple-50/50'
                : 'text-gray-500 border-transparent hover:text-gray-800'
            }`}
          >
            Execution Diagnostics
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 p-6 overflow-y-auto bg-[#fafafa]">
          {loading && !snapshot ? (
            <div className="flex flex-col items-center justify-center py-16 gap-3 text-gray-400">
              <RefreshCw className="w-8 h-8 animate-spin text-purple-600" />
              <p className="text-xs">Querying authoritative system singletons and telemetry...</p>
            </div>
          ) : !snapshot ? (
            <div className="text-center py-16 text-gray-500 text-xs">
              Unable to load system snapshot.
            </div>
          ) : (
            <>
              {/* TAB 1: OVERVIEW */}
              {activeTab === 'overview' && (
                <div className="space-y-4">
                  {/* Top Summary Cards */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div className="p-3.5 rounded-xl bg-white border border-gray-200/80 shadow-xs">
                      <div className="flex items-center gap-2 text-gray-400 text-xs mb-1 font-medium">
                        <Cpu className="w-4 h-4 text-purple-600" />
                        <span>Active Model</span>
                      </div>
                      <p className="text-sm font-bold text-gray-900 truncate">
                        {snapshot.active_model.name}
                      </p>
                      <p className="text-[10px] text-gray-500 mt-0.5">
                        {snapshot.active_model.serving_runtime.toUpperCase()} • {snapshot.active_model.quantization}
                      </p>
                    </div>

                    <div className="p-3.5 rounded-xl bg-white border border-gray-200/80 shadow-xs">
                      <div className="flex items-center gap-2 text-gray-400 text-xs mb-1 font-medium">
                        <Shield className="w-4 h-4 text-emerald-600" />
                        <span>Tool Guardrails</span>
                      </div>
                      <p className="text-sm font-bold text-emerald-700">
                        {snapshot.tool_capabilities.allowed_tools.length} Read-Only Tools
                      </p>
                      <p className="text-[10px] text-gray-500 mt-0.5">
                        {snapshot.tool_capabilities.forbidden_tools.length} Forbidden Limits
                      </p>
                    </div>

                    <div className="p-3.5 rounded-xl bg-white border border-gray-200/80 shadow-xs">
                      <div className="flex items-center gap-2 text-gray-400 text-xs mb-1 font-medium">
                        <Database className="w-4 h-4 text-blue-600" />
                        <span>Data Sources</span>
                      </div>
                      <p className="text-sm font-bold text-gray-900">
                        {snapshot.data_sources.total_sources} Sources
                      </p>
                      <p className="text-[10px] text-gray-500 mt-0.5">
                        {snapshot.data_sources.total_documents} Documents Indexed
                      </p>
                    </div>

                    <div className="p-3.5 rounded-xl bg-white border border-gray-200/80 shadow-xs">
                      <div className="flex items-center gap-2 text-gray-400 text-xs mb-1 font-medium">
                        <Activity className="w-4 h-4 text-amber-600" />
                        <span>Worker Coordinator</span>
                      </div>
                      <p className="text-sm font-bold text-gray-900">
                        {snapshot.worker_concurrency.is_busy ? (
                          <span className="text-amber-600 font-semibold">BUSY</span>
                        ) : (
                          <span className="text-emerald-600 font-semibold">IDLE / READY</span>
                        )}
                      </p>
                      <p className="text-[10px] text-gray-500 mt-0.5">
                        &gt;= 2GB macOS Headroom Locked
                      </p>
                    </div>
                  </div>

                  {/* System Identity Banner */}
                  <div className="p-4 rounded-xl bg-white border border-gray-200/80 shadow-xs space-y-2">
                    <h3 className="text-xs font-bold text-gray-900 uppercase tracking-wider">
                      Authoritative System Identity
                    </h3>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                      <div>
                        <span className="text-gray-400">Jurisdiction:</span>
                        <p className="font-medium text-gray-800">
                          {snapshot.system_info.jurisdiction}
                        </p>
                      </div>
                      <div>
                        <span className="text-gray-400">Operational Environment:</span>
                        <p className="font-medium text-gray-800">
                          {snapshot.system_info.environment}
                        </p>
                      </div>
                      <div>
                        <span className="text-gray-400">Active Clearance Scope:</span>
                        <p className="font-medium text-purple-700">
                          {clearanceLevel} Clearance
                        </p>
                      </div>
                      <div>
                        <span className="text-gray-400">Data Sovereignty Status:</span>
                        <p className="font-medium text-gray-800">
                          {isAirGapped ? 'Air-Gapped (Cloud models prohibited)' : 'Local + Cloud Permitted'}
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Quick Last Execution Summary */}
                  {snapshot.last_execution && (
                    <div className="p-4 rounded-xl bg-white border border-gray-200/80 shadow-xs space-y-2">
                      <div className="flex items-center justify-between">
                        <h3 className="text-xs font-bold text-gray-900 uppercase tracking-wider">
                          Last Turn Diagnostics
                        </h3>
                        <span
                          className={`text-[10px] px-2 py-0.5 rounded font-semibold ${
                            snapshot.last_execution.was_refused
                              ? 'bg-amber-100 text-amber-800'
                              : 'bg-emerald-100 text-emerald-800'
                          }`}
                        >
                          {snapshot.last_execution.was_refused ? 'ABSTAINED' : 'COMPLETED'}
                        </span>
                      </div>
                      <p className="text-xs text-gray-600 italic truncate">
                        &quot;{snapshot.last_execution.query_text_redacted}&quot;
                      </p>
                      <div className="flex items-center gap-4 text-xs text-gray-500">
                        <span>Latency: <strong>{snapshot.last_execution.total_latency_ms} ms</strong></span>
                        <span>Tokens: <strong>{snapshot.last_execution.prompt_tokens + snapshot.last_execution.completion_tokens}</strong></span>
                        {snapshot.last_execution.refusal_reason && (
                          <span className="text-amber-700 truncate">
                            Cause: {snapshot.last_execution.refusal_reason}
                          </span>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* TAB 2: MODEL & HARNESS */}
              {activeTab === 'model' && (
                <div className="space-y-4">
                  <div className="p-4 rounded-xl bg-white border border-gray-200/80 shadow-xs space-y-3">
                    <div className="flex items-center justify-between">
                      <h3 className="text-xs font-bold text-gray-900 uppercase tracking-wider flex items-center gap-2">
                        <Cpu className="w-4 h-4 text-purple-600" />
                        Model Specifications
                      </h3>
                      <span className="text-[10px] px-2 py-0.5 rounded bg-gray-100 text-gray-700 font-mono font-bold">
                        {snapshot.active_model.id}
                      </span>
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
                      <div>
                        <span className="text-gray-400">Architecture Family:</span>
                        <p className="font-semibold text-gray-800">{snapshot.active_model.family}</p>
                      </div>
                      <div>
                        <span className="text-gray-400">Serving Runtime:</span>
                        <p className="font-semibold text-gray-800">{snapshot.active_model.serving_runtime}</p>
                      </div>
                      <div>
                        <span className="text-gray-400">Quantization:</span>
                        <p className="font-semibold text-gray-800">{snapshot.active_model.quantization}</p>
                      </div>
                      <div>
                        <span className="text-gray-400">Context Window:</span>
                        <p className="font-semibold text-gray-800">{snapshot.active_model.context_window.toLocaleString()} tokens</p>
                      </div>
                      <div>
                        <span className="text-gray-400">Memory Footprint:</span>
                        <p className="font-semibold text-gray-800">{snapshot.active_model.memory_footprint_mb} MB</p>
                      </div>
                      <div>
                        <span className="text-gray-400">Reasoning Tokens:</span>
                        <p className="font-semibold text-gray-800">
                          {snapshot.active_model.supports_reasoning ? 'Supported (<think>)' : 'Not enabled'}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="p-4 rounded-xl bg-white border border-gray-200/80 shadow-xs space-y-3">
                    <h3 className="text-xs font-bold text-gray-900 uppercase tracking-wider flex items-center gap-2">
                      <Gauge className="w-4 h-4 text-purple-600" />
                      Active Harness Profile & Sampling Bounds
                    </h3>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
                      <div>
                        <span className="text-gray-400">Harness Profile:</span>
                        <p className="font-semibold text-gray-800">{snapshot.active_harness.profile_name}</p>
                      </div>
                      <div>
                        <span className="text-gray-400">Temperature Bounds:</span>
                        <p className="font-semibold text-gray-800">
                          [{snapshot.active_harness.temperature_range[0]} - {snapshot.active_harness.temperature_range[1]}] (Strictly Governed)
                        </p>
                      </div>
                      <div>
                        <span className="text-gray-400">Max Tokens Budget:</span>
                        <p className="font-semibold text-gray-800">{snapshot.active_harness.max_tokens_budget}</p>
                      </div>
                      <div>
                        <span className="text-gray-400">Reasoning Budget:</span>
                        <p className="font-semibold text-gray-800">
                          {snapshot.active_harness.thinking_enabled ? `${snapshot.active_harness.thinking_budget} tokens` : '0 tokens'}
                        </p>
                      </div>
                      <div className="col-span-2">
                        <span className="text-gray-400">Stop Sequences:</span>
                        <p className="font-mono text-[11px] text-gray-700 truncate">
                          {snapshot.active_harness.stop_sequences.join(', ')}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 3: TOOLS & GUARDRAILS */}
              {activeTab === 'tools' && (
                <div className="space-y-4">
                  {/* Allowed Tools */}
                  <div className="p-4 rounded-xl bg-white border border-gray-200/80 shadow-xs space-y-3">
                    <div className="flex items-center gap-2 text-xs font-bold text-emerald-800 uppercase tracking-wider">
                      <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                      Authorized Read-Only Tools ({snapshot.tool_capabilities.allowed_tools.length})
                    </div>
                    <div className="grid grid-cols-1 gap-2.5">
                      {snapshot.tool_capabilities.allowed_tools.map((tool) => (
                        <div
                          key={tool.name}
                          className="p-3 rounded-lg border border-emerald-100 bg-emerald-50/40 text-xs"
                        >
                          <div className="flex items-center justify-between font-mono font-bold text-emerald-900">
                            <span>{tool.name}</span>
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 font-sans font-semibold">
                              READ-ONLY
                            </span>
                          </div>
                          <p className="text-gray-600 mt-1 text-[11px]">{tool.description}</p>
                          <div className="flex items-center gap-1.5 mt-2 flex-wrap">
                            <span className="text-[10px] text-gray-400">Parameters:</span>
                            {tool.parameters.map((p) => (
                              <span
                                key={p}
                                className="text-[10px] px-1.5 py-0.2 rounded bg-white border border-emerald-200 text-emerald-800 font-mono"
                              >
                                {p}
                              </span>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Forbidden Capabilities */}
                  <div className="p-4 rounded-xl bg-white border border-gray-200/80 shadow-xs space-y-3">
                    <div className="flex items-center gap-2 text-xs font-bold text-red-800 uppercase tracking-wider">
                      <Ban className="w-4 h-4 text-red-600" />
                      Explicit Forbidden Sandbox Limits ({snapshot.tool_capabilities.forbidden_tools.length})
                    </div>
                    <p className="text-[11px] text-gray-500">
                      These operations are hardcoded as prohibited. The agent cannot call, construct, or execute any of these capabilities under any circumstance:
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {snapshot.tool_capabilities.forbidden_tools.map((f) => (
                        <span
                          key={f}
                          className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-md bg-red-50 text-red-700 border border-red-200 font-mono font-medium"
                        >
                          <Lock className="w-2.5 h-2.5" />
                          {f}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Governance Invariants */}
                  <div className="p-4 rounded-xl bg-white border border-gray-200/80 shadow-xs space-y-2">
                    <h4 className="text-xs font-bold text-gray-800 uppercase tracking-wider">
                      Core Governance Invariants
                    </h4>
                    <ul className="list-disc list-inside space-y-1 text-xs text-gray-600">
                      {snapshot.tool_capabilities.guardrail_invariants.map((inv, idx) => (
                        <li key={idx}>{inv}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              {/* TAB 4: DATA SOURCES */}
              {activeTab === 'sources' && (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div className="p-4 rounded-xl bg-white border border-gray-200/80 shadow-xs text-center">
                      <p className="text-2xl font-bold text-gray-900">{snapshot.data_sources.total_sources}</p>
                      <p className="text-xs text-gray-500 mt-1">Approved Sources</p>
                    </div>
                    <div className="p-4 rounded-xl bg-white border border-gray-200/80 shadow-xs text-center">
                      <p className="text-2xl font-bold text-gray-900">{snapshot.data_sources.total_documents}</p>
                      <p className="text-xs text-gray-500 mt-1">Total Indexed Documents</p>
                    </div>
                    <div className="p-4 rounded-xl bg-white border border-gray-200/80 shadow-xs text-center">
                      <p className="text-2xl font-bold text-gray-900">{snapshot.data_sources.total_chunks}</p>
                      <p className="text-xs text-gray-500 mt-1">Semantic Chunks</p>
                    </div>
                  </div>

                  <div className="p-4 rounded-xl bg-white border border-gray-200/80 shadow-xs space-y-3">
                    <h3 className="text-xs font-bold text-gray-900 uppercase tracking-wider flex items-center gap-2">
                      <Server className="w-4 h-4 text-purple-600" />
                      Approved System Connectors
                    </h3>
                    <div className="space-y-2 text-xs">
                      {snapshot.data_sources.approved_connectors.map((conn) => (
                        <div
                          key={conn}
                          className="flex items-center justify-between p-2 rounded-lg bg-gray-50 border border-gray-200/60"
                        >
                          <span className="font-medium text-gray-800">{conn}</span>
                          <span className="text-[10px] px-2 py-0.5 rounded bg-purple-100 text-purple-700 font-semibold">
                            ACTIVE
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="p-4 rounded-xl bg-white border border-gray-200/80 shadow-xs space-y-2">
                    <h3 className="text-xs font-bold text-gray-900 uppercase tracking-wider">
                      Represented Departments
                    </h3>
                    <div className="flex flex-wrap gap-1.5">
                      {snapshot.data_sources.registered_departments.length > 0 ? (
                        snapshot.data_sources.registered_departments.map((dept) => (
                          <span
                            key={dept}
                            className="text-[11px] px-2.5 py-1 rounded-lg bg-gray-100 text-gray-700 font-medium"
                          >
                            {dept}
                          </span>
                        ))
                      ) : (
                        <span className="text-xs text-gray-400">
                          Finance & Treasury, Rural Development, Gazette, Audit, GAD
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* TAB 5: EXECUTION DIAGNOSTICS */}
              {activeTab === 'execution' && (
                <div className="space-y-4">
                  {/* Heavy Worker Lock Status */}
                  <div className="p-4 rounded-xl bg-white border border-gray-200/80 shadow-xs space-y-2">
                    <div className="flex items-center justify-between">
                      <h3 className="text-xs font-bold text-gray-900 uppercase tracking-wider flex items-center gap-2">
                        <Activity className="w-4 h-4 text-amber-600" />
                        Heavy Worker Coordinator & Concurrency
                      </h3>
                      <span
                        className={`text-[10px] px-2 py-0.5 rounded font-bold ${
                          snapshot.worker_concurrency.is_busy
                            ? 'bg-amber-100 text-amber-800'
                            : 'bg-emerald-100 text-emerald-800'
                        }`}
                      >
                        {snapshot.worker_concurrency.is_busy ? 'BUSY' : 'IDLE'}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                      <div>
                        <span className="text-gray-400">Active Heavy Task:</span>
                        <p className="font-semibold text-gray-800">
                          {snapshot.worker_concurrency.active_task || 'None'}
                        </p>
                      </div>
                      <div>
                        <span className="text-gray-400">Task Elapsed:</span>
                        <p className="font-semibold text-gray-800">
                          {snapshot.worker_concurrency.elapsed_seconds}s
                        </p>
                      </div>
                      <div>
                        <span className="text-gray-400">Mutual Exclusion:</span>
                        <p className="font-semibold text-gray-800">
                          {snapshot.worker_concurrency.mutual_exclusion_enforced ? 'ENFORCED' : 'OFF'}
                        </p>
                      </div>
                      <div>
                        <span className="text-gray-400">Ingestion Jobs:</span>
                        <p className="font-semibold text-gray-800">
                          {snapshot.worker_concurrency.active_ingestion_jobs} active
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Last Execution Breakdown */}
                  {snapshot.last_execution ? (
                    <div className="p-4 rounded-xl bg-white border border-gray-200/80 shadow-xs space-y-3">
                      <div className="flex items-center justify-between">
                        <h3 className="text-xs font-bold text-gray-900 uppercase tracking-wider flex items-center gap-2">
                          <FileText className="w-4 h-4 text-purple-600" />
                          Last Request Execution Audit
                        </h3>
                        <span
                          className={`text-[10px] px-2 py-0.5 rounded font-semibold ${
                            snapshot.last_execution.was_refused
                              ? 'bg-amber-100 text-amber-800'
                              : 'bg-emerald-100 text-emerald-800'
                          }`}
                        >
                          {snapshot.last_execution.was_refused ? 'ABSTAINED' : 'SUCCESS'}
                        </span>
                      </div>

                      <div className="p-2.5 rounded-lg bg-gray-50 border border-gray-200/60 text-xs">
                        <span className="text-gray-400 text-[10px] uppercase font-bold">Query:</span>
                        <p className="font-medium text-gray-800 mt-0.5">
                          {snapshot.last_execution.query_text_redacted}
                        </p>
                      </div>

                      {snapshot.last_execution.refusal_reason && (
                        <div className="p-3 rounded-lg bg-amber-50 border border-amber-200 text-xs text-amber-900 space-y-1">
                          <div className="flex items-center gap-1.5 font-bold">
                            <AlertTriangle className="w-4 h-4 text-amber-600" />
                            Abstention / Refusal Diagnosis
                          </div>
                          <p>{snapshot.last_execution.refusal_reason}</p>
                        </div>
                      )}

                      {/* Stage-by-Stage Latency Waterfall */}
                      {Object.keys(snapshot.last_execution.per_stage_latency_ms).length > 0 && (
                        <div className="space-y-1.5 pt-1">
                          <h4 className="text-[11px] font-bold text-gray-600 uppercase tracking-wider">
                            Per-Stage Latencies (Total: {snapshot.last_execution.total_latency_ms} ms)
                          </h4>
                          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                            {Object.entries(snapshot.last_execution.per_stage_latency_ms).map(
                              ([stage, dur]) => (
                                <div
                                  key={stage}
                                  className="p-2 rounded-lg bg-gray-50 border border-gray-200/60 text-xs"
                                >
                                  <p className="text-[10px] text-gray-400 uppercase font-semibold truncate">
                                    {stage.replace(/_/g, ' ')}
                                  </p>
                                  <p className="font-bold text-gray-800 mt-0.5">{dur} ms</p>
                                </div>
                              )
                            )}
                          </div>
                        </div>
                      )}

                      <div className="grid grid-cols-3 gap-2 text-xs text-gray-600 pt-2 border-t border-gray-100">
                        <div>
                          <span className="text-gray-400">Tokens:</span>
                          <p className="font-semibold">
                            P: {snapshot.last_execution.prompt_tokens} / C: {snapshot.last_execution.completion_tokens}
                          </p>
                        </div>
                        <div>
                          <span className="text-gray-400">Validation Passed:</span>
                          <p className="font-semibold">
                            {snapshot.last_execution.validation_passed ? 'YES' : 'NO'}
                          </p>
                        </div>
                        <div>
                          <span className="text-gray-400">Intent Classified:</span>
                          <p className="font-semibold truncate">
                            {snapshot.last_execution.detected_intent || 'STANDARD'}
                          </p>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div className="p-8 text-center bg-white rounded-xl border border-gray-200/80 text-gray-400 text-xs">
                      No previous execution recorded in this session.
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-gray-100 flex items-center justify-between bg-white text-xs text-gray-400">
          <span>System Time: {snapshot?.system_info?.current_time_utc ? new Date(snapshot.system_info.current_time_utc).toLocaleTimeString() : 'N/A'}</span>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-xl bg-gray-900 hover:bg-black text-white font-semibold transition-colors shadow-xs"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
