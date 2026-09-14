'use client';

import { useState, useEffect, useRef } from 'react';
import IconRail, { type NavTab } from '@/components/IconRail';
import ChatWindow from '@/components/ChatWindow';
import ConversationHistory from '@/components/ConversationHistory';
import DocumentsView from '@/components/DocumentsView';
import PrecedentsView from '@/components/PrecedentsView';
import AuditView from '@/components/AuditView';
import SourcesView from '@/components/SourcesView';
import ReviewView from '@/components/ReviewView';
import SettingsModal from '@/components/SettingsModal';
import ApiKeyModal from '@/components/ApiKeyModal';
import { ChevronDown, Search, Plus, Check, Shield, Cpu, Cloud, Lock, Key } from 'lucide-react';
import type { DepartmentItem, ModelInfo } from '@/lib/types';
import { fetchModels, fetchVocabularies, getStoredGeminiApiKey, setStoredGeminiApiKey, clearStoredGeminiApiKey } from '@/lib/api';

const DEFAULT_OFFICER_ID = 'officer_dev_001';

const VIEW_TITLES: Record<NavTab, { title: string; caption: string }> = {
  home: { title: 'Chat Studio', caption: 'Ask across approved Uttarakhand public records' },
  docs: { title: 'Document Repository', caption: 'Government orders, circulars and notifications' },
  network: { title: 'Precedent Chains', caption: 'Supersession, amendment and continuation links' },
  audit: { title: 'Execution Audits', caption: 'Bounded agent runs and their evidence trail' },
  database: { title: 'Acquisition Sources', caption: 'Approved departmental crawl targets' },
  review: { title: 'Review Queue', caption: 'Pages held for human verification' },
};

export default function HomePage() {
  const [activeNavTab, setActiveNavTab] = useState<NavTab>('home');
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  // Officer Identity & Clearance State
  const [officerUserId, setOfficerUserId] = useState(DEFAULT_OFFICER_ID);
  const [clearanceLevel, setClearanceLevel] = useState('PUBLIC');
  const [departmentId, setDepartmentId] = useState('ALL');

  // Real Backend Data State
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState<ModelInfo | null>(null);
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const [departments, setDepartments] = useState<DepartmentItem[]>([]);
  const [searchFilter, setSearchFilter] = useState('');
  const modelMenuRef = useRef<HTMLDivElement>(null);

  // Gemini API Key & Cloud Models
  const [geminiApiKey, setGeminiApiKey] = useState<string | null>(null);
  const [apiKeyModalOpen, setApiKeyModalOpen] = useState(false);

  // Initial Load from API
  useEffect(() => {
    const key = getStoredGeminiApiKey();
    setGeminiApiKey(key);

    const loadModels = () => {
      const activeKey = getStoredGeminiApiKey();
      void fetchModels(activeKey).then((mList) => {
        setModels(mList);
        const supportedInstalled = mList.filter((m) => m.is_installed && !m.requires_legal_review && m.is_supported !== false);
        const storedModelId = typeof window !== 'undefined' ? localStorage.getItem('adam_selected_model_id') : null;
        setSelectedModel((current) => {
          if (current && supportedInstalled.some((model) => model.id === current.id)) return current;
          if (storedModelId) {
            const foundStored = supportedInstalled.find((m) => m.id === storedModelId);
            if (foundStored) return foundStored;
          }
          if (activeKey) {
            const geminiModel = supportedInstalled.find((m) => m.id === 'gemini-3.6-flash');
            if (geminiModel) return geminiModel;
          }
          return supportedInstalled.find((model) => model.is_primary) || supportedInstalled[0] || mList.find((model) => model.is_primary && !model.requires_legal_review) || null;
        });
      });
    };
    loadModels();
    const modelRefresh = window.setInterval(loadModels, 15_000);

    fetchVocabularies().then((v) => {
      setDepartments(v.departments || []);
    });
    return () => window.clearInterval(modelRefresh);
  }, []);

  // Dismiss the model menu on outside click / Escape.
  useEffect(() => {
    if (!modelDropdownOpen) return;
    const onPointer = (e: MouseEvent) => {
      if (!modelMenuRef.current?.contains(e.target as Node)) setModelDropdownOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setModelDropdownOpen(false);
    };
    document.addEventListener('mousedown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [modelDropdownOpen]);

  const handleNewThread = () => {
    setActiveNavTab('home');
    setActiveSessionId(null);
    setIsHistoryOpen(false);
  };

  const view = VIEW_TITLES[activeNavTab];
  const installedCount = models.filter((m) => m.is_installed).length;

  return (
    <main className="w-screen h-screen min-h-[600px] bg-bg overflow-hidden">
      <div className="w-full h-full bg-surface flex overflow-hidden relative">
        <IconRail
          activeTab={activeNavTab}
          onSelectTab={(tab) => {
            setActiveNavTab(tab);
            setIsHistoryOpen(false);
          }}
          onToggleHistory={() => setIsHistoryOpen((v) => !v)}
          isHistoryOpen={isHistoryOpen}
          onOpenSettings={() => setSettingsOpen(true)}
          userName={officerUserId}
          clearanceLevel={clearanceLevel}
        />

        {isHistoryOpen && (
          <ConversationHistory
            userId={officerUserId}
            activeSessionId={activeSessionId}
            onSelectSession={(id) => {
              setActiveSessionId(id);
              setActiveNavTab('home');
              setIsHistoryOpen(false);
            }}
            onClose={() => setIsHistoryOpen(false)}
            searchFilter={searchFilter}
          />
        )}

        <div className="flex-1 flex flex-col h-full overflow-hidden min-w-0">
          {/* ── Top bar ─────────────────────────────────────────────────── */}
          <header className="h-16 px-4 sm:px-6 border-b border-line flex items-center justify-between gap-4 bg-surface shrink-0 z-10">
            {/* View identity */}
            <div className="min-w-0 flex items-center gap-3">
              <div className="min-w-0">
                <h1 className="text-sm font-semibold text-ink truncate leading-tight">
                  {view.title}
                </h1>
                <p className="text-2xs text-ink-muted truncate leading-tight mt-0.5">
                  {view.caption}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {/* Thread search */}
              <div className="hidden lg:flex items-center gap-2 h-9 px-3 rounded-xl border border-line bg-surface-subtle text-xs text-ink-secondary focus-within:border-brand-border focus-within:bg-surface transition-colors">
                <Search className="w-3.5 h-3.5 text-ink-faint shrink-0" />
                <input
                  type="text"
                  placeholder="Search threads"
                  value={searchFilter}
                  onChange={(e) => {
                    setSearchFilter(e.target.value);
                    if (!isHistoryOpen) setIsHistoryOpen(true);
                  }}
                  className="bg-transparent outline-none w-32 text-xs placeholder-ink-faint"
                  aria-label="Search conversation threads"
                />
              </div>

              {/* Model selector — installed local models and keyed cloud models are selectable */}
              <div className="relative" ref={modelMenuRef}>
                <button
                  type="button"
                  onClick={() => setModelDropdownOpen((open) => !open)}
                  aria-haspopup="listbox"
                  aria-expanded={modelDropdownOpen}
                  className="inline-flex items-center gap-2 h-9 px-3 rounded-xl border border-line bg-surface hover:bg-surface-subtle text-xs font-medium text-ink-secondary transition-colors"
                  title="Select a model"
                >
                  <span
                    className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                      selectedModel?.is_installed ? 'bg-ok' : 'bg-warn'
                    }`}
                    aria-hidden
                  />
                  {selectedModel?.is_cloud ? (
                    <Cloud className="w-3.5 h-3.5 text-ink-faint hidden sm:block" />
                  ) : (
                    <Cpu className="w-3.5 h-3.5 text-ink-faint hidden sm:block" />
                  )}
                  <span className="font-semibold text-ink max-w-[150px] truncate">
                    {selectedModel?.name || 'Select model'}
                  </span>
                  <ChevronDown
                    className={`w-3 h-3 text-ink-faint transition-transform ${
                      modelDropdownOpen ? 'rotate-180' : ''
                    }`}
                  />
                </button>

                {modelDropdownOpen && (
                  <div
                    role="listbox"
                    className="absolute right-0 top-full mt-2 w-[340px] bg-surface rounded-panel border border-line shadow-xl py-1.5 z-30 animate-fade-rise"
                  >
                    <div className="px-3 py-2 flex items-center justify-between">
                      <span className="text-2xs uppercase tracking-wider font-semibold text-ink-faint">
                        Model inventory
                      </span>
                      <span className="text-2xs text-ink-faint tabular">
                        {installedCount}/{models.length} available
                      </span>
                    </div>

                    <div className="max-h-[340px] overflow-y-auto">
                      {models.map((model) => {
                        const isSelected = selectedModel?.id === model.id;
                        const isSelectable = Boolean(
                          model.is_installed && !model.requires_legal_review && model.is_supported !== false,
                        );
                        return (
                          <button
                            key={model.id}
                            type="button"
                            role="option"
                            aria-selected={isSelected}
                            disabled={!isSelectable}
                            onClick={() => {
                              if (!isSelectable) return;
                              setSelectedModel(model);
                              if (typeof window !== 'undefined') {
                                localStorage.setItem('adam_selected_model_id', model.id);
                              }
                              setModelDropdownOpen(false);
                            }}
                            title={
                              isSelectable
                                ? `Use ${model.name}`
                                : model.unavailable_reason || 'Not supported / pending review'
                            }
                            className={`w-full text-left px-3 py-2.5 flex items-start gap-2.5 transition-colors ${
                              isSelectable
                                ? 'hover:bg-brand-soft cursor-pointer'
                                : 'opacity-55 cursor-not-allowed'
                            }`}
                          >
                            <span
                              className={`mt-1.5 w-1.5 h-1.5 rounded-full shrink-0 ${
                                isSelectable ? 'bg-ok' : 'bg-line-strong'
                              }`}
                              aria-hidden
                            />
                            <span className="min-w-0 flex-1">
                              <span className="flex items-center gap-1.5 flex-wrap">
                                <span className="text-xs font-medium text-ink truncate">
                                  {model.name}
                                </span>
                                {model.is_primary && (
                                  <span className="px-1.5 py-px rounded bg-seal-soft text-seal text-[10px] font-semibold uppercase tracking-wide shrink-0">
                                    Primary
                                  </span>
                                )}
                                {model.is_cloud && (
                                  <span className="inline-flex items-center gap-0.5 px-1.5 py-px rounded bg-brand-soft text-brand border border-brand-border text-[10px] font-semibold uppercase tracking-wide shrink-0">
                                    <Cloud className="w-2.5 h-2.5" /> Cloud
                                  </span>
                                )}
                                {model.requires_legal_review ? (
                                  <span className="inline-flex items-center gap-0.5 px-1.5 py-px rounded bg-warn-soft text-warn text-[10px] font-semibold uppercase tracking-wide shrink-0">
                                    <Lock className="w-2.5 h-2.5" /> Frozen · Legal review
                                  </span>
                                ) : !model.is_installed ? (
                                  <span className="text-[10px] uppercase tracking-wide text-ink-faint shrink-0">
                                    {model.is_cloud ? 'Key required' : 'Not installed'}
                                  </span>
                                ) : null}
                              </span>
                              <span className="block text-2xs text-ink-muted mt-0.5 truncate">
                                {isSelectable
                                  ? model.is_cloud
                                    ? 'Google Gemini Cloud · active'
                                    : `${model.quantization} · ${model.context_window} ctx · ready locally`
                                  : model.unavailable_reason}
                              </span>
                            </span>
                            {isSelected && (
                              <Check className="w-3.5 h-3.5 text-brand shrink-0 mt-0.5" />
                            )}
                          </button>
                        );
                      })}
                    </div>

                    <div className="my-1.5 border-t border-line" />

                    {/* Add / configure Gemini API key (unlocks cloud models and hosted voice) */}
                    <button
                      type="button"
                      onClick={() => {
                        setModelDropdownOpen(false);
                        setApiKeyModalOpen(true);
                      }}
                      className="w-full text-left px-3 py-2.5 flex items-center justify-between gap-2 hover:bg-brand-soft transition-colors"
                    >
                      <span className="flex items-center gap-2 min-w-0">
                        <Key className="w-3.5 h-3.5 text-brand shrink-0" />
                        <span className="text-xs font-semibold text-ink truncate">
                          {geminiApiKey ? 'Configure Gemini API key' : 'Add Gemini API key'}
                        </span>
                      </span>
                      {geminiApiKey ? (
                        <span className="px-1.5 py-px rounded bg-ok-soft text-ok text-[10px] font-semibold uppercase tracking-wide shrink-0">
                          Active
                        </span>
                      ) : (
                        <span className="text-2xs text-ink-faint shrink-0">Voice &amp; cloud models</span>
                      )}
                    </button>
                  </div>
                )}
              </div>

              {/* Clearance */}
              <button
                type="button"
                onClick={() => setSettingsOpen(true)}
                className="inline-flex items-center gap-1.5 h-9 px-3 rounded-xl border border-line bg-surface hover:bg-surface-subtle text-xs font-semibold text-ink-secondary transition-colors"
                title="View or change officer clearance"
              >
                <Shield className="w-3.5 h-3.5 text-seal" />
                <span className="hidden sm:inline">{clearanceLevel}</span>
              </button>

              {/* New thread */}
              <button
                type="button"
                onClick={handleNewThread}
                className="inline-flex items-center gap-1.5 h-9 px-3.5 rounded-xl bg-brand hover:bg-brand-hover active:bg-brand-active text-ink-onBrand text-xs font-semibold shadow-sm transition-colors"
              >
                <Plus className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">New Thread</span>
              </button>
            </div>
          </header>

          {/* ── Active view ─────────────────────────────────────────────── */}
          <section className="flex-1 overflow-hidden relative">
            {activeNavTab === 'home' && (
              <ChatWindow
                userId={officerUserId}
                sessionId={activeSessionId}
                onSessionCreated={(id) => setActiveSessionId(id)}
                userName={officerUserId}
                clearanceLevel={clearanceLevel}
                modelId={selectedModel?.id}
                departments={departments}
                onOpenUpload={() => setActiveNavTab('docs')}
              />
            )}

            {activeNavTab === 'docs' && (
              <DocumentsView
                userId={officerUserId}
                clearanceLevel={clearanceLevel}
                departments={departments}
              />
            )}

            {activeNavTab === 'network' && <PrecedentsView />}
            {activeNavTab === 'audit' && <AuditView />}
            {activeNavTab === 'database' && <SourcesView />}
            {activeNavTab === 'review' && <ReviewView userId={officerUserId} />}
          </section>
        </div>
      </div>

      <SettingsModal
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        userId={officerUserId}
        onUpdateUserId={(id) => setOfficerUserId(id)}
        clearanceLevel={clearanceLevel}
        onUpdateClearanceLevel={(lvl) => setClearanceLevel(lvl)}
        departmentId={departmentId}
        onUpdateDepartmentId={(dept) => setDepartmentId(dept)}
        departments={departments}
      />

      {/* Google Gemini API Key & Cloud Model Modal */}
      <ApiKeyModal
        isOpen={apiKeyModalOpen}
        onClose={() => setApiKeyModalOpen(false)}
        currentKey={geminiApiKey}
        onKeySaved={(newKey) => {
          setStoredGeminiApiKey(newKey);
          setGeminiApiKey(newKey);
          if (typeof window !== 'undefined') {
            localStorage.setItem('adam_selected_model_id', 'gemini-3.6-flash');
          }
          void fetchModels(newKey).then((mList) => {
            setModels(mList);
            const geminiModel = mList.find((m) => m.id === 'gemini-3.6-flash');
            if (geminiModel && geminiModel.is_installed) {
              setSelectedModel(geminiModel);
            }
          });
        }}
        onKeyCleared={() => {
          clearStoredGeminiApiKey();
          setGeminiApiKey(null);
          if (typeof window !== 'undefined') {
            localStorage.removeItem('adam_selected_model_id');
          }
          void fetchModels(null).then((mList) => {
            setModels(mList);
            const primary = mList.find((m) => m.is_primary) || mList[0] || null;
            setSelectedModel(primary);
          });
        }}
      />
    </main>
  );
}
