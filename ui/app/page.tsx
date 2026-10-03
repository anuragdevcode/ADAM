'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import IconRail, { type NavTab } from '@/components/IconRail';
import ChatWindow from '@/components/ChatWindow';
import ConversationHistory from '@/components/ConversationHistory';
import DocumentsView from '@/components/DocumentsView';
import PrecedentsView from '@/components/PrecedentsView';
import AuditView from '@/components/AuditView';
import SourcesView from '@/components/SourcesView';
import ReviewView from '@/components/ReviewView';
import UnifiedSettingsModal, { type SettingsTabId } from '@/components/UnifiedSettingsModal';
import CommandPalette from '@/components/CommandPalette';
import KeyboardShortcutsModal from '@/components/KeyboardShortcutsModal';
import { useToast } from '@/components/ToastProvider';
import {
  Sparkles,
  ChevronDown,
  Search,
  Plus,
  Check,
  ShieldAlert,
  Key,
  Cloud,
  Globe,
} from 'lucide-react';
import SovereignLoadingScreen from '@/components/SovereignLoadingScreen';
import LoginPage from '@/components/LoginPage';
import type { DepartmentItem, ModelInfo, AuthUser } from '@/lib/types';
import {
  fetchModels,
  fetchVocabularies,
  getStoredGeminiApiKey,
  setStoredGeminiApiKey,
  clearStoredGeminiApiKey,
  triggerModelDiscovery,
  getStoredAuthToken,
  getStoredAuthUser,
  fetchCurrentUser,
  clearStoredAuthSession,
} from '@/lib/api';

const DEFAULT_OFFICER_ID = 'officer_dev_001';

export default function HomePage() {
  const [activeNavTab, setActiveNavTab] = useState<NavTab>('home');
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState<SettingsTabId>('general');
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false);
  const [shortcutsModalOpen, setShortcutsModalOpen] = useState(false);

  // Sovereign Loading & Authentication Initialization
  const [isInitializing, setIsInitializing] = useState(true);
  const [showLoadingScreen, setShowLoadingScreen] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);

  // Officer Identity & Clearance State
  const [officerUserId, setOfficerUserId] = useState(DEFAULT_OFFICER_ID);
  const [clearanceLevel, setClearanceLevel] = useState('PUBLIC');
  const [departmentId, setDepartmentId] = useState('ALL');

  // Real Backend Data State
  const [models, setModels] = useState<ModelInfo[]>([]);
  const [selectedModel, setSelectedModel] = useState<ModelInfo | null>(null);
  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const [departments, setDepartments] = useState<DepartmentItem[]>([]);
  const searchFilter = '';
  const modelMenuRef = useRef<HTMLDivElement>(null);

  // Gemini API Key & Cloud Models
  const [geminiApiKey, setGeminiApiKey] = useState<string | null>(null);

  const handleOpenSettings = (tab: SettingsTabId = 'general') => {
    setSettingsTab(tab);
    setSettingsOpen(true);
  };

  const { toast } = useToast();
  const isAirGapped = clearanceLevel === 'RESTRICTED' || clearanceLevel === 'CONFIDENTIAL';

  // Initial authentication verification & sovereign lifecycle check
  useEffect(() => {
    let isMounted = true;
    const initAuth = async () => {
      // 1. Check local session
      const token = getStoredAuthToken();
      const cachedUser = getStoredAuthUser();
      if (token && cachedUser) {
        if (isMounted) {
          setIsAuthenticated(true);
          setCurrentUser(cachedUser);
          setOfficerUserId(cachedUser.username || cachedUser.id);
          setClearanceLevel(cachedUser.clearance_level || 'PUBLIC');
          if (cachedUser.department_id) {
            setDepartmentId(cachedUser.department_id);
          }
        }
      }

      // 2. Validate token with backend asynchronously
      if (token) {
        try {
          const verified = await fetchCurrentUser();
          if (verified && isMounted) {
            setIsAuthenticated(true);
            setCurrentUser(verified);
            setOfficerUserId(verified.username || verified.id);
            setClearanceLevel(verified.clearance_level || 'PUBLIC');
            if (verified.department_id) {
              setDepartmentId(verified.department_id);
            }
          }
        } catch {}
      }

      // Allow calibrated minimum animation duration (500ms) to ensure smooth aperture render
      setTimeout(() => {
        if (isMounted) {
          setIsInitializing(false);
        }
      }, 500);
    };

    void initAuth();
    return () => {
      isMounted = false;
    };
  }, []);

  const handleLoginSuccess = useCallback((user: AuthUser) => {
    setIsAuthenticated(true);
    setCurrentUser(user);
    setOfficerUserId(user.username || user.id);
    setClearanceLevel(user.clearance_level || 'PUBLIC');
    if (user.department_id) {
      setDepartmentId(user.department_id);
    }
    toast.success(`Welcome, ${user.full_name || user.username} (${user.clearance_level} clearance)`);
  }, [toast]);

  const handleContinueAsGuest = useCallback(() => {
    setIsAuthenticated(true);
    setOfficerUserId('citizen_public_guest');
    setClearanceLevel('PUBLIC');
    toast.info('Entered in Public Citizen mode (Standard official records)');
  }, [toast]);

  const handleSignOut = useCallback(() => {
    clearStoredAuthSession();
    setIsAuthenticated(false);
    setCurrentUser(null);
    setOfficerUserId(DEFAULT_OFFICER_ID);
    setClearanceLevel('PUBLIC');
    toast.info('Signed out of administrative session');
  }, [toast]);

  // Dismiss model menu on outside click or Escape
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

  const handleNewThread = useCallback(() => {
    setActiveNavTab('home');
    setActiveSessionId(null);
    setIsHistoryOpen(false);
    toast.info('Started a new conversation thread');
  }, [toast]);

  // Global Keyboard Shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Cmd+K or Ctrl+K -> Command Palette
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setCommandPaletteOpen((prev) => !prev);
        return;
      }

      // Cmd+N or Ctrl+N -> New Thread
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'n') {
        e.preventDefault();
        handleNewThread();
        return;
      }

      // Cmd+/ or Ctrl+/ -> Shortcuts Cheat-sheet
      if ((e.metaKey || e.ctrlKey) && e.key === '/') {
        e.preventDefault();
        setShortcutsModalOpen((prev) => !prev);
        return;
      }

      // Cmd+, or Ctrl+, -> Settings & Governance
      if ((e.metaKey || e.ctrlKey) && e.key === ',') {
        e.preventDefault();
        handleOpenSettings('general');
        return;
      }

      // Navigation shortcuts Cmd+1 to Cmd+6
      if (e.metaKey || e.ctrlKey) {
        if (e.key === '1') {
          e.preventDefault();
          setActiveNavTab('home');
        } else if (e.key === '2') {
          e.preventDefault();
          setActiveNavTab('docs');
        } else if (e.key === '3') {
          e.preventDefault();
          setActiveNavTab('network');
        } else if (e.key === '4') {
          e.preventDefault();
          setActiveNavTab('audit');
        } else if (e.key === '5') {
          e.preventDefault();
          setActiveNavTab('database');
        } else if (e.key === '6') {
          e.preventDefault();
          setActiveNavTab('review');
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleNewThread]);

  return (
    <>
      {showLoadingScreen && (
        <SovereignLoadingScreen
          isReady={!isInitializing}
          onTransitionComplete={() => setShowLoadingScreen(false)}
        />
      )}

      {!isAuthenticated ? (
        <LoginPage
          onLoginSuccess={handleLoginSuccess}
          onContinueAsGuest={handleContinueAsGuest}
        />
      ) : (
        <main className="w-screen h-screen min-h-[600px] bg-[#f8fafc] dark:bg-[#090d16] text-[#0f172a] dark:text-[#f1f5f9] overflow-hidden select-none animate-in fade-in duration-300">
          <div className="w-full h-full bg-white dark:bg-[#0d121e] flex overflow-hidden relative">
            {/* Left Navigation Rail */}
            <IconRail
              activeTab={activeNavTab}
              onSelectTab={(tab) => {
                setActiveNavTab(tab);
                setIsHistoryOpen(false);
              }}
              onToggleHistory={() => setIsHistoryOpen((v) => !v)}
              isHistoryOpen={isHistoryOpen}
              onNewThread={handleNewThread}
              onOpenSettings={() => handleOpenSettings('general')}
              onOpenShortcuts={() => setShortcutsModalOpen(true)}
              onSignOut={handleSignOut}
              userName={currentUser?.full_name || currentUser?.username || officerUserId}
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
        <div className="flex-1 flex flex-col h-full overflow-hidden select-auto min-w-0">
          {/* Top Header Bar */}
          <header className="h-[64px] px-4 sm:px-6 border-b border-slate-200/80 dark:border-slate-800 flex items-center justify-between bg-white dark:bg-[#0d121e] shrink-0 z-10">
            {/* Left: Model Selector Pill */}
            <div ref={modelMenuRef} className="relative">
              <button
                type="button"
                onClick={() => setModelDropdownOpen((open) => !open)}
                className="group inline-flex items-center gap-2 px-3 py-1.5 rounded-xl border border-slate-200/90 dark:border-slate-800 bg-white dark:bg-[#131926] hover:border-purple-300/40 dark:hover:border-purple-500/30 hover:shadow-[0_0_16px_-3px_rgba(168,85,247,0.25)] hover:bg-purple-50/20 dark:hover:bg-purple-950/20 text-xs font-medium text-slate-700 dark:text-slate-200 shadow-2xs hover:scale-[1.02] active:scale-95 transition-all duration-150 cursor-pointer"
                title="Select active inference runtime or cloud model"
              >
                <Sparkles className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400 group-hover:scale-110 transition-transform duration-200" />
                <span className="font-semibold">{selectedModel?.name || 'ADAM model'}</span>
                {selectedModel?.quantization && (
                  <span className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-[10px] font-mono text-slate-500 dark:text-slate-400">
                    {selectedModel.quantization}
                  </span>
                )}
                {selectedModel?.is_cloud ? (
                  <span className="px-1.5 py-0.5 rounded bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 text-[9px] font-semibold border border-indigo-200 dark:border-indigo-800">
                    Cloud
                  </span>
                ) : (
                  <span className="px-1.5 py-0.5 rounded bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 text-[9px] font-semibold border border-emerald-200 dark:border-emerald-800">
                    Local
                  </span>
                )}
                <ChevronDown className={`w-3 h-3 text-slate-400 dark:text-slate-500 transition-transform duration-200 ${modelDropdownOpen ? 'rotate-180 text-purple-600 dark:text-purple-400' : ''}`} />
              </button>

              {/* Model Dropdown Menu */}
              {modelDropdownOpen && (
                <div className="absolute left-0 top-full mt-2 w-84 bg-white dark:bg-[#131926] rounded-2xl border border-slate-200 dark:border-slate-800 shadow-2xl py-2 z-30 divide-y divide-slate-100 dark:divide-slate-800 animate-in fade-in zoom-in-95 duration-150 origin-top-left">
                  <div className="px-3.5 py-1 text-[10px] uppercase tracking-wider font-semibold text-slate-400 dark:text-slate-500">
                    Available Runtimes &amp; Models
                  </div>

                  <div className="py-1 max-h-72 overflow-y-auto">
                    {(() => {
                      let lastGroup: string | null = null;
                      return models.map((model) => {
                        const isCloudRestricted = isAirGapped && model.is_cloud;
                        const isSelectable = Boolean(
                          model.is_installed &&
                            !model.requires_legal_review &&
                            model.is_supported !== false &&
                            !isCloudRestricted,
                        );
                        const currentGroup = model.display_group || (model.is_cloud ? 'REMOTE' : 'LOCAL');
                        const showGroupHeader = currentGroup !== lastGroup;
                        lastGroup = currentGroup;

                        return (
                          <div key={model.id}>
                            {showGroupHeader && (
                              <div className="px-3.5 pt-2 pb-0.5 text-[9px] uppercase tracking-widest font-semibold text-slate-400 dark:text-slate-500">
                                {currentGroup === 'LOCAL' ? 'Local Sovereign Models' : 'Remote APIs'}
                              </div>
                            )}
                            <button
                              type="button"
                              disabled={!isSelectable}
                              onClick={() => {
                                if (!isSelectable) return;
                                setSelectedModel(model);
                                if (typeof window !== 'undefined') {
                                  localStorage.setItem('adam_selected_model_id', model.id);
                                }
                                toast.success(`Switched model to ${model.name}`);
                                setModelDropdownOpen(false);
                              }}
                              className={`w-full text-left px-3.5 py-2 text-xs flex items-center justify-between transition-colors ${
                                isSelectable
                                  ? 'hover:bg-purple-50 dark:hover:bg-purple-950/40 text-slate-700 dark:text-slate-200 cursor-pointer'
                                  : 'opacity-40 cursor-not-allowed bg-slate-50/50 dark:bg-slate-900/30 text-slate-400 select-none'
                              }`}
                            >
                              <div className="min-w-0 pr-2">
                                <div className="flex items-center gap-1.5 flex-wrap">
                                  <p className="font-medium truncate">{model.name}</p>
                                  {isCloudRestricted ? (
                                    <span className="inline-flex items-center gap-0.5 text-[9px] px-1.5 py-0.5 rounded bg-red-50 dark:bg-red-950/60 text-red-700 dark:text-red-400 border border-red-200 dark:border-red-800 font-semibold uppercase">
                                      <ShieldAlert className="w-2.5 h-2.5" /> Blocked
                                    </span>
                                  ) : model.is_cloud ? (
                                    <span className="inline-flex items-center gap-0.5 text-[9px] px-1.5 py-0.5 rounded bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800 font-semibold uppercase">
                                      <Cloud className="w-2.5 h-2.5" /> Cloud
                                    </span>
                                  ) : null}
                                </div>
                                <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5">
                                  {isCloudRestricted
                                    ? `Disabled under ${clearanceLevel} clearance`
                                    : model.is_cloud
                                    ? 'Google Gemini Cloud'
                                    : `${model.quantization || 'Local'} • Sovereign Host`}
                                </p>
                              </div>
                              {selectedModel?.id === model.id && (
                                <Check className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400 shrink-0" />
                              )}
                            </button>
                          </div>
                        );
                      });
                    })()}
                  </div>

                  {/* Actions Section in Model Dropdown */}
                  <div className="pt-1">
                    <button
                      type="button"
                      onClick={() => {
                        setModelDropdownOpen(false);
                        handleOpenSettings('providers');
                      }}
                      className="w-full text-left px-3.5 py-2 text-xs flex items-center justify-between hover:bg-purple-50 dark:hover:bg-purple-950/40 text-purple-900 dark:text-purple-300 transition-colors"
                    >
                      <div className="flex items-center gap-2">
                        <Key className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400 shrink-0" />
                        <span className="font-semibold">
                          {geminiApiKey ? 'Configure Gemini Key' : '+ Add Gemini Key'}
                        </span>
                      </div>
                      {geminiApiKey ? (
                        <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-100 dark:bg-emerald-950/80 text-emerald-800 dark:text-emerald-300 font-mono">
                          Active
                        </span>
                      ) : (
                        <span className="text-[10px] text-purple-700 dark:text-purple-400 bg-purple-100/60 dark:bg-purple-900/40 px-1.5 py-0.5 rounded font-medium">
                          Cloud
                        </span>
                      )}
                    </button>

                    <button
                      type="button"
                      onClick={() => {
                        void triggerModelDiscovery().then((result) => {
                          if (result && result.discovered_count > 0) {
                            const activeKey = getStoredGeminiApiKey();
                            void fetchModels(activeKey, clearanceLevel).then(setModels);
                            toast.success(`Discovered ${result.discovered_count} new models`);
                          } else {
                            toast.info('Model inventory refreshed');
                          }
                        });
                        setModelDropdownOpen(false);
                      }}
                      className="w-full text-left px-3.5 py-2 text-xs flex items-center gap-2 hover:bg-slate-50 dark:hover:bg-slate-800/40 text-slate-600 dark:text-slate-300 transition-colors"
                    >
                      <span className="text-slate-400 text-sm leading-none">⟳</span>
                      <span className="font-medium">Refresh Models</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => {
                        setModelDropdownOpen(false);
                        handleOpenSettings('providers');
                      }}
                      className="w-full text-left px-3.5 py-2 text-xs flex items-center gap-2 hover:bg-purple-50 dark:hover:bg-purple-950/40 text-purple-700 dark:text-purple-400 transition-colors"
                    >
                      <Globe className="w-3.5 h-3.5 text-purple-500 shrink-0" />
                      <span className="font-semibold">+ Add Remote API</span>
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Middle/Right: Quick Search Cmd+K + Security Badges + New Thread */}
            <div className="flex items-center gap-2.5">
              {/* Command Palette Search Trigger Button */}
              <button
                type="button"
                onClick={() => setCommandPaletteOpen(true)}
                className="hidden md:inline-flex items-center gap-2.5 px-3 py-1.5 rounded-xl border border-slate-200/90 dark:border-slate-800 bg-slate-50/70 dark:bg-[#131926] text-xs text-slate-500 dark:text-slate-400 hover:border-purple-300/40 dark:hover:border-purple-500/30 hover:shadow-[0_0_16px_-3px_rgba(168,85,247,0.22)] hover:bg-white dark:hover:bg-[#161d2d] hover:scale-[1.02] active:scale-95 transition-all duration-150 cursor-pointer"
                title="Search commands, views, models, departments (⌘K)"
              >
                <Search className="w-3.5 h-3.5 text-slate-400" />
                <span>Search commands…</span>
                <kbd className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-200/80 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-300 dark:border-slate-700">
                  ⌘K
                </kbd>
              </button>

              {/* Air-Gapped Indicator */}
              {isAirGapped && (
                <div className="hidden lg:inline-flex items-center gap-1.5 text-[10px] px-2.5 py-1 rounded-xl bg-purple-50 dark:bg-purple-950/60 text-purple-800 dark:text-purple-300 border border-purple-200 dark:border-purple-800 font-medium">
                  <ShieldAlert className="w-3 h-3 text-purple-600 dark:text-purple-400" />
                  <span>Air-Gapped Active</span>
                </div>
              )}

              {/* + New Thread Button */}
              <button
                type="button"
                onClick={handleNewThread}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl bg-slate-900 hover:bg-slate-800 dark:bg-purple-600 dark:hover:bg-purple-500 hover:scale-105 active:scale-90 text-white text-xs font-semibold shadow-xs hover:shadow-[0_0_18px_rgba(168,85,247,0.35)] transition-all duration-200 ease-spring cursor-pointer"
                title="Start a new thread (⌘N)"
              >
                <Plus className="w-3.5 h-3.5" />
                <span className="hidden xs:inline">New Thread</span>
                <kbd className="hidden sm:inline-block ml-1 opacity-60 text-[10px] font-mono">⌘N</kbd>
              </button>
            </div>
          </header>

          {/* Dynamic Main View Switcher */}
          <section key={activeNavTab} className="flex-1 overflow-hidden relative animate-in fade-in duration-200 ease-smooth">
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
                onOpenApiKeyModal={() => handleOpenSettings('providers')}
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

      {/* Global Command Palette */}
      <CommandPalette
        isOpen={commandPaletteOpen}
        onClose={() => setCommandPaletteOpen(false)}
        onSelectNav={(tab) => {
          setActiveNavTab(tab);
          setIsHistoryOpen(false);
        }}
        onNewThread={handleNewThread}
        models={models}
        selectedModel={selectedModel}
        onSelectModel={(model) => setSelectedModel(model)}
        departments={departments}
        selectedDept={departmentId}
        onSelectDept={(dept) => setDepartmentId(dept)}
        onOpenSettings={(tab) => handleOpenSettings(tab || 'general')}
        onOpenApiKey={() => handleOpenSettings('providers')}
        onOpenIntrospection={() => handleOpenSettings('telemetry')}
        onOpenAdvancedSettings={() => handleOpenSettings('inference')}
        onOpenShortcuts={() => setShortcutsModalOpen(true)}
      />

      {/* Keyboard Shortcuts Cheat-sheet Modal */}
      <KeyboardShortcutsModal
        isOpen={shortcutsModalOpen}
        onClose={() => setShortcutsModalOpen(false)}
      />

      {/* Single Authoritative Unified Settings Hub */}
      <UnifiedSettingsModal
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        initialTab={settingsTab}
        userId={officerUserId}
        onUpdateUserId={(id) => setOfficerUserId(id)}
        clearanceLevel={clearanceLevel}
        onUpdateClearanceLevel={(lvl) => setClearanceLevel(lvl)}
        departmentId={departmentId}
        onUpdateDepartmentId={(dept) => setDepartmentId(dept)}
        departments={departments}
        sessionId={activeSessionId}
        geminiApiKey={geminiApiKey}
        onUpdateGeminiApiKey={(newKey) => {
          if (newKey) {
            setStoredGeminiApiKey(newKey);
            setGeminiApiKey(newKey);
            if (typeof window !== 'undefined') {
              localStorage.setItem('adam_selected_model_id', 'gemini-3.6-flash');
            }
            void fetchModels(newKey, clearanceLevel).then((mList) => {
              setModels(mList);
              const geminiModel = mList.find((m) => m.id === 'gemini-3.6-flash');
              if (geminiModel && geminiModel.is_installed) {
                setSelectedModel(geminiModel);
              }
            });
            toast.success('Gemini API Key validated and configured');
          } else {
            clearStoredGeminiApiKey();
            setGeminiApiKey(null);
            if (typeof window !== 'undefined') {
              localStorage.removeItem('adam_selected_model_id');
            }
            void fetchModels(null, clearanceLevel).then((mList) => {
              setModels(mList);
              const primary = mList.find((m) => m.is_primary) || mList[0] || null;
              setSelectedModel(primary);
            });
            toast.info('Gemini API Key cleared. Defaulted to local models');
          }
        }}
      />
        </main>
      )}
    </>
  );
}
