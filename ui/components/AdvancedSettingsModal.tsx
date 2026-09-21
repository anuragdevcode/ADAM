'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  X, SlidersHorizontal, Zap, Target, Cpu, Mic2,
  ChevronRight, RotateCcw, Check, Save, Info,
} from 'lucide-react';
import type {
  AdvancedSettingsBundle,
  AdvancedSettingsPreset,
  AdvancedSettingsResponse,
  PerformanceSettings,
  VoiceSettings,
} from '@/lib/types';
import {
  fetchAdvancedSettings,
  saveAdvancedSettings,
  resetAdvancedSettings,
} from '@/lib/api';

interface AdvancedSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  userId: string;
  /** Called when saved settings are persisted — callers should update chat headers. */
  onSettingsChange?: (bundle: AdvancedSettingsBundle) => void;
}

// ── Preset display config ──────────────────────────────────────────────────────

const PRESET_DISPLAY: Record<AdvancedSettingsPreset, {
  label: string; tagline: string; icon: string; color: string; bg: string; border: string;
}> = {
  PRECISE: {
    label: 'Precise',
    tagline: 'Strictest grounding · fastest · shortest answers',
    icon: '🎯',
    color: 'text-blue-700',
    bg: 'bg-blue-50',
    border: 'border-blue-200',
  },
  BALANCED: {
    label: 'Balanced',
    tagline: 'Default ADAM behaviour · calibrated for governance',
    icon: '⚖️',
    color: 'text-purple-700',
    bg: 'bg-purple-50',
    border: 'border-purple-200',
  },
  THOROUGH: {
    label: 'Thorough',
    tagline: 'Broader search · longer answers · more evidence',
    icon: '🔬',
    color: 'text-emerald-700',
    bg: 'bg-emerald-50',
    border: 'border-emerald-200',
  },
  CUSTOM: {
    label: 'Custom',
    tagline: 'Your own individual values',
    icon: '🛠️',
    color: 'text-gray-700',
    bg: 'bg-gray-50',
    border: 'border-gray-200',
  },
};

const IMPACT_BADGE: Record<string, { label: string; cls: string }> = {
  accuracy: { label: '🎯 Accuracy', cls: 'bg-blue-50 text-blue-700' },
  speed:    { label: '⚡ Speed',    cls: 'bg-amber-50 text-amber-700' },
  memory:   { label: '🖥️ Memory',  cls: 'bg-violet-50 text-violet-700' },
};

const ENV_PROFILES = [
  { value: 'MACBOOK_AIR_8GB', label: 'MacBook Air 8GB', desc: 'Single request, strict mutual exclusion (Chat blocks OCR/indexing)' },
  { value: 'DEV_SERVER',      label: 'Dev Server 8–16GB', desc: '4 concurrent requests, relaxed mutual exclusion' },
  { value: 'GOV_PRODUCTION',  label: 'Gov Production GPU', desc: '16 concurrent, independent workers' },
];

const VOICE_LANGS = [
  { value: 'hi',    label: 'Hindi (हिन्दी)' },
  { value: 'en',    label: 'English' },
  { value: 'hi-en', label: 'Bilingual' },
];

// ── Helpers ────────────────────────────────────────────────────────────────────

type TabId = 'presets' | 'generation' | 'retrieval' | 'performance';

function clamp(v: number, min: number, max: number) { return Math.max(min, Math.min(max, v)); }
function round2(v: number) { return Math.round(v * 100) / 100; }

// ── Slider with label, value, default badge, and impact badge ──────────────────

function SettingSlider({
  label, description, value, defaultValue, min, max, step, impact, disabled,
  onChange,
}: {
  label: string; description: string; value: number; defaultValue: number;
  min: number; max: number; step: number; impact: string; disabled?: boolean;
  onChange: (v: number) => void;
}) {
  const isDefault = Math.abs(value - defaultValue) < step / 2;
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xs font-semibold text-gray-800 truncate">{label}</span>
          <span className={`shrink-0 px-1.5 py-0.5 rounded text-[9px] font-semibold ${IMPACT_BADGE[impact]?.cls ?? ''}`}>
            {IMPACT_BADGE[impact]?.label}
          </span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {!isDefault && (
            <button
              type="button"
              onClick={() => onChange(defaultValue)}
              title="Reset to default"
              className="p-0.5 rounded text-gray-400 hover:text-purple-600 transition-colors"
            >
              <RotateCcw className="w-3 h-3" />
            </button>
          )}
          <span className="text-xs font-mono font-bold text-purple-700 min-w-[3rem] text-right">
            {step < 1 ? value.toFixed(2) : value}
          </span>
        </div>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(step < 1 ? round2(parseFloat(e.target.value)) : parseInt(e.target.value))}
        className="w-full h-1.5 rounded-full appearance-none cursor-pointer accent-purple-600 disabled:opacity-40 disabled:cursor-default"
      />
      <div className="flex justify-between text-[10px] text-gray-400">
        <span>{step < 1 ? min.toFixed(1) : min}</span>
        <span className="text-[10px] text-gray-400 text-center px-2 truncate">{description}</span>
        <span>{step < 1 ? max.toFixed(1) : max}</span>
      </div>
    </div>
  );
}

function ToggleSetting({ label, description, value, impact, onChange }: {
  label: string; description: string; value: boolean; impact: string;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-1">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold text-gray-800">{label}</span>
          <span className={`shrink-0 px-1.5 py-0.5 rounded text-[9px] font-semibold ${IMPACT_BADGE[impact]?.cls ?? ''}`}>
            {IMPACT_BADGE[impact]?.label}
          </span>
        </div>
        <p className="text-[10px] text-gray-500 mt-0.5">{description}</p>
      </div>
      <div
        onClick={() => onChange(!value)}
        className={`w-9 h-5 rounded-full transition-colors relative flex items-center p-0.5 cursor-pointer shrink-0 ${
          value ? 'bg-purple-600' : 'bg-gray-200'
        }`}
      >
        <div className={`w-4 h-4 rounded-full bg-white shadow-xs transition-transform ${value ? 'translate-x-4' : 'translate-x-0'}`} />
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function AdvancedSettingsModal({
  isOpen, onClose, userId, onSettingsChange,
}: AdvancedSettingsModalProps) {
  const [activeTab, setActiveTab] = useState<TabId>('presets');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedOk, setSavedOk] = useState(false);
  const [settingsData, setSettingsData] = useState<AdvancedSettingsResponse | null>(null);
  const [bundle, setBundle] = useState<AdvancedSettingsBundle | null>(null);
  const [optIn, setOptIn] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const data = await fetchAdvancedSettings(userId);
    setSettingsData(data);
    if (data) setBundle(JSON.parse(JSON.stringify(data.current)));
    setLoading(false);
  }, [userId]);

  useEffect(() => {
    if (isOpen) { setActiveTab('presets'); load(); }
  }, [isOpen, load]);

  if (!isOpen) return null;

  const defaults = settingsData?.defaults ?? null;
  const presets  = settingsData?.presets  ?? null;

  /** Patch bundle and auto-switch preset to CUSTOM */
  function patchBundle(updater: (b: AdvancedSettingsBundle) => void) {
    if (!bundle) return;
    const next: AdvancedSettingsBundle = JSON.parse(JSON.stringify(bundle));
    updater(next);
    // If differs from any named preset, mark as CUSTOM
    const named: AdvancedSettingsPreset[] = ['PRECISE', 'BALANCED', 'THOROUGH'];
    let matchedPreset: AdvancedSettingsPreset = 'CUSTOM';
    for (const p of named) {
      if (presets && JSON.stringify(presets[p].generation) === JSON.stringify(next.generation) &&
          JSON.stringify(presets[p].retrieval)   === JSON.stringify(next.retrieval) &&
          JSON.stringify(presets[p].performance) === JSON.stringify(next.performance)) {
        matchedPreset = p;
        break;
      }
    }
    next.preset = matchedPreset;
    setBundle(next);
  }

  function applyPreset(preset: AdvancedSettingsPreset) {
    if (!presets) return;
    const p = presets[preset];
    if (!p) return;
    setBundle({ ...JSON.parse(JSON.stringify(p)), preset });
  }

  async function handleSave() {
    if (!bundle) return;
    setSaving(true);
    const ok = await saveAdvancedSettings(userId, bundle, optIn);
    setSaving(false);
    if (ok) {
      setSavedOk(true);
      onSettingsChange?.(bundle);
      setTimeout(() => { setSavedOk(false); onClose(); }, 700);
    }
  }

  async function handleReset() {
    const def = await resetAdvancedSettings(userId);
    if (def) {
      setBundle(JSON.parse(JSON.stringify(def)));
      onSettingsChange?.(def);
    }
  }

  const g = bundle?.generation;
  const r = bundle?.retrieval;
  const p = bundle?.performance;
  const v = bundle?.voice;
  const dg = defaults?.generation;
  const dr = defaults?.retrieval;
  const dp = defaults?.performance;

  const tabs: { id: TabId; label: string; icon: React.ReactNode }[] = [
    { id: 'presets',     label: 'Presets',     icon: <SlidersHorizontal className="w-3.5 h-3.5" /> },
    { id: 'generation',  label: 'Generation',  icon: <Zap className="w-3.5 h-3.5" /> },
    { id: 'retrieval',   label: 'Retrieval',   icon: <Target className="w-3.5 h-3.5" /> },
    { id: 'performance', label: 'Performance & Voice', icon: <Cpu className="w-3.5 h-3.5" /> },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-xs p-4">
      <div className="bg-white rounded-3xl border border-gray-100 shadow-2xl max-w-2xl w-full overflow-hidden animate-in fade-in zoom-in-95 duration-150 flex flex-col max-h-[90vh]">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 shrink-0">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-purple-50 text-purple-600 flex items-center justify-center">
              <SlidersHorizontal className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-gray-800">Advanced Settings</h2>
              <p className="text-[11px] text-gray-400">Inference · Retrieval · Performance · Voice</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {bundle && (
              <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${PRESET_DISPLAY[bundle.preset]?.bg} ${PRESET_DISPLAY[bundle.preset]?.color} ${PRESET_DISPLAY[bundle.preset]?.border}`}>
                {PRESET_DISPLAY[bundle.preset]?.icon} {PRESET_DISPLAY[bundle.preset]?.label}
              </span>
            )}
            <button onClick={onClose} className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Tab bar */}
        <div className="flex border-b border-gray-100 shrink-0 px-4 pt-2 gap-1">
          {tabs.map(t => (
            <button
              key={t.id}
              onClick={() => setActiveTab(t.id)}
              className={`flex items-center gap-1.5 px-3 py-2 rounded-t-xl text-xs font-semibold transition-all border-b-2 ${
                activeTab === t.id
                  ? 'border-purple-600 text-purple-700 bg-purple-50/60'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {t.icon} {t.label}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {loading ? (
            <div className="flex items-center justify-center h-40 text-gray-400 text-xs">Loading settings…</div>
          ) : !bundle ? (
            <div className="flex items-center justify-center h-40 text-gray-400 text-xs">Could not load settings.</div>
          ) : (

            /* ── Tab: Presets ── */
            activeTab === 'presets' ? (
              <div className="space-y-3">
                <p className="text-[11px] text-gray-500">
                  Choose a named preset to apply all settings at once. Adjusting any individual value on the other tabs automatically switches to <strong>Custom</strong>.
                </p>
                <div className="grid grid-cols-2 gap-3">
                  {(['PRECISE', 'BALANCED', 'THOROUGH', 'CUSTOM'] as AdvancedSettingsPreset[]).map(preset => {
                    const pd = PRESET_DISPLAY[preset];
                    const isActive = bundle.preset === preset;
                    return (
                      <div
                        key={preset}
                        onClick={() => preset !== 'CUSTOM' ? applyPreset(preset) : undefined}
                        className={`p-4 rounded-2xl border cursor-pointer transition-all ${
                          isActive
                            ? `${pd.border} ${pd.bg} shadow-sm ring-1 ring-purple-200`
                            : 'border-gray-200 hover:border-gray-300 bg-white'
                        } ${preset === 'CUSTOM' ? 'cursor-default opacity-80' : ''}`}
                      >
                        <div className="flex items-center gap-2 mb-1.5">
                          <span className="text-lg">{pd.icon}</span>
                          <span className={`text-sm font-bold ${isActive ? pd.color : 'text-gray-700'}`}>{pd.label}</span>
                          {isActive && <Check className="w-3.5 h-3.5 ml-auto text-purple-600" />}
                        </div>
                        <p className="text-[10px] text-gray-500 leading-tight">{pd.tagline}</p>
                        {preset !== 'CUSTOM' && presets && (
                          <div className="mt-2 pt-2 border-t border-gray-200/60 grid grid-cols-2 gap-1 text-[9px] text-gray-500">
                            <span>Top-K: <strong>{presets[preset].retrieval.top_k}</strong></span>
                            <span>Max tokens: <strong>{presets[preset].generation.max_tokens_rag}</strong></span>
                            <span>Temp (RAG): <strong>{presets[preset].generation.temperature_rag}</strong></span>
                            <span>Passages: <strong>{presets[preset].retrieval.max_passages}</strong></span>
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                {/* Governance notice */}
                <div className="flex gap-2 p-3 rounded-2xl bg-amber-50 border border-amber-100">
                  <Info className="w-3.5 h-3.5 text-amber-600 shrink-0 mt-0.5" />
                  <p className="text-[10px] text-amber-800 leading-relaxed">
                    <strong>Phase 04 governance:</strong> RAG temperature is hard-bounded to [0.0, 0.2] regardless of preset. Conversational temperature, memory retention TTLs for classified content, cryptographic secrets, and database paths are protected and not user-adjustable.
                  </p>
                </div>
              </div>

            /* ── Tab: Generation ── */
            ) : activeTab === 'generation' ? (
              <div className="space-y-5">
                <p className="text-[11px] text-gray-500">Controls inference parameters passed to the model harness. Settings apply to every chat query in this session.</p>

                <div className="space-y-4">
                  <div className="p-3 rounded-2xl bg-gray-50 border border-gray-100 space-y-4">
                    <h4 className="text-xs font-semibold text-gray-700">Governed RAG (citation-grounded)</h4>
                    {dg && <SettingSlider
                      label="RAG Temperature" description="Phase 04 bounded [0.0–0.2]"
                      value={g!.temperature_rag} defaultValue={dg.temperature_rag}
                      min={0.0} max={0.2} step={0.01} impact="accuracy"
                      onChange={v => patchBundle(b => { b.generation.temperature_rag = v; })}
                    />}
                    {dg && <SettingSlider
                      label="Max Answer Length (RAG)" description="Completion tokens for cited answers"
                      value={g!.max_tokens_rag} defaultValue={dg.max_tokens_rag}
                      min={256} max={4096} step={128} impact="speed"
                      onChange={v => patchBundle(b => { b.generation.max_tokens_rag = v; })}
                    />}
                    {dg && <SettingSlider
                      label="Passages in Prompt" description="Evidence passages injected into RAG prompt"
                      value={g!.max_rag_prompt_passages} defaultValue={dg.max_rag_prompt_passages}
                      min={2} max={8} step={1} impact="memory"
                      onChange={v => patchBundle(b => { b.generation.max_rag_prompt_passages = v; })}
                    />}
                  </div>

                  <div className="p-3 rounded-2xl bg-gray-50 border border-gray-100 space-y-4">
                    <h4 className="text-xs font-semibold text-gray-700">Conversational / General</h4>
                    {dg && <SettingSlider
                      label="Conversational Creativity" description="Applies to greetings & general turns only"
                      value={g!.temperature_conversational} defaultValue={dg.temperature_conversational}
                      min={0.0} max={0.8} step={0.05} impact="accuracy"
                      onChange={v => patchBundle(b => { b.generation.temperature_conversational = v; })}
                    />}
                    {dg && <SettingSlider
                      label="Max Answer Length (Conversational)" description="Completion tokens for general turns"
                      value={g!.max_tokens_conversational} defaultValue={dg.max_tokens_conversational}
                      min={256} max={4096} step={128} impact="speed"
                      onChange={v => patchBundle(b => { b.generation.max_tokens_conversational = v; })}
                    />}
                  </div>

                  <div className="p-3 rounded-2xl bg-gray-50 border border-gray-100 space-y-4">
                    <h4 className="text-xs font-semibold text-gray-700">Sampling Parameters</h4>
                    {dg && <SettingSlider
                      label="Top-P (Nucleus Sampling)" description="Probability mass threshold"
                      value={g!.top_p} defaultValue={dg.top_p}
                      min={0.1} max={1.0} step={0.05} impact="accuracy"
                      onChange={v => patchBundle(b => { b.generation.top_p = v; })}
                    />}
                    {dg && <SettingSlider
                      label="Top-K Sampling" description="Max token candidates per step"
                      value={g!.top_k_sampling} defaultValue={dg.top_k_sampling}
                      min={10} max={100} step={5} impact="accuracy"
                      onChange={v => patchBundle(b => { b.generation.top_k_sampling = v; })}
                    />}
                    {dg && <SettingSlider
                      label="Context Window (tokens)" description="Tokens fed to model — larger uses more RAM"
                      value={g!.context_size} defaultValue={dg.context_size}
                      min={2048} max={32768} step={1024} impact="memory"
                      onChange={v => patchBundle(b => { b.generation.context_size = v; })}
                    />}
                    {dg && <SettingSlider
                      label="Min-P Threshold (Qwen)" description="Low-quality token filter (Qwen family only)"
                      value={g!.min_p} defaultValue={dg.min_p}
                      min={0.0} max={0.2} step={0.01} impact="accuracy"
                      onChange={v => patchBundle(b => { b.generation.min_p = v; })}
                    />}
                  </div>

                  <div className="p-3 rounded-2xl bg-gray-50 border border-gray-100 space-y-3">
                    <h4 className="text-xs font-semibold text-gray-700">Extended Thinking (Qwen3 reasoning variants only)</h4>
                    <ToggleSetting
                      label="Enable Thinking Mode" description="Internal chain-of-thought scratchpad. Qwen3 only."
                      value={g!.thinking_enabled} impact="speed"
                      onChange={v => patchBundle(b => { b.generation.thinking_enabled = v; })}
                    />
                    {g!.thinking_enabled && dg && (
                      <SettingSlider
                        label="Thinking Budget (tokens)" description="Reserved headroom for reasoning"
                        value={g!.thinking_budget} defaultValue={dg.thinking_budget}
                        min={256} max={4096} step={256} impact="speed"
                        onChange={v => patchBundle(b => { b.generation.thinking_budget = v; })}
                      />
                    )}
                  </div>
                </div>
              </div>

            /* ── Tab: Retrieval ── */
            ) : activeTab === 'retrieval' ? (
              <div className="space-y-5">
                <p className="text-[11px] text-gray-500">Controls the hybrid BM25 + vector retrieval pipeline. Changes take effect on the next query.</p>
                <div className="space-y-4">
                  <div className="p-3 rounded-2xl bg-gray-50 border border-gray-100 space-y-4">
                    <h4 className="text-xs font-semibold text-gray-700">Candidate Fetch</h4>
                    {dr && <SettingSlider
                      label="Retrieval Candidates (Top-K)" description="Passages fetched before reranking"
                      value={r!.top_k} defaultValue={dr.top_k}
                      min={3} max={20} step={1} impact="speed"
                      onChange={v => patchBundle(b => { b.retrieval.top_k = v; })}
                    />}
                    <ToggleSetting
                      label="Cross-Encoder Reranker" description="Reranks passages by exact query alignment. Improves precision at slight speed cost."
                      value={r!.enable_rerank} impact="accuracy"
                      onChange={v => patchBundle(b => { b.retrieval.enable_rerank = v; })}
                    />
                  </div>

                  <div className="p-3 rounded-2xl bg-gray-50 border border-gray-100 space-y-4">
                    <h4 className="text-xs font-semibold text-gray-700">Hybrid Scoring Weights</h4>
                    <p className="text-[10px] text-gray-400">BM25 + vector weights must sum to 1. Adjusting BM25 automatically adjusts vector.</p>
                    {dr && <SettingSlider
                      label="BM25 Keyword Weight" description={`Vector weight = ${round2(1 - r!.bm25_weight)}`}
                      value={r!.bm25_weight} defaultValue={dr.bm25_weight}
                      min={0.1} max={0.9} step={0.05} impact="accuracy"
                      onChange={v => patchBundle(b => { b.retrieval.bm25_weight = v; })}
                    />}
                    {dr && <SettingSlider
                      label="Min Vector Similarity" description="Cosine floor — candidates below are dropped"
                      value={r!.vector_min_similarity} defaultValue={dr.vector_min_similarity}
                      min={0.3} max={0.95} step={0.05} impact="accuracy"
                      onChange={v => patchBundle(b => { b.retrieval.vector_min_similarity = v; })}
                    />}
                  </div>

                  <div className="p-3 rounded-2xl bg-gray-50 border border-gray-100 space-y-4">
                    <h4 className="text-xs font-semibold text-gray-700">Evidence Packet</h4>
                    {dr && <SettingSlider
                      label="Min Relevance Score" description="Hybrid score floor for evidence inclusion"
                      value={r!.min_score_threshold} defaultValue={dr.min_score_threshold}
                      min={0.01} max={0.3} step={0.01} impact="accuracy"
                      onChange={v => patchBundle(b => { b.retrieval.min_score_threshold = v; })}
                    />}
                    {dr && <SettingSlider
                      label="Min Evidence Passages" description="Minimum passages required for a cited answer"
                      value={r!.min_passages} defaultValue={dr.min_passages}
                      min={1} max={6} step={1} impact="accuracy"
                      onChange={v => patchBundle(b => { b.retrieval.min_passages = clamp(v, 1, r!.max_passages); })}
                    />}
                    {dr && <SettingSlider
                      label="Max Evidence Passages" description="Maximum passages in the evidence packet sent to model"
                      value={r!.max_passages} defaultValue={dr.max_passages}
                      min={3} max={12} step={1} impact="memory"
                      onChange={v => patchBundle(b => { b.retrieval.max_passages = clamp(v, r!.min_passages, 12); })}
                    />}
                  </div>

                  {/* Chunking — read-only informational */}
                  <div className="p-3 rounded-2xl bg-gray-50 border border-gray-200/60">
                    <div className="flex items-center gap-1.5 mb-2">
                      <span className="text-xs font-semibold text-gray-600">Chunking Parameters</span>
                      <span className="px-1.5 py-0.5 rounded text-[9px] bg-gray-200 text-gray-600 font-semibold">READ-ONLY</span>
                    </div>
                    <p className="text-[10px] text-gray-500 mb-2">Applied at ingest time. Cannot change without re-ingesting all documents.</p>
                    <div className="grid grid-cols-3 gap-2 text-[10px] text-gray-600">
                      <div className="p-2 rounded-xl bg-white border border-gray-200"><div className="font-mono font-bold text-gray-800">350</div><div className="text-[9px] text-gray-500">Min tokens</div></div>
                      <div className="p-2 rounded-xl bg-white border border-gray-200"><div className="font-mono font-bold text-gray-800">500</div><div className="text-[9px] text-gray-500">Target tokens</div></div>
                      <div className="p-2 rounded-xl bg-white border border-gray-200"><div className="font-mono font-bold text-gray-800">12%</div><div className="text-[9px] text-gray-500">Overlap ratio</div></div>
                    </div>
                  </div>
                </div>
              </div>

            /* ── Tab: Performance & Voice ── */
            ) : (
              <div className="space-y-5">

                {/* Environment profile */}
                <div className="p-3 rounded-2xl bg-gray-50 border border-gray-100 space-y-3">
                  <h4 className="text-xs font-semibold text-gray-700">Hardware Environment Profile</h4>
                  <p className="text-[10px] text-gray-500">Controls concurrency limits and mutual exclusion between chat inference and background OCR/indexing.</p>
                  <div className="space-y-2">
                    {ENV_PROFILES.map(ep => {
                      const isActive = p!.environment_profile === ep.value;
                      return (
                        <div
                          key={ep.value}
                          onClick={() => patchBundle(b => { b.performance.environment_profile = ep.value as PerformanceSettings['environment_profile']; })}
                          className={`flex items-start gap-3 p-3 rounded-2xl border cursor-pointer transition-all ${
                            isActive ? 'border-purple-300 bg-purple-50/60 shadow-xs' : 'border-gray-200 hover:border-gray-300 bg-white'
                          }`}
                        >
                          <div className={`w-4 h-4 rounded-full border mt-0.5 flex items-center justify-center shrink-0 ${isActive ? 'border-purple-600 bg-purple-600 text-white' : 'border-gray-300'}`}>
                            {isActive && <Check className="w-2.5 h-2.5 stroke-[3]" />}
                          </div>
                          <div className="min-w-0 flex-1">
                            <span className="text-xs font-semibold text-gray-800">{ep.label}</span>
                            <p className="text-[10px] text-gray-500 mt-0.5">{ep.desc}</p>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Cache settings */}
                <div className="p-3 rounded-2xl bg-gray-50 border border-gray-100 space-y-4">
                  <h4 className="text-xs font-semibold text-gray-700">Response Cache</h4>
                  {dp && <SettingSlider
                    label="Cache TTL (seconds)" description="How long identical responses stay cached"
                    value={p!.cache_ttl_seconds} defaultValue={dp.cache_ttl_seconds}
                    min={60} max={86400} step={60} impact="speed"
                    onChange={v => patchBundle(b => { b.performance.cache_ttl_seconds = v; })}
                  />}
                  {dp && <SettingSlider
                    label="Cache Max Entries" description="LRU cache capacity before oldest entries evicted"
                    value={p!.cache_max_entries} defaultValue={dp.cache_max_entries}
                    min={50} max={2000} step={50} impact="memory"
                    onChange={v => patchBundle(b => { b.performance.cache_max_entries = v; })}
                  />}
                </div>

                {/* Voice */}
                <div className="p-3 rounded-2xl bg-gray-50 border border-gray-100 space-y-3">
                  <h4 className="text-xs font-semibold text-gray-700 flex items-center gap-1.5">
                    <Mic2 className="w-3.5 h-3.5" /> Voice Defaults
                  </h4>
                  <div>
                    <label className="text-[11px] font-medium text-gray-600 block mb-1.5">Default Voice Language (STT + TTS)</label>
                    <div className="grid grid-cols-3 gap-2">
                      {VOICE_LANGS.map(l => (
                        <button
                          key={l.value}
                          type="button"
                          onClick={() => patchBundle(b => { b.voice.default_voice_language = l.value as VoiceSettings['default_voice_language']; })}
                          className={`py-1.5 text-xs rounded-xl border text-center transition-all ${
                            v!.default_voice_language === l.value
                              ? 'border-purple-400 bg-purple-50 text-purple-700 font-semibold'
                              : 'border-gray-200 bg-white text-gray-600'
                          }`}
                        >
                          {l.label}
                        </button>
                      ))}
                    </div>
                  </div>
                  <ToggleSetting
                    label="Auto-Read Answers Aloud" description="Automatically reads each answer with TTS when complete."
                    value={v!.tts_enabled_default} impact="accuracy"
                    onChange={val => patchBundle(b => { b.voice.tts_enabled_default = val; })}
                  />
                </div>

                {/* Persistence opt-in */}
                <div className="p-3 rounded-2xl bg-gray-50 border border-gray-100">
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="text-xs font-semibold text-gray-800">Persist Settings</span>
                      <p className="text-[10px] text-gray-500">Save encrypted to your user profile (opt-in per governance standard).</p>
                    </div>
                    <div
                      onClick={() => setOptIn(!optIn)}
                      className={`w-9 h-5 rounded-full transition-colors relative flex items-center p-0.5 cursor-pointer ${optIn ? 'bg-purple-600' : 'bg-gray-200'}`}
                    >
                      <div className={`w-4 h-4 rounded-full bg-white shadow-xs transition-transform ${optIn ? 'translate-x-4' : 'translate-x-0'}`} />
                    </div>
                  </div>
                </div>
              </div>
            )
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3.5 border-t border-gray-100 bg-gray-50/70 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-xs font-medium text-gray-500 hover:text-gray-800 transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleReset}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl border border-gray-200 text-xs text-gray-600 hover:bg-gray-100 transition-colors"
            >
              <RotateCcw className="w-3 h-3" />
              Reset to Defaults
            </button>
          </div>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving || !bundle}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-700 disabled:bg-purple-300 text-white text-xs font-semibold shadow-xs transition-all"
          >
            {savedOk ? <Check className="w-3.5 h-3.5" /> : saving ? <ChevronRight className="w-3.5 h-3.5 animate-pulse" /> : <Save className="w-3.5 h-3.5" />}
            <span>{savedOk ? 'Saved!' : saving ? 'Saving…' : 'Save & Apply'}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
