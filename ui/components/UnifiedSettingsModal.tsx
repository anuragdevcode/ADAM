'use client';

import React, { useState, useEffect } from 'react';
import {
  X,
  Shield,
  ShieldAlert,
  User,
  Building2,
  Lock,
  Check,
  Save,
  SlidersHorizontal,
  Cpu,
  Activity,
  Key,
  Globe,
  RotateCcw,
  RefreshCw,
  Eye,
  EyeOff,
  Ban,
} from 'lucide-react';
import type {
  DepartmentItem,
  AdvancedSettingsBundle,
  AdvancedSettingsPreset,
  AdvancedSettingsResponse,
  PerformanceSettings,
  VoiceSettings,
  SystemSnapshot,
} from '@/lib/types';
import {
  fetchUserPreferences,
  saveUserPreferences,
  fetchAdvancedSettings,
  saveAdvancedSettings,
  resetAdvancedSettings,
  validateGeminiKey,
  registerProvider,
  fetchSystemIntrospection,
} from '@/lib/api';
import { useToast } from './ToastProvider';

export type SettingsTabId = 'general' | 'inference' | 'providers' | 'hardware' | 'telemetry';

interface UnifiedSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  initialTab?: SettingsTabId;
  userId: string;
  onUpdateUserId: (id: string) => void;
  clearanceLevel: string;
  onUpdateClearanceLevel: (lvl: string) => void;
  departmentId: string;
  onUpdateDepartmentId: (dept: string) => void;
  departments: DepartmentItem[];
  sessionId?: string | null;
  onSettingsChange?: (bundle: AdvancedSettingsBundle) => void;
  geminiApiKey: string | null;
  onUpdateGeminiApiKey: (key: string | null) => void;
}

// ── Preset Display Constants ──────────────────────────────────────────────────
const PRESET_DISPLAY: Record<
  AdvancedSettingsPreset,
  { label: string; tagline: string; badge: string; color: string; bg: string; border: string }
> = {
  PRECISE: {
    label: 'Precise',
    tagline: 'Strictest grounding, fastest latency, concise answers',
    badge: 'High Grounding',
    color: 'text-blue-700 dark:text-blue-400',
    bg: 'bg-blue-50 dark:bg-blue-950/30',
    border: 'border-blue-200 dark:border-blue-900/50',
  },
  BALANCED: {
    label: 'Balanced',
    tagline: 'Recommended sovereign default — calibrated for Gov Orders',
    badge: 'Recommended Default',
    color: 'text-purple-700 dark:text-purple-400',
    bg: 'bg-purple-50 dark:bg-purple-950/30',
    border: 'border-purple-200 dark:border-purple-900/50',
  },
  THOROUGH: {
    label: 'Thorough',
    tagline: 'Deep search across historical gazettes, maximum citations',
    badge: 'Broad Audit',
    color: 'text-emerald-700 dark:text-emerald-400',
    bg: 'bg-emerald-50 dark:bg-emerald-950/30',
    border: 'border-emerald-200 dark:border-emerald-900/50',
  },
  CUSTOM: {
    label: 'Custom',
    tagline: 'Manual overrides for research or specialized workflows',
    badge: 'Custom Limits',
    color: 'text-zinc-700 dark:text-zinc-300',
    bg: 'bg-zinc-50 dark:bg-zinc-800/40',
    border: 'border-zinc-200 dark:border-zinc-800',
  },
};

const CLEARANCE_LEVELS = [
  { id: 'PUBLIC', name: 'PUBLIC', desc: 'Standard public government gazettes, notifications & portals' },
  { id: 'INTERNAL', name: 'INTERNAL', desc: 'Internal departmental working documents & draft orders' },
  { id: 'RESTRICTED', name: 'RESTRICTED', desc: 'Protected state financial ceilings, audit deliberations & budgets' },
  { id: 'CONFIDENTIAL', name: 'CONFIDENTIAL', desc: 'Confidential vigilance inquiry & high-sensitivity state records' },
];

const ENV_PROFILES = [
  { value: 'MACBOOK_AIR_8GB', label: 'MacBook Air 8GB', desc: 'Single request concurrency, strict mutual exclusion (Chat blocks OCR/indexing)' },
  { value: 'DEV_SERVER', label: 'Dev Server 8–16GB', desc: '4 concurrent requests, relaxed background indexing' },
  { value: 'GOV_PRODUCTION', label: 'Gov Production GPU', desc: '16 concurrent requests, independent background workers' },
];

const VOICE_LANGS = [
  { value: 'hi', label: 'Hindi (हिन्दी)' },
  { value: 'en', label: 'English' },
  { value: 'hi-en', label: 'Bilingual' },
];

function round2(v: number) {
  return Math.round(v * 100) / 100;
}

export default function UnifiedSettingsModal({
  isOpen,
  onClose,
  initialTab = 'general',
  userId,
  onUpdateUserId,
  clearanceLevel,
  onUpdateClearanceLevel,
  departmentId,
  onUpdateDepartmentId,
  departments,
  sessionId,
  onSettingsChange,
  geminiApiKey,
  onUpdateGeminiApiKey,
}: UnifiedSettingsModalProps) {
  const [activeTab, setActiveTab] = useState<SettingsTabId>(initialTab);
  const { toast } = useToast();

  // General State
  const [tempUserId, setTempUserId] = useState(userId);
  const [languagePref, setLanguagePref] = useState('bilingual');
  const [persistOptIn, setPersistOptIn] = useState(false);
  const [savingGeneral, setSavingGeneral] = useState(false);

  // Advanced / Inference State
  const [loadingAdv, setLoadingAdv] = useState(false);
  const [savingAdv, setSavingAdv] = useState(false);
  const [advData, setAdvData] = useState<AdvancedSettingsResponse | null>(null);
  const [bundle, setBundle] = useState<AdvancedSettingsBundle | null>(null);

  // Gemini & Provider State
  const [geminiKeyInput, setGeminiKeyInput] = useState('');
  const [showGeminiKey, setShowGeminiKey] = useState(false);
  const [validatingKey, setValidatingKey] = useState(false);
  const [providerName, setProviderName] = useState('');
  const [providerUrl, setProviderUrl] = useState('');
  const [providerKey, setProviderKey] = useState('');
  const [registeringProvider, setRegisteringProvider] = useState(false);

  // Telemetry Snapshot State
  const [snapshot, setSnapshot] = useState<SystemSnapshot | null>(null);
  const [loadingTelemetry, setLoadingTelemetry] = useState(false);

  // Sync tab and load on open
  useEffect(() => {
    if (isOpen) {
      setActiveTab(initialTab);
      setTempUserId(userId);
      setGeminiKeyInput(geminiApiKey || '');

      // Load user preferences
      fetchUserPreferences(userId).then((p) => {
        setPersistOptIn(p.opt_in);
        if (p.preferences && typeof p.preferences.language === 'string') {
          setLanguagePref(p.preferences.language);
        }
      });

      // Load advanced inference settings
      setLoadingAdv(true);
      fetchAdvancedSettings(userId)
        .then((data) => {
          setAdvData(data);
          if (data) setBundle(JSON.parse(JSON.stringify(data.current)));
        })
        .finally(() => setLoadingAdv(false));

      // Load telemetry
      setLoadingTelemetry(true);
      fetchSystemIntrospection(sessionId, { userId, clearanceLevel })
        .then((s) => setSnapshot(s))
        .finally(() => setLoadingTelemetry(false));
    }
  }, [isOpen, initialTab, userId, sessionId, clearanceLevel, geminiApiKey]);

  if (!isOpen) return null;

  const isAirGapped = clearanceLevel === 'RESTRICTED' || clearanceLevel === 'CONFIDENTIAL';

  // ── Handlers ────────────────────────────────────────────────────────────────

  const handleSaveGeneral = async () => {
    setSavingGeneral(true);
    onUpdateUserId(tempUserId);
    await saveUserPreferences(tempUserId, persistOptIn, 'UI preferences and linguistic register', {
      language: languagePref,
      last_updated: new Date().toISOString(),
    });
    setSavingGeneral(false);
    toast.success('Officer context and preferences saved');
  };

  const patchBundle = (updater: (b: AdvancedSettingsBundle) => void) => {
    if (!bundle) return;
    const next: AdvancedSettingsBundle = JSON.parse(JSON.stringify(bundle));
    updater(next);

    const named: AdvancedSettingsPreset[] = ['PRECISE', 'BALANCED', 'THOROUGH'];
    let matchedPreset: AdvancedSettingsPreset = 'CUSTOM';
    if (advData?.presets) {
      for (const p of named) {
        if (
          JSON.stringify(advData.presets[p].generation) === JSON.stringify(next.generation) &&
          JSON.stringify(advData.presets[p].retrieval) === JSON.stringify(next.retrieval) &&
          JSON.stringify(advData.presets[p].performance) === JSON.stringify(next.performance)
        ) {
          matchedPreset = p;
          break;
        }
      }
    }
    next.preset = matchedPreset;
    setBundle(next);
  };

  const applyPreset = (preset: AdvancedSettingsPreset) => {
    if (!advData?.presets) return;
    const p = advData.presets[preset];
    if (!p) return;
    setBundle({ ...JSON.parse(JSON.stringify(p)), preset });
    toast.info(`Switched to ${PRESET_DISPLAY[preset]?.label} preset`);
  };

  const handleSaveInference = async () => {
    if (!bundle) return;
    setSavingAdv(true);
    const ok = await saveAdvancedSettings(userId, bundle, true);
    setSavingAdv(false);
    if (ok) {
      onSettingsChange?.(bundle);
      toast.success('Inference and retrieval parameters updated');
    } else {
      toast.error('Failed to save settings');
    }
  };

  const handleResetInference = async () => {
    const def = await resetAdvancedSettings(userId);
    if (def) {
      setBundle(JSON.parse(JSON.stringify(def)));
      onSettingsChange?.(def);
      toast.info('Settings restored to Balanced default');
    }
  };

  const handleVerifyGeminiKey = async () => {
    const cleanKey = geminiKeyInput.trim();
    if (!cleanKey) {
      toast.error('Please enter an API key');
      return;
    }
    setValidatingKey(true);
    try {
      const res = await validateGeminiKey(cleanKey);
      if (res.valid) {
        onUpdateGeminiApiKey(cleanKey);
        toast.success(res.message || 'Gemini API key verified successfully!');
      } else {
        toast.error(res.message || 'Validation failed. Check your key in Google AI Studio.');
      }
    } catch (e) {
      toast.error(`Verification error: ${e}`);
    } finally {
      setValidatingKey(false);
    }
  };

  const handleClearGeminiKey = () => {
    onUpdateGeminiApiKey(null);
    setGeminiKeyInput('');
    toast.info('Gemini API key removed');
  };

  const handleRegisterCustomProvider = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!providerName.trim() || !providerUrl.trim()) {
      toast.error('Provider name and endpoint URL are required');
      return;
    }
    setRegisteringProvider(true);
    try {
      const res = await registerProvider(
        {
          name: providerName.trim(),
          endpoint_url: providerUrl.trim(),
          display_name: providerName.trim(),
        },
        providerKey.trim() || null,
      );
      if (res && Array.isArray(res.models)) {
        toast.success(`Provider registered: ${res.models.length} models discovered`);
        setProviderName('');
        setProviderUrl('');
        setProviderKey('');
      } else {
        toast.error('Failed to register provider. Check endpoint and credentials.');
      }
    } catch (err) {
      toast.error(`Error: ${err}`);
    } finally {
      setRegisteringProvider(false);
    }
  };

  const refreshTelemetry = () => {
    setLoadingTelemetry(true);
    fetchSystemIntrospection(sessionId, { userId, clearanceLevel })
      .then((s) => {
        setSnapshot(s);
        toast.info('Authoritative telemetry refreshed');
      })
      .finally(() => setLoadingTelemetry(false));
  };

  const g = bundle?.generation;
  const r = bundle?.retrieval;
  const p = bundle?.performance;

  // ── Tab items arranged hierarchically ─────────────────────────────────────────
  const TABS: { id: SettingsTabId; label: string; desc: string; icon: React.ComponentType<{ className?: string }> }[] = [
    { id: 'general', label: 'Officer & Access', desc: 'Clearance & context', icon: Shield },
    { id: 'inference', label: 'Inference & RAG', desc: 'Thinking mode & bounds', icon: SlidersHorizontal },
    { id: 'providers', label: 'Keys & Endpoints', desc: 'Gemini BYOK & Ollama', icon: Key },
    { id: 'hardware', label: 'Hardware & Cache', desc: 'Profiles & voice', icon: Cpu },
    { id: 'telemetry', label: 'System Diagnostics', desc: 'Self-model & audits', icon: Activity },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-slate-950/50 dark:bg-black/70 backdrop-blur-xs animate-in fade-in duration-150">
      <div className="relative w-full max-w-4xl max-h-[92vh] bg-white dark:bg-[#12161f] rounded-3xl shadow-2xl border border-slate-200/90 dark:border-zinc-800 flex flex-col overflow-hidden">
        
        {/* Top Header Bar */}
        <div className="px-6 py-4 border-b border-slate-200/80 dark:border-zinc-800 flex items-center justify-between bg-slate-50/60 dark:bg-[#151a26]/70 shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-purple-600 text-white flex items-center justify-center shadow-xs">
              <Shield className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-sm font-bold text-slate-900 dark:text-zinc-100">
                  Settings &amp; Sovereign Governance Hub
                </h2>
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-purple-100 dark:bg-purple-950/60 text-purple-700 dark:text-purple-300 font-semibold uppercase">
                  {clearanceLevel}
                </span>
                {isAirGapped && (
                  <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-red-100 dark:bg-red-950/60 text-red-700 dark:text-red-400 font-semibold uppercase">
                    <ShieldAlert className="w-3 h-3" /> Air-Gapped Active
                  </span>
                )}
              </div>
              <p className="text-[11px] text-slate-500 dark:text-zinc-400">
                Authoritative platform configuration, reasoning parameters, remote providers, and execution telemetry
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-xl text-slate-400 hover:text-slate-700 dark:hover:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition-colors"
              title="Close (Esc)"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Modal Layout: Sidebar Navigation + Bento Content */}
        <div className="flex-1 flex overflow-hidden">
          {/* Left Vertical Tab Rail */}
          <nav className="w-56 border-r border-slate-200/80 dark:border-zinc-800 p-3 flex flex-col gap-1 shrink-0 bg-slate-50/40 dark:bg-[#10141c] select-none">
            {TABS.map((t) => {
              const Icon = t.icon;
              const isActive = activeTab === t.id;
              return (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setActiveTab(t.id)}
                  className={`w-full text-left px-3 py-2.5 rounded-xl flex items-center gap-2.5 transition-all text-xs ${
                    isActive
                      ? 'bg-purple-50 dark:bg-purple-950/50 text-purple-700 dark:text-purple-300 font-semibold border border-purple-200 dark:border-purple-900/60 shadow-xs'
                      : 'text-slate-600 dark:text-zinc-400 hover:text-slate-900 dark:hover:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800/60'
                  }`}
                >
                  <Icon className={`w-4 h-4 shrink-0 ${isActive ? 'text-purple-600 dark:text-purple-400' : 'text-slate-400 dark:text-zinc-500'}`} />
                  <div className="min-w-0">
                    <p className="truncate leading-tight">{t.label}</p>
                    <p className="text-[10px] text-slate-400 dark:text-zinc-500 font-normal truncate mt-0.5">{t.desc}</p>
                  </div>
                </button>
              );
            })}

            <div className="mt-auto pt-3 border-t border-slate-200/60 dark:border-zinc-800 text-[10px] text-slate-400 dark:text-zinc-500 px-3">
              <p className="font-semibold text-slate-700 dark:text-zinc-300">ADAM Sovereign Core</p>
              <p className="text-[9px] mt-0.5">Gov of Uttarakhand • Phase 05</p>
            </div>
          </nav>

          {/* Right Main Bento Content Area */}
          <div className="flex-1 overflow-y-auto p-6 bg-white dark:bg-[#12161f]">
            
            {/* ── TAB 1: GENERAL & ACCESS ── */}
            {activeTab === 'general' && (
              <div className="space-y-5">
                <div>
                  <h3 className="text-sm font-bold text-slate-900 dark:text-zinc-100">Officer Context &amp; Clearance Scope</h3>
                  <p className="text-xs text-slate-500 dark:text-zinc-400 mt-0.5">Frequently adjusted settings for session authorization and departmental boundary control.</p>
                </div>

                {/* Bento Grid: User ID + Department */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                  <div className="p-3.5 rounded-2xl bg-slate-50/70 dark:bg-zinc-900/60 border border-slate-200/80 dark:border-zinc-800 space-y-1.5">
                    <label className="text-xs font-semibold text-slate-700 dark:text-zinc-300 flex items-center gap-1.5">
                      <User className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400" />
                      <span>Officer User Identifier (X-User-Id)</span>
                    </label>
                    <input
                      type="text"
                      value={tempUserId}
                      onChange={(e) => setTempUserId(e.target.value)}
                      placeholder="officer_dev_001"
                      className="w-full px-3 py-1.5 rounded-xl border border-slate-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-xs text-slate-900 dark:text-zinc-100 font-mono outline-none focus:border-purple-500"
                    />
                    <p className="text-[10px] text-slate-400 dark:text-zinc-500">Binds audit logs and private conversation threads.</p>
                  </div>

                  <div className="p-3.5 rounded-2xl bg-slate-50/70 dark:bg-zinc-900/60 border border-slate-200/80 dark:border-zinc-800 space-y-1.5">
                    <label className="text-xs font-semibold text-slate-700 dark:text-zinc-300 flex items-center gap-1.5">
                      <Building2 className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400" />
                      <span>Department Assignment (X-Department-Id)</span>
                    </label>
                    <select
                      value={departmentId}
                      onChange={(e) => onUpdateDepartmentId(e.target.value)}
                      className="w-full px-3 py-1.5 rounded-xl border border-slate-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-xs text-slate-900 dark:text-zinc-100 outline-none focus:border-purple-500"
                    >
                      <option value="ALL">All State Departments (General Scope)</option>
                      {departments.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.label}
                        </option>
                      ))}
                    </select>
                    <p className="text-[10px] text-slate-400 dark:text-zinc-500">Scopes retrieval filtering and statutory jurisdiction.</p>
                  </div>
                </div>

                {/* Clearance Level Bento Cards */}
                <div className="space-y-2">
                  <label className="text-xs font-bold text-slate-800 dark:text-zinc-200 flex items-center gap-1.5">
                    <Lock className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400" />
                    <span>Security Clearance Ceiling (X-Clearance-Level)</span>
                  </label>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                    {CLEARANCE_LEVELS.map((lvl) => {
                      const isSelected = clearanceLevel === lvl.id;
                      return (
                        <div
                          key={lvl.id}
                          onClick={() => onUpdateClearanceLevel(lvl.id)}
                          className={`p-3 rounded-2xl border cursor-pointer transition-all ${
                            isSelected
                              ? 'border-purple-500 dark:border-purple-500 bg-purple-50/60 dark:bg-purple-950/40 shadow-xs ring-1 ring-purple-300 dark:ring-purple-900/60'
                              : 'border-slate-200/80 dark:border-zinc-800 hover:border-slate-300 dark:hover:border-zinc-700 bg-white dark:bg-zinc-900/60'
                          }`}
                        >
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-xs font-bold text-slate-900 dark:text-zinc-100">{lvl.name}</span>
                            <div className="flex items-center gap-1.5">
                              {lvl.id !== 'PUBLIC' && (
                                <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-amber-100 dark:bg-amber-950/80 text-amber-800 dark:text-amber-300 border border-amber-200 dark:border-amber-800">
                                  AIR-GAPPED
                                </span>
                              )}
                              {isSelected && <Check className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400" />}
                            </div>
                          </div>
                          <p className="text-[10px] text-slate-500 dark:text-zinc-400 leading-relaxed">{lvl.desc}</p>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Linguistic Register & Save */}
                <div className="p-3.5 rounded-2xl bg-slate-50/70 dark:bg-zinc-900/60 border border-slate-200/80 dark:border-zinc-800 flex flex-col sm:flex-row items-center justify-between gap-3">
                  <div>
                    <span className="text-xs font-semibold text-slate-800 dark:text-zinc-200">Linguistic Register</span>
                    <p className="text-[10px] text-slate-400 dark:text-zinc-500">Preferred output language across Government circulars.</p>
                  </div>
                  <div className="flex items-center gap-1.5">
                    {[
                      { id: 'hi', name: 'Hindi' },
                      { id: 'en', name: 'English' },
                      { id: 'bilingual', name: 'Bilingual' },
                    ].map((l) => (
                      <button
                        key={l.id}
                        type="button"
                        onClick={() => setLanguagePref(l.id)}
                        className={`px-3 py-1 rounded-xl text-xs font-medium border transition-all ${
                          languagePref === l.id
                            ? 'border-purple-400 bg-purple-50 dark:bg-purple-950/60 text-purple-700 dark:text-purple-300 font-semibold'
                            : 'border-slate-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-slate-600 dark:text-zinc-300'
                        }`}
                      >
                        {l.name}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="pt-2 flex justify-end">
                  <button
                    type="button"
                    onClick={handleSaveGeneral}
                    disabled={savingGeneral}
                    className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-700 text-white text-xs font-semibold shadow-xs transition-all"
                  >
                    <Save className="w-3.5 h-3.5" />
                    <span>{savingGeneral ? 'Saving…' : 'Save Officer Profile'}</span>
                  </button>
                </div>
              </div>
            )}

            {/* ── TAB 2: INFERENCE & RAG ── */}
            {activeTab === 'inference' && (
              <div className="space-y-5">
                <div>
                  <h3 className="text-sm font-bold text-slate-900 dark:text-zinc-100">Inference &amp; RAG Parameters</h3>
                  <p className="text-xs text-slate-500 dark:text-zinc-400 mt-0.5">Calibrated sovereign parameters governing citations, reasoning scratchpads, and temperature bounds.</p>
                </div>

                {loadingAdv && !bundle ? (
                  <div className="py-12 text-center text-slate-400 text-xs flex items-center justify-center gap-2">
                    <RefreshCw className="w-4 h-4 animate-spin text-purple-600" />
                    <span>Loading inference profiles…</span>
                  </div>
                ) : !bundle ? (
                  <div className="py-12 text-center text-slate-400 text-xs">Failed to load inference settings.</div>
                ) : (
                  <>
                    {/* Preset Bento Grid */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                      {(['PRECISE', 'BALANCED', 'THOROUGH', 'CUSTOM'] as AdvancedSettingsPreset[]).map((preset) => {
                        const pd = PRESET_DISPLAY[preset];
                        const isActive = bundle.preset === preset;
                        return (
                          <div
                            key={preset}
                            onClick={() => (preset !== 'CUSTOM' ? applyPreset(preset) : undefined)}
                            className={`p-3 rounded-2xl border transition-all ${
                              isActive
                                ? `${pd.border} ${pd.bg} ring-1 ring-purple-300 dark:ring-purple-900 shadow-xs`
                                : 'border-slate-200/80 dark:border-zinc-800 bg-white dark:bg-zinc-900/60 hover:border-slate-300'
                            } ${preset !== 'CUSTOM' ? 'cursor-pointer' : 'cursor-default opacity-85'}`}
                          >
                            <div className="flex items-center justify-between mb-1">
                              <span className={`text-xs font-bold ${isActive ? pd.color : 'text-slate-800 dark:text-zinc-200'}`}>
                                {pd.label}
                              </span>
                              {isActive && <Check className="w-3 h-3 text-purple-600 dark:text-purple-400" />}
                            </div>
                            <p className="text-[9px] text-slate-500 dark:text-zinc-400 line-clamp-2 leading-tight">{pd.tagline}</p>
                          </div>
                        );
                      })}
                    </div>

                    {/* Qwen Thinking Mode Bento Card */}
                    <div className="p-3.5 rounded-2xl bg-purple-50/70 dark:bg-purple-950/30 border border-purple-200 dark:border-purple-900/50 space-y-2">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <h4 className="text-xs font-bold text-purple-950 dark:text-purple-200">Thinking Mode (Qwen models)</h4>
                          <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-purple-600 text-white">
                            RECOMMENDED ON
                          </span>
                        </div>
                        <div
                          onClick={() => patchBundle((b) => { b.generation.thinking_enabled = !b.generation.thinking_enabled; })}
                          className={`w-9 h-5 rounded-full transition-colors relative flex items-center p-0.5 cursor-pointer ${
                            g!.thinking_enabled ? 'bg-purple-600' : 'bg-slate-300 dark:bg-zinc-700'
                          }`}
                        >
                          <div className={`w-4 h-4 rounded-full bg-white shadow-xs transition-transform ${g!.thinking_enabled ? 'translate-x-4' : 'translate-x-0'}`} />
                        </div>
                      </div>
                      <p className="text-[10px] text-purple-900 dark:text-purple-300 leading-relaxed">
                        Qwen generates internal chain-of-thought tokens to inspect date precedence, reconcile conflicting Government Orders, and evaluate departmental sanction limits. <strong>Always keep Thinking Mode enabled for Qwen.</strong>
                      </p>
                    </div>

                    {/* Stacking Sliders: RAG Temperature & Answer Length */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                      <div className="p-3.5 rounded-2xl bg-slate-50/70 dark:bg-zinc-900/60 border border-slate-200/80 dark:border-zinc-800 space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-semibold text-slate-800 dark:text-zinc-200">RAG Temperature [0.0–0.2]</span>
                          <span className="text-xs font-mono font-bold text-purple-700 dark:text-purple-400">{g!.temperature_rag.toFixed(2)}</span>
                        </div>
                        <input
                          type="range"
                          min={0.0}
                          max={0.2}
                          step={0.01}
                          value={g!.temperature_rag}
                          onChange={(e) => patchBundle((b) => { b.generation.temperature_rag = round2(parseFloat(e.target.value)); })}
                          className="w-full h-1.5 accent-purple-600 bg-slate-200 dark:bg-zinc-700 rounded-full"
                        />
                        <p className="text-[9px] text-slate-400 dark:text-zinc-500">Strictly bounded to prevent hallucination in state records.</p>
                      </div>

                      <div className="p-3.5 rounded-2xl bg-slate-50/70 dark:bg-zinc-900/60 border border-slate-200/80 dark:border-zinc-800 space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-semibold text-slate-800 dark:text-zinc-200">Max Completion Tokens</span>
                          <span className="text-xs font-mono font-bold text-purple-700 dark:text-purple-400">{g!.max_tokens_rag}</span>
                        </div>
                        <input
                          type="range"
                          min={256}
                          max={4096}
                          step={128}
                          value={g!.max_tokens_rag}
                          onChange={(e) => patchBundle((b) => { b.generation.max_tokens_rag = parseInt(e.target.value); })}
                          className="w-full h-1.5 accent-purple-600 bg-slate-200 dark:bg-zinc-700 rounded-full"
                        />
                        <p className="text-[9px] text-slate-400 dark:text-zinc-500">Headroom reserved for cited government responses.</p>
                      </div>

                      <div className="p-3.5 rounded-2xl bg-slate-50/70 dark:bg-zinc-900/60 border border-slate-200/80 dark:border-zinc-800 space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-semibold text-slate-800 dark:text-zinc-200">Top-K Candidate Retrieval</span>
                          <span className="text-xs font-mono font-bold text-purple-700 dark:text-purple-400">{r!.top_k}</span>
                        </div>
                        <input
                          type="range"
                          min={3}
                          max={20}
                          step={1}
                          value={r!.top_k}
                          onChange={(e) => patchBundle((b) => { b.retrieval.top_k = parseInt(e.target.value); })}
                          className="w-full h-1.5 accent-purple-600 bg-slate-200 dark:bg-zinc-700 rounded-full"
                        />
                        <p className="text-[9px] text-slate-400 dark:text-zinc-500">Passages fetched before BM25/Vector reranking.</p>
                      </div>

                      <div className="p-3.5 rounded-2xl bg-slate-50/70 dark:bg-zinc-900/60 border border-slate-200/80 dark:border-zinc-800 flex items-center justify-between">
                        <div>
                          <span className="text-xs font-semibold text-slate-800 dark:text-zinc-200">Cross-Encoder Reranker</span>
                          <p className="text-[9px] text-slate-400 dark:text-zinc-500">Re-scores passages by exact statutory query alignment.</p>
                        </div>
                        <div
                          onClick={() => patchBundle((b) => { b.retrieval.enable_rerank = !b.retrieval.enable_rerank; })}
                          className={`w-9 h-5 rounded-full transition-colors relative flex items-center p-0.5 cursor-pointer ${
                            r!.enable_rerank ? 'bg-purple-600' : 'bg-slate-300 dark:bg-zinc-700'
                          }`}
                        >
                          <div className={`w-4 h-4 rounded-full bg-white shadow-xs transition-transform ${r!.enable_rerank ? 'translate-x-4' : 'translate-x-0'}`} />
                        </div>
                      </div>
                    </div>

                    <div className="pt-2 flex items-center justify-between">
                      <button
                        type="button"
                        onClick={handleResetInference}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-200 dark:border-zinc-700 text-xs text-slate-600 dark:text-zinc-300 hover:bg-slate-100 dark:hover:bg-zinc-800 transition-colors"
                      >
                        <RotateCcw className="w-3 h-3" />
                        <span>Reset to Defaults</span>
                      </button>

                      <button
                        type="button"
                        onClick={handleSaveInference}
                        disabled={savingAdv}
                        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-700 text-white text-xs font-semibold shadow-xs transition-all"
                      >
                        <Save className="w-3.5 h-3.5" />
                        <span>{savingAdv ? 'Saving…' : 'Save & Apply Parameters'}</span>
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}

            {/* ── TAB 3: API KEYS & CLOUD PROVIDERS ── */}
            {activeTab === 'providers' && (
              <div className="space-y-5">
                <div>
                  <h3 className="text-sm font-bold text-slate-900 dark:text-zinc-100">API Keys &amp; Remote Endpoints</h3>
                  <p className="text-xs text-slate-500 dark:text-zinc-400 mt-0.5">Manage Google Gemini BYOK keys and register custom OpenAI-compatible / Ollama model endpoints.</p>
                </div>

                {/* Gemini BYOK Key Card */}
                <div className="p-4 rounded-2xl bg-slate-50/70 dark:bg-zinc-900/60 border border-slate-200/80 dark:border-zinc-800 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <div className="w-7 h-7 rounded-lg bg-purple-100 dark:bg-purple-950/60 text-purple-700 dark:text-purple-300 flex items-center justify-center">
                        <Key className="w-4 h-4" />
                      </div>
                      <div>
                        <h4 className="text-xs font-bold text-slate-900 dark:text-zinc-100">Google Gemini API Key (BYOK)</h4>
                        <p className="text-[10px] text-slate-400 dark:text-zinc-500">Unlocks Gemini 2.5 Flash and Gemini 2.5 Pro</p>
                      </div>
                    </div>
                    {geminiApiKey ? (
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-emerald-100 dark:bg-emerald-950/60 text-emerald-800 dark:text-emerald-300 font-semibold">
                        ACTIVE KEY
                      </span>
                    ) : (
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-200 dark:bg-zinc-700 text-slate-600 dark:text-zinc-400 font-semibold">
                        NOT CONFIGURED
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    <div className="relative flex-1">
                      <input
                        type={showGeminiKey ? 'text' : 'password'}
                        value={geminiKeyInput}
                        onChange={(e) => setGeminiKeyInput(e.target.value)}
                        placeholder="AIzaSy..."
                        className="w-full px-3 py-1.5 pr-8 rounded-xl border border-slate-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-xs text-slate-900 dark:text-zinc-100 font-mono outline-none focus:border-purple-500"
                      />
                      <button
                        type="button"
                        onClick={() => setShowGeminiKey(!showGeminiKey)}
                        className="absolute right-2.5 top-2 text-slate-400 hover:text-slate-600 dark:hover:text-zinc-200"
                      >
                        {showGeminiKey ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                      </button>
                    </div>

                    <button
                      type="button"
                      onClick={handleVerifyGeminiKey}
                      disabled={validatingKey}
                      className="px-3.5 py-1.5 rounded-xl bg-purple-600 hover:bg-purple-700 text-white text-xs font-semibold shadow-xs transition-all shrink-0"
                    >
                      {validatingKey ? 'Testing…' : 'Verify & Save'}
                    </button>

                    {geminiApiKey && (
                      <button
                        type="button"
                        onClick={handleClearGeminiKey}
                        className="px-3 py-1.5 rounded-xl border border-red-200 dark:border-red-900 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 text-xs font-semibold transition-colors shrink-0"
                      >
                        Remove
                      </button>
                    )}
                  </div>
                </div>

                {/* Custom Remote Endpoint Registration Form */}
                <form onSubmit={handleRegisterCustomProvider} className="p-4 rounded-2xl bg-slate-50/70 dark:bg-zinc-900/60 border border-slate-200/80 dark:border-zinc-800 space-y-3">
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-lg bg-blue-100 dark:bg-blue-950/60 text-blue-700 dark:text-blue-300 flex items-center justify-center">
                      <Globe className="w-4 h-4" />
                    </div>
                    <div>
                      <h4 className="text-xs font-bold text-slate-900 dark:text-zinc-100">Register Custom Endpoint (Ollama / vLLM / OpenAI API)</h4>
                      <p className="text-[10px] text-slate-400 dark:text-zinc-500">Attach local or remote OpenAI-compatible serving endpoints</p>
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                    <div>
                      <label className="text-[10px] uppercase font-bold text-slate-400 dark:text-zinc-500 block mb-1">Provider ID / Name</label>
                      <input
                        type="text"
                        value={providerName}
                        onChange={(e) => setProviderName(e.target.value)}
                        placeholder="e.g. ollama_local"
                        className="w-full px-3 py-1.5 rounded-xl border border-slate-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-xs text-slate-900 dark:text-zinc-100 outline-none focus:border-purple-500"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] uppercase font-bold text-slate-400 dark:text-zinc-500 block mb-1">Endpoint Base URL</label>
                      <input
                        type="url"
                        value={providerUrl}
                        onChange={(e) => setProviderUrl(e.target.value)}
                        placeholder="http://localhost:11434/v1"
                        className="w-full px-3 py-1.5 rounded-xl border border-slate-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-xs text-slate-900 dark:text-zinc-100 outline-none focus:border-purple-500"
                      />
                    </div>
                    <div className="sm:col-span-2">
                      <label className="text-[10px] uppercase font-bold text-slate-400 dark:text-zinc-500 block mb-1">Bearer API Key (Optional)</label>
                      <input
                        type="password"
                        value={providerKey}
                        onChange={(e) => setProviderKey(e.target.value)}
                        placeholder="Bearer token or leave blank for local"
                        className="w-full px-3 py-1.5 rounded-xl border border-slate-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-xs text-slate-900 dark:text-zinc-100 outline-none focus:border-purple-500"
                      />
                    </div>
                  </div>

                  <div className="flex justify-end pt-1">
                    <button
                      type="submit"
                      disabled={registeringProvider}
                      className="px-4 py-1.5 rounded-xl bg-slate-900 dark:bg-zinc-100 text-white dark:text-zinc-900 text-xs font-semibold shadow-xs hover:bg-black transition-colors"
                    >
                      {registeringProvider ? 'Registering…' : '+ Register Endpoint'}
                    </button>
                  </div>
                </form>
              </div>
            )}

            {/* ── TAB 4: HARDWARE & CACHE ── */}
            {activeTab === 'hardware' && (
              <div className="space-y-5">
                <div>
                  <h3 className="text-sm font-bold text-slate-900 dark:text-zinc-100">Hardware &amp; Concurrency Architecture</h3>
                  <p className="text-xs text-slate-500 dark:text-zinc-400 mt-0.5">Controls concurrency limits, LRU cache memory, and voice settings.</p>
                </div>

                {bundle && (
                  <>
                    {/* Hardware Profile Bento Cards */}
                    <div className="space-y-2">
                      <label className="text-xs font-bold text-slate-800 dark:text-zinc-200">Hardware Environment Profile</label>
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                        {ENV_PROFILES.map((ep) => {
                          const isActive = p!.environment_profile === ep.value;
                          return (
                            <div
                              key={ep.value}
                              onClick={() => patchBundle((b) => { b.performance.environment_profile = ep.value as PerformanceSettings['environment_profile']; })}
                              className={`p-3 rounded-2xl border cursor-pointer transition-all ${
                                isActive
                                  ? 'border-purple-500 bg-purple-50/60 dark:bg-purple-950/40 ring-1 ring-purple-300 dark:ring-purple-900 shadow-xs'
                                  : 'border-slate-200/80 dark:border-zinc-800 bg-white dark:bg-zinc-900/60 hover:border-slate-300'
                              }`}
                            >
                              <div className="flex items-center justify-between mb-1">
                                <span className="text-xs font-bold text-slate-900 dark:text-zinc-100">{ep.label}</span>
                                {isActive && <Check className="w-3 h-3 text-purple-600 dark:text-purple-400" />}
                              </div>
                              <p className="text-[9px] text-slate-500 dark:text-zinc-400 leading-tight">{ep.desc}</p>
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    {/* Cache Settings */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
                      <div className="p-3.5 rounded-2xl bg-slate-50/70 dark:bg-zinc-900/60 border border-slate-200/80 dark:border-zinc-800 space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-semibold text-slate-800 dark:text-zinc-200">Cache TTL (Seconds)</span>
                          <span className="text-xs font-mono font-bold text-purple-700 dark:text-purple-400">{p!.cache_ttl_seconds}s</span>
                        </div>
                        <input
                          type="range"
                          min={60}
                          max={86400}
                          step={60}
                          value={p!.cache_ttl_seconds}
                          onChange={(e) => patchBundle((b) => { b.performance.cache_ttl_seconds = parseInt(e.target.value); })}
                          className="w-full h-1.5 accent-purple-600 bg-slate-200 dark:bg-zinc-700 rounded-full"
                        />
                        <p className="text-[9px] text-slate-400 dark:text-zinc-500">Duration identical RAG queries remain in memory.</p>
                      </div>

                      <div className="p-3.5 rounded-2xl bg-slate-50/70 dark:bg-zinc-900/60 border border-slate-200/80 dark:border-zinc-800 space-y-2">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-semibold text-slate-800 dark:text-zinc-200">Max Cache Entries</span>
                          <span className="text-xs font-mono font-bold text-purple-700 dark:text-purple-400">{p!.cache_max_entries}</span>
                        </div>
                        <input
                          type="range"
                          min={50}
                          max={2000}
                          step={50}
                          value={p!.cache_max_entries}
                          onChange={(e) => patchBundle((b) => { b.performance.cache_max_entries = parseInt(e.target.value); })}
                          className="w-full h-1.5 accent-purple-600 bg-slate-200 dark:bg-zinc-700 rounded-full"
                        />
                        <p className="text-[9px] text-slate-400 dark:text-zinc-500">LRU memory limit before oldest responses are evicted.</p>
                      </div>
                    </div>

                    {/* Voice Defaults */}
                    <div className="p-3.5 rounded-2xl bg-slate-50/70 dark:bg-zinc-900/60 border border-slate-200/80 dark:border-zinc-800 space-y-2.5">
                      <span className="text-xs font-bold text-slate-800 dark:text-zinc-200">Voice Language Defaults (STT / TTS)</span>
                      <div className="grid grid-cols-3 gap-2">
                        {VOICE_LANGS.map((vl) => (
                          <button
                            key={vl.value}
                            type="button"
                            onClick={() => patchBundle((b) => { b.voice.default_voice_language = vl.value as VoiceSettings['default_voice_language']; })}
                            className={`py-1.5 text-xs rounded-xl border text-center transition-all ${
                              bundle.voice.default_voice_language === vl.value
                                ? 'border-purple-400 bg-purple-50 dark:bg-purple-950/60 text-purple-700 dark:text-purple-300 font-semibold'
                                : 'border-slate-200 dark:border-zinc-700 bg-white dark:bg-zinc-800 text-slate-600 dark:text-zinc-300'
                            }`}
                          >
                            {vl.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    <div className="pt-2 flex justify-end">
                      <button
                        type="button"
                        onClick={handleSaveInference}
                        disabled={savingAdv}
                        className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-purple-600 hover:bg-purple-700 text-white text-xs font-semibold shadow-xs transition-all"
                      >
                        <Save className="w-3.5 h-3.5" />
                        <span>{savingAdv ? 'Saving…' : 'Save Hardware Profile'}</span>
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}

            {/* ── TAB 5: SYSTEM DIAGNOSTICS & TELEMETRY ── */}
            {activeTab === 'telemetry' && (
              <div className="space-y-5">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-bold text-slate-900 dark:text-zinc-100">System Telemetry &amp; Self-Model</h3>
                    <p className="text-xs text-slate-500 dark:text-zinc-400 mt-0.5">Authoritative ground-truth state across tools, active models, and execution audits.</p>
                  </div>
                  <button
                    type="button"
                    onClick={refreshTelemetry}
                    disabled={loadingTelemetry}
                    className="p-1.5 rounded-xl text-slate-400 hover:text-slate-700 dark:hover:text-zinc-200 hover:bg-slate-100 dark:hover:bg-zinc-800 transition-colors"
                    title="Refresh telemetry"
                  >
                    <RefreshCw className={`w-4 h-4 ${loadingTelemetry ? 'animate-spin text-purple-600' : ''}`} />
                  </button>
                </div>

                {loadingTelemetry && !snapshot ? (
                  <div className="py-12 text-center text-slate-400 text-xs flex items-center justify-center gap-2">
                    <RefreshCw className="w-4 h-4 animate-spin text-purple-600" />
                    <span>Querying system singletons and memory headroom…</span>
                  </div>
                ) : !snapshot ? (
                  <div className="py-12 text-center text-slate-400 text-xs">No telemetry recorded yet.</div>
                ) : (
                  <>
                    {/* 4 Metric Bento Cards */}
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                      <div className="p-3 rounded-2xl bg-slate-50/70 dark:bg-zinc-900/60 border border-slate-200/80 dark:border-zinc-800">
                        <span className="text-[10px] text-slate-400 dark:text-zinc-500 uppercase font-semibold">Active Model</span>
                        <p className="text-xs font-bold text-slate-900 dark:text-zinc-100 truncate mt-0.5">{snapshot.active_model.name}</p>
                        <p className="text-[9px] text-slate-400 dark:text-zinc-500 mt-0.5">{snapshot.active_model.quantization} • {snapshot.active_model.serving_runtime}</p>
                      </div>

                      <div className="p-3 rounded-2xl bg-slate-50/70 dark:bg-zinc-900/60 border border-slate-200/80 dark:border-zinc-800">
                        <span className="text-[10px] text-slate-400 dark:text-zinc-500 uppercase font-semibold">Tool Guardrails</span>
                        <p className="text-xs font-bold text-emerald-700 dark:text-emerald-400 mt-0.5">{snapshot.tool_capabilities.allowed_tools.length} Read-Only</p>
                        <p className="text-[9px] text-slate-400 dark:text-zinc-500 mt-0.5">{snapshot.tool_capabilities.forbidden_tools.length} Forbidden</p>
                      </div>

                      <div className="p-3 rounded-2xl bg-slate-50/70 dark:bg-zinc-900/60 border border-slate-200/80 dark:border-zinc-800">
                        <span className="text-[10px] text-slate-400 dark:text-zinc-500 uppercase font-semibold">Indexed Records</span>
                        <p className="text-xs font-bold text-slate-900 dark:text-zinc-100 mt-0.5">{snapshot.data_sources.total_documents} Documents</p>
                        <p className="text-[9px] text-slate-400 dark:text-zinc-500 mt-0.5">{snapshot.data_sources.total_chunks} Chunks</p>
                      </div>

                      <div className="p-3 rounded-2xl bg-slate-50/70 dark:bg-zinc-900/60 border border-slate-200/80 dark:border-zinc-800">
                        <span className="text-[10px] text-slate-400 dark:text-zinc-500 uppercase font-semibold">Worker State</span>
                        <p className="text-xs font-bold text-slate-900 dark:text-zinc-100 mt-0.5">
                          {snapshot.worker_concurrency.is_busy ? (
                            <span className="text-amber-600 dark:text-amber-400">BUSY</span>
                          ) : (
                            <span className="text-emerald-600 dark:text-emerald-400">READY</span>
                          )}
                        </p>
                        <p className="text-[9px] text-slate-400 dark:text-zinc-500 mt-0.5">&gt;= 2GB Locked</p>
                      </div>
                    </div>

                    {/* Last Turn Waterfall */}
                    {snapshot.last_execution && (
                      <div className="p-3.5 rounded-2xl bg-slate-50/70 dark:bg-zinc-900/60 border border-slate-200/80 dark:border-zinc-800 space-y-2.5">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-slate-800 dark:text-zinc-200">Last Execution Latency Breakdown</span>
                          <span className="text-[10px] px-2 py-0.5 rounded font-mono font-bold bg-purple-100 dark:bg-purple-950/60 text-purple-700 dark:text-purple-300">
                            {snapshot.last_execution.total_latency_ms} ms total
                          </span>
                        </div>

                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                          {Object.entries(snapshot.last_execution.per_stage_latency_ms).map(([stage, ms]) => (
                            <div key={stage} className="p-2 rounded-xl bg-white dark:bg-zinc-800 border border-slate-200/60 dark:border-zinc-700/60 text-xs">
                              <p className="text-[9px] text-slate-400 dark:text-zinc-500 uppercase truncate">{stage.replace(/_/g, ' ')}</p>
                              <p className="font-mono font-bold text-slate-900 dark:text-zinc-100 mt-0.5">{ms} ms</p>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Authorized vs Forbidden Boundaries */}
                    <div className="p-3.5 rounded-2xl bg-slate-50/70 dark:bg-zinc-900/60 border border-slate-200/80 dark:border-zinc-800 space-y-2">
                      <span className="text-xs font-bold text-red-700 dark:text-red-400 flex items-center gap-1.5">
                        <Ban className="w-3.5 h-3.5" />
                        <span>Hardcoded Forbidden Sandbox Limits</span>
                      </span>
                      <div className="flex flex-wrap gap-1.5">
                        {snapshot.tool_capabilities.forbidden_tools.map((f) => (
                          <span
                            key={f}
                            className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-md bg-red-50 dark:bg-red-950/40 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-900/60 font-mono font-medium"
                          >
                            <Lock className="w-2.5 h-2.5" />
                            {f}
                          </span>
                        ))}
                      </div>
                    </div>
                  </>
                )}
              </div>
            )}

          </div>
        </div>

      </div>
    </div>
  );
}
