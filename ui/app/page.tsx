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
import { Sparkles, ChevronDown, Search, Plus, Check, Shield, ShieldAlert, Lock, Key, Cloud } from 'lucide-react';
import type { DepartmentItem, ModelInfo } from '@/lib/types';
import { fetchModels, fetchVocabularies, getStoredGeminiApiKey, setStoredGeminiApiKey, clearStoredGeminiApiKey } from '@/lib/api';

const DEFAULT_OFFICER_ID = 'officer_dev_001';

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

  const isAirGapped = clearanceLevel === 'RESTRICTED' || clearanceLevel === 'CONFIDENTIAL';

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

  // Initial and reactive load from API
  useEffect(() => {
    const key = getStoredGeminiApiKey();
    setGeminiApiKey(key);

    const loadModels = () => {
      const activeKey = getStoredGeminiApiKey();
      void fetchModels(activeKey, clearanceLevel).then((mList) => {
        setModels(mList);
        const supportedInstalled = mList.filter(
          (m) =>
            m.is_installed &&
            !m.requires_legal_review &&
            m.is_supported !== false &&
            !(isAirGapped && m.is_cloud),
        );
        const storedModelId = typeof window !== 'undefined' ? localStorage.getItem('adam_selected_model_id') : null;
        setSelectedModel((current) => {
          // If air-gapped is active, current cloud model must be replaced
          if (isAirGapped && current?.is_cloud) {
            return supportedInstalled.find((m) => !m.is_cloud && m.is_primary) || supportedInstalled.find((m) => !m.is_cloud) || null;
          }
          if (current && supportedInstalled.some((model) => model.id === current.id)) return current;
          if (storedModelId && !(isAirGapped && storedModelId.includes('gemini'))) {
            const foundStored = supportedInstalled.find((m) => m.id === storedModelId);
            if (foundStored) return foundStored;
          }
          if (activeKey && !isAirGapped) {
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
  }, [clearanceLevel, isAirGapped]);

  const handleNewThread = () => {
    setActiveNavTab('home');
    setActiveSessionId(null);
    setIsHistoryOpen(false);
  };

  return (
    <main className="w-screen h-screen min-h-[600px] bg-[#f8fafc] overflow-hidden">
      <div className="w-full h-full bg-white flex overflow-hidden relative">
        {/* Left Navigation Rail */}
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

        {/* Slide-out Session History Drawer */}
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

        {/* Main Application Area */}
        <div className="flex-1 flex flex-col h-full overflow-hidden">
          {/* Top Header Bar */}
          <header className="h-[68px] px-4 sm:px-6 border-b border-[#eaecf0] flex items-center justify-between bg-white shrink-0 z-10">
            {/* Installed artifacts are selectable; unavailable artifacts remain visible but frozen. */}
            <div ref={modelMenuRef} className="relative">
              <button
                type="button"
                onClick={() => setModelDropdownOpen((open) => !open)}
                className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-[#e4e7ec] bg-white hover:border-purple-200 hover:bg-purple-50/40 text-xs font-medium text-gray-700 shadow-sm transition-all"
                title="Select an installed model"
              >
                <Sparkles className="w-3.5 h-3.5 text-purple-600" />
                <span className="font-semibold">{selectedModel?.name || 'ADAM model'}</span>
                {selectedModel?.quantization && (
                  <span className="px-1.5 py-0.5 rounded bg-gray-100 text-[10px] font-mono text-gray-500">
                    {selectedModel.quantization}
                  </span>
                )}
                <ChevronDown className="w-3 h-3 text-gray-400" />
              </button>
              {modelDropdownOpen && (
                <div className="absolute left-0 top-full mt-2 w-80 bg-white rounded-2xl border border-[#eaecf0] shadow-[0_16px_36px_rgba(16,24,40,0.12)] py-1.5 z-30">
                  <div className="px-3 py-1 text-[10px] uppercase tracking-wider font-semibold text-gray-400">
                    Model inventory
                  </div>
                  {models.map((model) => {
                    const isCloudRestricted = isAirGapped && model.is_cloud;
                    const isSelectable = Boolean(
                      model.is_installed &&
                      !model.requires_legal_review &&
                      model.is_supported !== false &&
                      !isCloudRestricted,
                    );
                    return (
                      <button
                        key={model.id}
                        type="button"
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
                          isCloudRestricted
                            ? `Cloud models are disabled for ${clearanceLevel} clearance under air-gapped data sovereignty policy`
                            : isSelectable
                            ? `Use ${model.name}`
                            : model.unavailable_reason || 'Not supported / pending review'
                        }
                        className={`w-full text-left px-3 py-2 text-xs flex items-center justify-between transition-colors ${
                          isSelectable
                            ? 'hover:bg-purple-50 text-gray-700 cursor-pointer'
                            : 'opacity-40 cursor-not-allowed bg-gray-50/80 text-gray-400 select-none'
                        }`}
                      >
                        <div className="min-w-0 pr-2">
                          <div className="flex items-center gap-1.5">
                            <p className="font-medium truncate">{model.name}</p>
                            {isCloudRestricted ? (
                              <span className="inline-flex items-center gap-0.5 text-[9px] px-1.5 py-0.5 rounded bg-red-50 text-red-700 border border-red-200 font-semibold uppercase">
                                <ShieldAlert className="w-2.5 h-2.5" /> Air-Gapped: Cloud Blocked
                              </span>
                            ) : model.is_cloud ? (
                              <span className="inline-flex items-center gap-0.5 text-[9px] px-1.5 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200 font-semibold uppercase">
                                <Cloud className="w-2.5 h-2.5" /> Cloud
                              </span>
                            ) : null}
                            {model.requires_legal_review ? (
                              <span className="inline-flex items-center gap-0.5 text-[9px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 border border-amber-300 font-semibold uppercase">
                                <Lock className="w-2.5 h-2.5" /> Frozen • Legal Review
                              </span>
                            ) : !model.is_installed && !isCloudRestricted ? (
                              <span className="text-[9px] uppercase text-gray-400">
                                {model.is_cloud ? 'Key required' : 'Not installed'}
                              </span>
                            ) : null}
                          </div>
                          <p className="text-[10px] text-gray-400 mt-0.5">
                            {isCloudRestricted
                              ? `Cloud disabled under Air-Gapped Data Sovereignty Policy (${clearanceLevel})`
                              : isSelectable
                              ? (model.is_cloud ? 'Google Gemini Cloud • Active' : `${model.quantization} • ready locally`)
                              : model.unavailable_reason}
                          </p>
                        </div>
                        {selectedModel?.id === model.id && <Check className="w-3.5 h-3.5 text-purple-600 shrink-0" />}
                      </button>
                    );
                  })}

                  <div className="my-1.5 border-t border-[#eaecf0]" />

                  {/* Add / Configure Gemini Key button */}
                  <button
                    type="button"
                    onClick={() => {
                      setModelDropdownOpen(false);
                      setApiKeyModalOpen(true);
                    }}
                    className="w-full text-left px-3 py-2 text-xs flex items-center justify-between hover:bg-purple-50 text-purple-900 transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      <Key className="w-3.5 h-3.5 text-purple-600 shrink-0" />
                      <span className="font-semibold">
                        {geminiApiKey ? 'Configure Gemini API Key' : '+ Add Gemini API Key'}
                      </span>
                    </div>
                    {geminiApiKey ? (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 border border-emerald-200 font-mono">
                        Active
                      </span>
                    ) : (
                      <span className="text-[10px] text-purple-700 bg-purple-100/60 px-1.5 py-0.5 rounded font-medium">
                        Voice & Models
                      </span>
                    )}
                  </button>
                </div>
              )}
            </div>

            {/* Top-Right: Air-Gapped Indicator + Search Threads + Clearance Indicator + New Thread */}
            <div className="flex items-center gap-2.5">
              {isAirGapped && (
                <div className="hidden lg:inline-flex items-center gap-1.5 text-[10px] px-2.5 py-1 rounded-xl bg-purple-50 text-purple-800 border border-purple-200 font-medium">
                  <ShieldAlert className="w-3 h-3 text-purple-600" />
                  <span>Air-Gapped Sovereignty Active</span>
                </div>
              )}

              {/* Search Thread Filter */}
              <div className="hidden md:flex items-center gap-2 px-3 py-2 rounded-xl border border-[#e4e7ec] bg-[#fcfcfd] text-xs text-gray-600 focus-within:border-purple-300 focus-within:bg-white transition-all">
                <Search className="w-3.5 h-3.5 text-gray-400" />
                <input
                  type="text"
                  placeholder="Search threads"
                  value={searchFilter}
                  onChange={(e) => {
                    setSearchFilter(e.target.value);
                    if (!isHistoryOpen) setIsHistoryOpen(true);
                  }}
                  className="bg-transparent outline-none w-28 text-xs placeholder-gray-400"
                />
              </div>

              {/* Clearance Badge */}
              <button
                type="button"
                onClick={() => setSettingsOpen(true)}
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl border border-[#e4e7ec] bg-white hover:bg-gray-50 text-xs font-semibold text-gray-700 transition-all"
                title="Click to view or change officer clearance"
              >
                <Shield className="w-3.5 h-3.5 text-purple-600" />
                <span>{clearanceLevel}</span>
              </button>

              {/* + New Thread Button */}
              <button
                type="button"
                onClick={handleNewThread}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-[#292c33] hover:bg-[#17191d] active:scale-[0.98] text-white text-xs font-semibold shadow-sm transition-all"
              >
                <Plus className="w-3.5 h-3.5" />
                <span>New Thread</span>
              </button>
            </div>
          </header>

          {/* Dynamic Main View Switcher */}
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
                onOpenApiKeyModal={() => setApiKeyModalOpen(true)}
                onOpenModelSelector={() => setModelDropdownOpen(true)}
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

      {/* Settings & Officer Clearance Governance Modal */}
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
