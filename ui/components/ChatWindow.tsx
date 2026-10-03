'use client';

import { useState, useRef, useEffect, useCallback, useId } from 'react';
import {
  streamChat,
  getSessionHistory,
  getStoredAdvancedSettings,
  updateStoredThinkingEnabled,
  ADAM_SETTINGS_UPDATED_EVENT,
} from '@/lib/api';
import type { ChatMessage, DepartmentItem, ChatErrorDetails, AdvancedSettingsBundle } from '@/lib/types';
import CitationCard from './CitationCard';
import CurrencyBanner from './CurrencyBanner';
import ExecutionStatus from './ExecutionStatus';
import VoiceControls from './VoiceControls';
import { useVoiceConversation, type VoiceAnswer } from '@/lib/useVoiceConversation';
import { Markdown } from '@/lib/markdown';
import { useToast } from './ToastProvider';
import {
  Sparkles,
  Paperclip,
  ChevronDown,
  ArrowUp,
  Square,
  Check,
  ChevronRight,
  FileText,
  Link2,
  Banknote,
  Landmark,
  Clock,
  LifeBuoy,
  AlertTriangle,
  RotateCcw,
  Key,
  Copy,
  ServerOff,
  Cloud,
  Brain,
  Zap,
} from 'lucide-react';

interface ChatWindowProps {
  userId: string;
  sessionId: string | null;
  onSessionCreated: (sessionId: string) => void;
  userName?: string;
  clearanceLevel: string;
  modelId?: string;
  departments: DepartmentItem[];
  onOpenUpload?: () => void;
  onOpenApiKeyModal?: () => void;
  onOpenModelSelector?: () => void;
}

function CopyableCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // ignore
    }
  };

  return (
    <div className="mt-2.5 flex items-center justify-between gap-3 px-3 py-2 bg-slate-900 dark:bg-[#0c1017] text-slate-200 rounded-lg font-mono text-xs border border-slate-700/60 dark:border-slate-800 shadow-inner">
      <div className="flex items-center gap-2 overflow-x-auto select-all">
        <span className="text-purple-400 select-none font-bold">$</span>
        <span className="text-slate-100">{command}</span>
      </div>
      <button
        type="button"
        onClick={handleCopy}
        className="shrink-0 inline-flex items-center gap-1 text-[11px] font-sans font-medium text-slate-300 hover:text-white px-2 py-1 rounded bg-white/10 hover:bg-white/20 transition-colors"
      >
        {copied ? (
          <>
            <Check className="w-3 h-3 text-emerald-400" />
            <span className="text-emerald-400">Copied</span>
          </>
        ) : (
          <>
            <Copy className="w-3 h-3 text-slate-400" />
            <span>Copy</span>
          </>
        )}
      </button>
    </div>
  );
}

function AiErrorCard({
  error,
  onRetry,
  onOpenApiKeyModal,
  onOpenModelSelector,
}: {
  error: ChatErrorDetails;
  onRetry: () => void;
  onOpenApiKeyModal?: () => void;
  onOpenModelSelector?: () => void;
}) {
  const [showTechnicalDetails, setShowTechnicalDetails] = useState(false);

  const isOllamaIssue = error.category === 'ollama_offline' || error.category === 'model_not_pulled';
  const isGeminiIssue = error.category === 'gemini_key_missing' || error.category === 'gemini_api_error';

  return (
    <div className="w-full rounded-2xl border border-rose-200 dark:border-rose-900/60 bg-rose-50/50 dark:bg-rose-950/20 p-4 sm:p-5 shadow-xs text-left transition-all">
      <div className="flex items-start gap-3">
        <div className="w-8 h-8 rounded-xl bg-rose-100 dark:bg-rose-900/40 flex items-center justify-center shrink-0 text-rose-700 dark:text-rose-300 mt-0.5 shadow-xs">
          {isGeminiIssue ? (
            <Key className="w-4 h-4" />
          ) : isOllamaIssue ? (
            <ServerOff className="w-4 h-4" />
          ) : (
            <AlertTriangle className="w-4 h-4" />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100 leading-tight">
              {error.title || 'Inference Service Unavailable'}
            </h3>
            <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-rose-100 dark:bg-rose-900/50 text-rose-800 dark:text-rose-300 border border-rose-200 dark:border-rose-800">
              {error.category === 'ollama_offline'
                ? 'Local Service Offline'
                : error.category === 'model_not_pulled'
                ? 'Model Missing'
                : error.category === 'gemini_key_missing'
                ? 'API Key Required'
                : error.category === 'gemini_api_error'
                ? 'API Error'
                : error.category === 'rate_limit'
                ? 'Rate Limited'
                : 'Connection Issue'}
            </span>
          </div>

          <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed">
            {error.message}
          </p>

          {error.commandHint && (
            <CopyableCommand command={error.commandHint} />
          )}

          <div className="mt-3.5 flex items-center gap-2 flex-wrap pt-2.5 border-t border-rose-200/60 dark:border-rose-900/40">
            <button
              type="button"
              onClick={onRetry}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-white dark:bg-[#131926] border border-slate-300 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-200 shadow-xs transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5 text-slate-500" />
              <span>Retry</span>
            </button>

            {(isGeminiIssue || isOllamaIssue) && onOpenApiKeyModal && (
              <button
                type="button"
                onClick={onOpenApiKeyModal}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-purple-600 hover:bg-purple-700 text-white shadow-xs transition-colors"
              >
                {isGeminiIssue ? <Key className="w-3.5 h-3.5" /> : <Cloud className="w-3.5 h-3.5" />}
                <span>{isGeminiIssue ? 'Configure Gemini Key' : 'Switch to Google Gemini Cloud'}</span>
              </button>
            )}

            {onOpenModelSelector && (
              <button
                type="button"
                onClick={onOpenModelSelector}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-white dark:bg-[#131926] border border-purple-200 dark:border-purple-800 hover:bg-purple-50 dark:hover:bg-purple-950/40 text-purple-700 dark:text-purple-300 shadow-xs transition-colors"
              >
                <Sparkles className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400" />
                <span>Switch Model</span>
              </button>
            )}

            {error.raw && error.raw !== error.message && (
              <button
                type="button"
                onClick={() => setShowTechnicalDetails(!showTechnicalDetails)}
                className="ml-auto text-[11px] text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 underline underline-offset-2 transition-colors"
              >
                {showTechnicalDetails ? 'Hide details' : 'Technical details'}
              </button>
            )}
          </div>

          {showTechnicalDetails && error.raw && (
            <div className="mt-2.5 p-2.5 rounded-lg bg-slate-900 text-slate-300 font-mono text-[11px] overflow-x-auto leading-normal">
              {error.raw}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

const EXAMPLE_CARDS = [
  {
    title: 'Revised Dearness Allowance rate for State employees',
    dept: 'Finance & Treasury',
    query:
      'What is the revised Dearness Allowance rate for Uttarakhand state employees effective July 2024 under GO UK/FIN/2024/3401?',
    icon: Banknote,
  },
  {
    title: 'Timeline for online land mutation (dakhil-kharij)',
    dept: 'Board of Revenue',
    query:
      'What is the prescribed timeline for disposing of online land mutation and varasat applications in Uttarakhand?',
    icon: Landmark,
  },
  {
    title: 'Secretariat working hours and holiday schedule',
    dept: 'General Administration',
    query: 'What are the official working hours for the Uttarakhand Civil Secretariat and official holiday rules?',
    icon: Clock,
  },
  {
    title: 'SDRF ex-gratia relief norms for loss of life',
    dept: 'Disaster Management',
    query: 'What ex-gratia relief is payable from the State Disaster Response Fund (SDRF) in case of loss of life?',
    icon: LifeBuoy,
  },
];

function ThoughtAccordion({
  thinking,
  isThinking,
}: {
  thinking?: string | null;
  isThinking?: boolean;
}) {
  const [isExpanded, setIsExpanded] = useState(false);

  // Auto-expand while thinking tokens are actively generating
  useEffect(() => {
    if (isThinking) {
      setIsExpanded(true);
    }
  }, [isThinking]);

  if (!thinking && !isThinking) return null;

  return (
    <div className="mb-3 rounded-xl border border-purple-200/80 dark:border-purple-900/50 bg-purple-50/40 dark:bg-purple-950/20 overflow-hidden transition-all text-left shadow-xs">
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-3.5 py-2 flex items-center justify-between text-xs font-medium text-purple-900 dark:text-purple-300 hover:bg-purple-100/50 dark:hover:bg-purple-900/30 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Brain
            className={`w-3.5 h-3.5 ${
              isThinking ? 'text-purple-600 dark:text-purple-400 animate-pulse' : 'text-purple-500'
            }`}
          />
          <span className="font-semibold">
            {isThinking ? 'Thinking & Unrolling Reasoning...' : 'Thought Process'}
          </span>
          {isThinking && (
            <span className="flex h-2 w-2 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-purple-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-purple-500" />
            </span>
          )}
          {!isThinking && thinking && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-100 dark:bg-purple-900/60 text-purple-700 dark:text-purple-300 font-mono">
              Deep Think
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5 text-slate-400">
          <span className="text-[11px] font-normal">{isExpanded ? 'Hide' : 'Show'}</span>
          <ChevronRight
            className={`w-3.5 h-3.5 transition-transform duration-200 ${
              isExpanded ? 'rotate-90' : ''
            }`}
          />
        </div>
      </button>

      {isExpanded && (
        <div className="px-3.5 pb-3 pt-1 border-t border-purple-100 dark:border-purple-900/40">
          <div className="text-xs font-mono text-slate-600 dark:text-slate-400 leading-relaxed whitespace-pre-wrap max-h-72 overflow-y-auto pr-1">
            {thinking || (isThinking ? 'Analyzing query parameters and unrolling logic...' : '')}
            {isThinking && (
              <span className="inline-block w-1.5 h-3.5 ml-1 bg-purple-500 animate-pulse rounded-full align-middle" />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function ChatWindow({
  userId,
  sessionId,
  onSessionCreated,
  userName = 'Officer',
  clearanceLevel,
  modelId,
  departments,
  onOpenUpload,
  onOpenApiKeyModal,
  onOpenModelSelector,
}: ChatWindowProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [lastAnswer, setLastAnswer] = useState<VoiceAnswer>({ text: '', seq: 0 });
  const [citationEnabled, setCitationEnabled] = useState(true);
  const [deepThinkEnabled, setDeepThinkEnabled] = useState<boolean>(() => {
    if (typeof window !== 'undefined') {
      const stored = getStoredAdvancedSettings();
      if (stored?.generation?.thinking_enabled != null) {
        return stored.generation.thinking_enabled;
      }
    }
    return false;
  });
  const [selectedDept, setSelectedDept] = useState<string>('ALL');
  const [deptMenuOpen, setDeptMenuOpen] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const locallyStartedSession = useRef<string | null>(null);
  const idPrefix = useId();
  const { toast } = useToast();

  // Keep deepThinkEnabled synchronized with AdvancedSettings / UnifiedSettings / storage events
  useEffect(() => {
    const stored = getStoredAdvancedSettings();
    if (stored?.generation?.thinking_enabled != null) {
      setDeepThinkEnabled(stored.generation.thinking_enabled);
    }

    const handleSettingsUpdated = (e: Event) => {
      const customEvent = e as CustomEvent<AdvancedSettingsBundle>;
      if (customEvent.detail?.generation?.thinking_enabled != null) {
        setDeepThinkEnabled(customEvent.detail.generation.thinking_enabled);
      } else {
        const current = getStoredAdvancedSettings();
        if (current?.generation?.thinking_enabled != null) {
          setDeepThinkEnabled(current.generation.thinking_enabled);
        }
      }
    };

    const handleStorage = (e: StorageEvent) => {
      if (e.key === 'adam_advanced_settings') {
        const current = getStoredAdvancedSettings();
        if (current?.generation?.thinking_enabled != null) {
          setDeepThinkEnabled(current.generation.thinking_enabled);
        }
      }
    };

    window.addEventListener(ADAM_SETTINGS_UPDATED_EVENT, handleSettingsUpdated);
    window.addEventListener('storage', handleStorage);
    return () => {
      window.removeEventListener(ADAM_SETTINGS_UPDATED_EVENT, handleSettingsUpdated);
      window.removeEventListener('storage', handleStorage);
    };
  }, []);

  const handleToggleDeepThink = useCallback(() => {
    setDeepThinkEnabled((prev) => {
      const next = !prev;
      updateStoredThinkingEnabled(next);
      return next;
    });
  }, []);

  const handleStop = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
    }
  }, []);

  // Cleanup abort controller on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (!sessionId) {
      setMessages([]);
      locallyStartedSession.current = null;
      return;
    }
    if (locallyStartedSession.current === sessionId) return;
    let cancelled = false;
    (async () => {
      try {
        const turns = await getSessionHistory(sessionId, userId);
        if (cancelled) return;
        const msgs: ChatMessage[] = turns.map((t, i) => ({
          id: `${idPrefix}-hist-${i}`,
          role: t.role as 'user' | 'assistant',
          content: t.content,
          modelId: t.model_id || undefined,
        }));
        setMessages(msgs);
      } catch {
        setMessages([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId, userId, idPrefix]);

  const sendMessage = useCallback(
    async (queryText: string, options?: { enableThinking?: boolean }) => {
      const q = queryText.trim();
      if (!q || isLoading) return;

      const effectiveThinking = options?.enableThinking ?? deepThinkEnabled;

      const userMsg: ChatMessage = {
        id: `${idPrefix}-${Date.now()}-u`,
        role: 'user',
        content: q,
      };
      const assistantMsgId = `${idPrefix}-${Date.now()}-a`;
      const assistantMsg: ChatMessage = {
        id: assistantMsgId,
        role: 'assistant',
        content: '',
        isStreaming: true,
        modelId: modelId || undefined,
        citations: [],
        banners: [],
        suggestions: [],
        thinking: null,
        isThinking: effectiveThinking,
        thinkingSuggestion: null,
      };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setInput('');
      setIsLoading(true);

      const ctrl = new AbortController();
      abortRef.current = ctrl;
      let activeSessionId = sessionId;

      try {
        await streamChat(
          q,
          activeSessionId,
          userId,
          {
            clearanceLevel,
            departmentId: selectedDept !== 'ALL' ? selectedDept : null,
            modelId: modelId || null,
            enableThinking: effectiveThinking,
          },
          {
            onStart: (sid, returnedModelId) => {
              if (!activeSessionId) {
                activeSessionId = sid;
                locallyStartedSession.current = sid;
                onSessionCreated(sid);
              }
              if (returnedModelId) {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantMsgId ? { ...m, modelId: returnedModelId } : m,
                  ),
                );
              }
            },
            onStatus: (event) => {
              setMessages((prev) =>
                prev.map((m) => {
                  if (m.id !== assistantMsgId) return m;
                  const existing = m.operationalEvents || [];
                  const idx = existing.findIndex((e) => e.sequence === event.sequence);
                  const updated =
                    idx !== -1
                      ? existing.map((e, i) => (i === idx ? event : e))
                      : [...existing, event];
                  return { ...m, operationalEvents: updated };
                }),
              );
            },
            onThinking: (chunk) => {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? {
                        ...m,
                        thinking: (m.thinking || '') + chunk,
                        isThinking: true,
                      }
                    : m,
                ),
              );
            },
            onToken: (text) => {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? {
                        ...m,
                        content: m.content + text,
                        isThinking: false,
                      }
                    : m,
                ),
              );
            },
            onCitations: (citations) => {
              if (!citationEnabled) return;
              setMessages((prev) =>
                prev.map((m) => (m.id === assistantMsgId ? { ...m, citations } : m)),
              );
            },
            onBanners: (banners) => {
              setMessages((prev) =>
                prev.map((m) => (m.id === assistantMsgId ? { ...m, banners } : m)),
              );
            },
            onSuggestions: (suggestions) => {
              setMessages((prev) =>
                prev.map((m) => (m.id === assistantMsgId ? { ...m, suggestions } : m)),
              );
            },
            onPlan: (plan) => {
              setMessages((prev) =>
                prev.map((m) => (m.id === assistantMsgId ? { ...m, plan } : m)),
              );
            },
            onCalculations: (calcs) => {
              setMessages((prev) =>
                prev.map((m) => (m.id === assistantMsgId ? { ...m, computationResults: calcs } : m)),
              );
            },
            onResearch: (res) => {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? { ...m, researchSummary: res.summary, subagents: res.subagents }
                    : m,
                ),
              );
            },
            onTrail: (trail) => {
              setMessages((prev) =>
                prev.map((m) => {
                  if (m.id !== assistantMsgId) return m;
                  return {
                    ...m,
                    stateHistory: trail.state_history,
                    perStageLatency: trail.per_stage_latency,
                    abstentionReason: trail.abstention_reason,
                    latencyMs: trail.latency_ms,
                    plan: trail.plan ?? m.plan,
                    computationResults: trail.computation_results ?? m.computationResults,
                    researchSummary: trail.research_summary ?? m.researchSummary,
                    subagents: trail.subagents ?? m.subagents,
                    thinking: trail.thinking ?? m.thinking,
                    thinkingSuggestion: trail.thinking_suggestion ?? m.thinkingSuggestion,
                  };
                }),
              );
            },
            onDone: (meta) => {
              setMessages((prev) => {
                const updated = prev.map((m) =>
                  m.id === assistantMsgId
                    ? {
                        ...m,
                        isStreaming: false,
                        isThinking: false,
                        isNoAnswer: meta.is_no_answer,
                        isHighRisk: meta.is_high_risk,
                        latencyMs: meta.latency_ms,
                        stateHistory: meta.state_history || m.stateHistory,
                        perStageLatency: meta.per_stage_latency || m.perStageLatency,
                        abstentionReason: meta.abstention_reason || m.abstentionReason,
                        plan: meta.plan ?? m.plan,
                        computationResults: meta.computation_results ?? m.computationResults,
                        researchSummary: meta.research_summary ?? m.researchSummary,
                        subagents: meta.subagents ?? m.subagents,
                        thinking: meta.thinking ?? m.thinking,
                        thinkingSuggestion: meta.thinking_suggestion ?? m.thinkingSuggestion,
                      }
                    : m,
                );
                const finalMsg = updated.find((m) => m.id === assistantMsgId);
                if (finalMsg) {
                  setLastAnswer((prev) => ({ text: finalMsg.content, seq: prev.seq + 1 }));
                }
                return updated;
              });
            },
            onError: (err) => {
              if (ctrl.signal.aborted) return;
              const errorObj: ChatErrorDetails =
                typeof err === 'string'
                  ? {
                      title: 'Inference Connection Error',
                      message: err,
                      category: err.toLowerCase().includes('gemini') ? 'gemini_key_missing' : 'general',
                      suggestedAction: 'retry',
                      raw: err,
                    }
                  : err;

              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? { ...m, content: '', isStreaming: false, error: errorObj }
                    : m,
                ),
              );
            },
          },
          ctrl.signal,
        );
      } catch (err: unknown) {
        const isAbort = ctrl.signal.aborted || (err instanceof Error && err.name === 'AbortError');
        if (!isAbort) {
          const errMessage = err instanceof Error ? err.message : String(err);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? {
                    ...m,
                    content: '',
                    isStreaming: false,
                    error: {
                      title: 'Unexpected Client Error',
                      message: errMessage,
                      category: 'general',
                      suggestedAction: 'retry',
                      raw: String(err),
                    },
                  }
                : m,
            ),
          );
        }
      } finally {
        if (ctrl.signal.aborted) {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantMsgId
                ? {
                    ...m,
                    content: m.content?.trim() ? m.content : 'Generation stopped.',
                    isStreaming: false,
                    isThinking: false,
                  }
                : m,
            ),
          );
        }
        setIsLoading(false);
        abortRef.current = null;
      }
    },
    [isLoading, sessionId, userId, clearanceLevel, selectedDept, modelId, onSessionCreated, idPrefix, citationEnabled, deepThinkEnabled],
  );

  const handleRetry = useCallback(
    (failedMsg: ChatMessage) => {
      const idx = messages.findIndex((m) => m.id === failedMsg.id);
      let queryText = '';
      if (idx !== -1) {
        for (let i = idx - 1; i >= 0; i--) {
          if (messages[i].role === 'user') {
            queryText = messages[i].content;
            break;
          }
        }
      }
      if (!queryText) {
        const lastUser = [...messages].reverse().find((m) => m.role === 'user');
        if (lastUser) queryText = lastUser.content;
      }
      if (!queryText) return;

      setMessages((prev) => prev.filter((m) => m.id !== failedMsg.id));
      void sendMessage(queryText);
    },
    [messages, sendMessage],
  );

  const voice = useVoiceConversation({
    onTranscript: (text) => {
      setInput(text);
      void sendMessage(text);
    },
    onInterim: setInput,
    isBusy: isLoading,
    answer: lastAnswer,
  });

  const composerPlaceholder =
    voice.phase === 'listening'
      ? 'Listening… speak your administrative question'
      : voice.phase === 'transcribing'
      ? 'Transcribing speech…'
      : 'Ask about Uttarakhand Government Orders, circulars, or statutory rules…';

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (isLoading) {
        handleStop();
      } else {
        sendMessage(input);
      }
    }
  };

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).then(() => {
      toast.success('Answer copied to clipboard');
    });
  };

  const hasMessages = messages.length > 0;
  const currentDeptLabel =
    selectedDept === 'ALL'
      ? 'All Departments'
      : departments.find((d) => d.id === selectedDept)?.label || selectedDept;
  const latestCitations = [...messages]
    .reverse()
    .find((message) => message.role === 'assistant' && message.citations?.length)?.citations ?? [];

  return (
    <div className="flex flex-col h-full bg-white dark:bg-[#0c111c] overflow-hidden relative transition-colors">
      {/* ── EMPTY / WELCOME STATE ────────────────────────────────────── */}
      {!hasMessages ? (
        <div className="flex-1 overflow-y-auto px-4 sm:px-8 py-8 sm:py-12 flex flex-col items-center min-h-0 bg-[radial-gradient(ellipse_at_top,#faf7ff_0%,#fff_50%)] dark:bg-[radial-gradient(ellipse_at_top,#1a1429_0%,#0c111c_55%)]">
          <div className="max-w-3xl w-full flex flex-col items-center text-center my-auto py-2">
            {/* Signature Sovereign 3D Orb */}
            <div className="relative mb-5 flex items-center justify-center group">
              <div className="absolute -inset-2.5 rounded-full bg-purple-500/20 dark:bg-purple-600/30 blur-lg transition-all group-hover:scale-110" />
              <div className="sovereign-orb relative shadow-xl shadow-purple-500/25" />
            </div>

            {/* Greetings & Header */}
            <h1 className="text-2xl sm:text-3xl lg:text-4xl font-semibold text-slate-900 dark:text-slate-100 tracking-tight mb-2">
              Welcome, {userName || 'Administrative Officer'}
            </h1>
            <h2 className="text-sm sm:text-base lg:text-lg font-normal text-slate-600 dark:text-slate-400 mb-6 sm:mb-8">
              Uttarakhand State Administrative <span className="text-purple-600 dark:text-purple-400 font-semibold">Intelligence</span>
            </h2>

            {/* Main Floating Search / Prompt Composer Card */}
            <div className="w-full bg-white dark:bg-[#111726] rounded-2xl border border-slate-200 dark:border-slate-800 shadow-xl shadow-slate-200/50 dark:shadow-purple-950/20 p-4 sm:p-5 text-left transition-all focus-within:border-purple-400 dark:focus-within:border-purple-600 focus-within:ring-2 focus-within:ring-purple-400/20 mb-8">
              <div className="flex items-start gap-3">
                <Sparkles className="w-4 h-4 text-purple-600 dark:text-purple-400 mt-1 shrink-0" />
                <textarea
                  rows={2}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={composerPlaceholder}
                  className="w-full bg-transparent text-sm text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 outline-none resize-none pt-0.5 leading-relaxed"
                />
              </div>

              {/* Bottom Actions Toolbar inside prompt card */}
              <div className="flex flex-wrap items-center justify-between gap-2.5 mt-3.5 pt-3 border-t border-slate-100 dark:border-slate-800/80">
                {/* Left side: Attach + Department filter + Deep Think */}
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    onClick={onOpenUpload}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#131926] text-xs font-semibold text-slate-700 dark:text-slate-300 hover:border-slate-300 dark:hover:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors shadow-2xs shrink-0"
                    title="Upload official order PDF for verification"
                  >
                    <Paperclip className="w-3.5 h-3.5 text-slate-400" />
                    <span>Attach Order</span>
                  </button>

                  <div className="relative shrink-0">
                    <button
                      type="button"
                      onClick={() => setDeptMenuOpen(!deptMenuOpen)}
                      className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#131926] text-xs font-semibold text-slate-700 dark:text-slate-300 hover:border-slate-300 dark:hover:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors shadow-2xs"
                    >
                      <span className="max-w-[110px] sm:max-w-[140px] truncate">{currentDeptLabel}</span>
                      <ChevronDown className="w-3 h-3 text-slate-400 shrink-0" />
                    </button>

                    {deptMenuOpen && (
                      <div className="absolute left-0 bottom-full mb-1 w-64 bg-white dark:bg-[#131926] rounded-2xl border border-slate-200 dark:border-slate-800 shadow-xl py-1.5 z-30 max-h-56 overflow-y-auto">
                        <div className="px-3.5 py-1 text-[10px] uppercase font-semibold text-slate-400 dark:text-slate-500">
                          Scope Department
                        </div>
                        <button
                          type="button"
                          onClick={() => {
                            setSelectedDept('ALL');
                            setDeptMenuOpen(false);
                          }}
                          className="w-full text-left px-3.5 py-1.5 text-xs text-slate-700 dark:text-slate-300 hover:bg-purple-50 dark:hover:bg-purple-950/40 hover:text-purple-700 dark:hover:text-purple-300 flex items-center justify-between"
                        >
                          <span>All Departments</span>
                          {selectedDept === 'ALL' && <Check className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400" />}
                        </button>
                        {departments.map((d) => (
                          <button
                            key={d.id}
                            type="button"
                            onClick={() => {
                              setSelectedDept(d.id);
                              setDeptMenuOpen(false);
                            }}
                            className="w-full text-left px-3.5 py-1.5 text-xs text-slate-700 dark:text-slate-300 hover:bg-purple-50 dark:hover:bg-purple-950/40 hover:text-purple-700 dark:hover:text-purple-300 flex items-center justify-between"
                          >
                            <span className="truncate pr-2">{d.label}</span>
                            {selectedDept === d.id && <Check className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400 shrink-0" />}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Deep Think Mode Toggle Button */}
                  <button
                    type="button"
                    onClick={handleToggleDeepThink}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-semibold transition-all shadow-2xs shrink-0 ${
                      deepThinkEnabled
                        ? 'border-purple-500/60 bg-purple-50 text-purple-700 dark:bg-purple-950/50 dark:border-purple-500/70 dark:text-purple-300 shadow-xs ring-1 ring-purple-400/30'
                        : 'border-slate-200 dark:border-slate-800 bg-white dark:bg-[#131926] text-slate-700 dark:text-slate-300 hover:border-slate-300 dark:hover:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800'
                    }`}
                    title={
                      deepThinkEnabled
                        ? 'Deep Think reasoning mode active (unrolls multi-step chain-of-thought)'
                        : 'Enable Deep Think reasoning mode for complex multi-hop queries and calculations'
                    }
                  >
                    <Brain
                      className={`w-3.5 h-3.5 ${
                        deepThinkEnabled ? 'text-purple-600 dark:text-purple-400 animate-pulse' : 'text-slate-400'
                      }`}
                    />
                    <span>Deep Think</span>
                    {deepThinkEnabled && (
                      <span className="w-1.5 h-1.5 rounded-full bg-purple-500 animate-ping" />
                    )}
                  </button>
                </div>

                {/* Right side: Citation Toggle + Voice + Submit/Stop */}
                <div className="flex items-center gap-3 ml-auto sm:ml-0 shrink-0">
                  {/* Citation Switch */}
                  <label className="flex items-center gap-1.5 cursor-pointer select-none">
                    <div
                      onClick={() => setCitationEnabled(!citationEnabled)}
                      className={`w-8 h-4.5 rounded-full transition-colors relative flex items-center p-0.5 ${
                        citationEnabled ? 'bg-purple-600' : 'bg-slate-200 dark:bg-slate-700'
                      }`}
                    >
                      <div
                        className={`w-3.5 h-3.5 rounded-full bg-white shadow-xs transition-transform ${
                          citationEnabled ? 'translate-x-3.5' : 'translate-x-0'
                        }`}
                      />
                    </div>
                    <span className="text-xs text-slate-600 dark:text-slate-400 font-medium">Citation</span>
                  </label>

                  {/* Voice Controls */}
                  <VoiceControls voice={voice} hasAnswer={!!lastAnswer.text} />

                  {/* Submit / Stop Button */}
                  {isLoading ? (
                    <button
                      type="button"
                      onClick={handleStop}
                      className="p-2 rounded-xl bg-red-600 hover:bg-red-700 active:scale-95 text-white transition-all shadow-xs animate-in fade-in"
                      title="Stop generation (Click to cancel)"
                    >
                      <Square className="w-4 h-4 fill-current" />
                    </button>
                  ) : (
                    <button
                      type="button"
                      onClick={() => sendMessage(input)}
                      disabled={!input.trim()}
                      className="p-2 rounded-xl bg-slate-900 dark:bg-purple-600 text-white hover:bg-slate-800 dark:hover:bg-purple-500 active:scale-95 disabled:bg-slate-200 dark:disabled:bg-slate-800 disabled:text-slate-400 disabled:cursor-not-allowed transition-all shadow-xs"
                      title="Send query (Enter)"
                    >
                      <ArrowUp className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </div>
            </div>

            {/* Example Prompts Header */}
            <div className="w-full text-left mb-3">
              <p className="text-[11px] font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider">
                EXPLORE VERIFIED UTTARAKHAND PUBLIC RECORDS
              </p>
            </div>

            {/* 4 Cards Grid - 2 Columns on Tablet/Desktop, comfortable padding & min-height */}
            <div className="w-full grid grid-cols-1 sm:grid-cols-2 gap-3.5 text-left">
              {EXAMPLE_CARDS.map((card, idx) => {
                const IconComponent = card.icon;
                return (
                  <div
                    key={idx}
                    onClick={() => sendMessage(card.query)}
                    className="group bg-white/80 dark:bg-[#111726]/80 hover:bg-white dark:hover:bg-[#141b2c] hover:-translate-y-0.5 hover:shadow-md hover:border-purple-300 dark:hover:border-purple-700/60 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-4 transition-all cursor-pointer flex flex-col justify-between min-h-[112px]"
                  >
                    <div>
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-[10px] font-bold text-purple-700 dark:text-purple-400 uppercase tracking-wider bg-purple-50 dark:bg-purple-950/50 px-2 py-0.5 rounded-md border border-purple-100 dark:border-purple-900/50">
                          {card.dept}
                        </span>
                        <div className="text-slate-400 group-hover:text-purple-600 dark:group-hover:text-purple-400 transition-colors">
                          <IconComponent className="w-4 h-4" />
                        </div>
                      </div>
                      <p className="text-xs sm:text-[13px] text-slate-800 dark:text-slate-200 leading-snug font-medium group-hover:text-purple-950 dark:group-hover:text-white transition-colors">
                        {card.title}
                      </p>
                    </div>
                    <div className="flex items-center justify-between text-slate-400 group-hover:text-purple-600 dark:group-hover:text-purple-400 pt-2.5 mt-2 border-t border-slate-100 dark:border-slate-800/60 text-[11px] font-medium">
                      <span className="text-slate-500 dark:text-slate-400 group-hover:text-slate-700 dark:group-hover:text-slate-300 transition-colors">
                        Query record
                      </span>
                      <ChevronRight className="w-3.5 h-3.5 transform group-hover:translate-x-0.5 transition-transform" />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      ) : (
        /* ── ACTIVE CHAT MESSAGES VIEW ─────────────────────────────── */
        <div className="flex-1 flex min-h-0 bg-slate-50/50 dark:bg-[#090d16]">
          <div className="flex-1 overflow-y-auto px-4 sm:px-8 py-8 space-y-6 min-w-0">
            <div className="max-w-4xl w-full mx-auto space-y-6">
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
                >
                  {/* User Message */}
                  {msg.role === 'user' ? (
                    <div className="bg-slate-900 dark:bg-[#1a2336] text-white dark:text-slate-100 border border-transparent dark:border-slate-700/60 rounded-2xl rounded-tr-md px-5 py-3 text-sm max-w-xl shadow-xs leading-relaxed whitespace-pre-wrap">
                      {msg.content}
                    </div>
                  ) : (
                    /* Assistant Message */
                    <div className="w-full max-w-3xl bg-white dark:bg-[#111726] rounded-2xl border border-slate-200/80 dark:border-slate-800 p-5 shadow-xs">
                      {/* Assistant Header Row */}
                      <div className="flex items-center gap-2 mb-3 flex-wrap">
                        <div className="w-6 h-6 rounded-lg bg-gradient-to-tr from-purple-600 to-indigo-600 flex items-center justify-center text-white shadow-xs">
                          <Sparkles className="w-3.5 h-3.5" />
                        </div>
                        <span className="text-xs font-semibold text-slate-900 dark:text-slate-100">ADAM Sovereign</span>
                        <span className="text-[10px] text-slate-400 dark:text-slate-500">• Governed Synthesis</span>

                        {msg.modelId?.toLowerCase().includes('gemini') ? (
                          <span className="ml-auto inline-flex items-center gap-1.5 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800 shadow-xs">
                            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse" />
                            ☁️ Google Gemini
                          </span>
                        ) : msg.modelId ? (
                          <span className="ml-auto inline-flex items-center gap-1.5 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-50 dark:bg-emerald-950/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800 shadow-xs">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                            ⚡ {msg.modelId}
                          </span>
                        ) : null}

                        {/* Copy Answer Button */}
                        {msg.content && !msg.isStreaming && (
                          <button
                            type="button"
                            onClick={() => copyToClipboard(msg.content)}
                            className="p-1 rounded-md text-slate-400 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors ml-1"
                            title="Copy answer"
                          >
                            <Copy className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>

                      {/* Operational Transparency Execution Status */}
                      <ExecutionStatus
                        events={msg.operationalEvents}
                        stateHistory={msg.stateHistory}
                        perStageLatency={msg.perStageLatency}
                        abstentionReason={msg.abstentionReason}
                        latencyMs={msg.latencyMs}
                        isStreaming={msg.isStreaming}
                        hasError={!!msg.error}
                        isNoAnswer={msg.isNoAnswer}
                        plan={msg.plan}
                        computationResults={msg.computationResults}
                        researchSummary={msg.researchSummary}
                        subagents={msg.subagents}
                      />

                      {/* Deep Think Thoughts Section */}
                      <ThoughtAccordion
                        thinking={msg.thinking}
                        isThinking={msg.isThinking}
                      />

                      {msg.error ? (
                        <AiErrorCard
                          error={msg.error}
                          onRetry={() => handleRetry(msg)}
                          onOpenApiKeyModal={onOpenApiKeyModal}
                          onOpenModelSelector={onOpenModelSelector}
                        />
                      ) : (
                        <div className="text-sm text-slate-800 dark:text-slate-200 leading-relaxed">
                          <Markdown text={msg.content} />
                          {msg.isStreaming && (
                            <span className="inline-block w-1.5 h-4 ml-1 bg-purple-600 dark:bg-purple-400 animate-pulse rounded-full align-middle" />
                          )}
                        </div>
                      )}

                      {/* Precedent / Amendment Notice Banners */}
                      {msg.banners && msg.banners.length > 0 && (
                        <div className="mt-3">
                          {msg.banners.map((b, i) => (
                            <CurrencyBanner key={i} message={b} />
                          ))}
                        </div>
                      )}

                      {/* Citation Cards */}
                      {msg.citations && msg.citations.length > 0 && (
                        <div className="mt-4 pt-3 border-t border-slate-100 dark:border-slate-800">
                          <p className="text-[11px] font-semibold text-slate-400 dark:text-slate-500 uppercase tracking-wider mb-2">
                            Sources &amp; Precedents
                          </p>
                          {msg.citations.map((c, i) => (
                            <CitationCard key={i} citation={c} index={i} />
                          ))}
                        </div>
                      )}

                      {/* Search Suggestions if No Answer */}
                      {msg.suggestions && msg.suggestions.length > 0 && (
                        <div className="mt-3 p-3 rounded-xl bg-purple-50/70 dark:bg-purple-950/30 border border-purple-100 dark:border-purple-800 text-xs text-purple-900 dark:text-purple-300">
                          <p className="font-semibold mb-1">Search suggestions:</p>
                          <ul className="list-disc list-inside space-y-0.5 text-purple-800 dark:text-purple-300">
                            {msg.suggestions.map((s, i) => (
                              <li key={i}>{s}</li>
                            ))}
                          </ul>
                        </div>
                      )}

                      {/* Autonomous Deep Think Recommendation Banner */}
                      {msg.thinkingSuggestion?.suggested && !msg.isStreaming && (
                        <div className="mt-3.5 p-3.5 rounded-xl bg-purple-50/80 dark:bg-purple-950/40 border border-purple-200 dark:border-purple-800/70 flex items-start justify-between gap-3 text-left shadow-xs">
                          <div className="flex items-start gap-2.5 min-w-0">
                            <div className="w-7 h-7 rounded-lg bg-purple-100 dark:bg-purple-900/60 flex items-center justify-center shrink-0 text-purple-700 dark:text-purple-300 mt-0.5">
                              <Brain className="w-4 h-4" />
                            </div>
                            <div className="min-w-0">
                              <div className="flex items-center gap-2 flex-wrap">
                                <p className="text-xs font-semibold text-purple-900 dark:text-purple-200">
                                  Deep Think Recommended
                                </p>
                                <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-purple-200/60 dark:bg-purple-800/60 text-purple-800 dark:text-purple-300">
                                  Complex Reasoning Detected
                                </span>
                              </div>
                              <p className="text-xs text-purple-700 dark:text-purple-300 mt-1 leading-relaxed">
                                {msg.thinkingSuggestion.reason}
                              </p>
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={() => {
                              setDeepThinkEnabled(true);
                              const targetPrompt = msg.thinkingSuggestion?.prompt;
                              if (targetPrompt) {
                                sendMessage(targetPrompt, { enableThinking: true });
                              }
                            }}
                            className="shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-700 active:scale-[0.98] text-white text-xs font-semibold shadow-xs transition-all"
                          >
                            <Zap className="w-3.5 h-3.5" />
                            <span>Re-prompt with Deep Think</span>
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
              <div ref={scrollRef} />
            </div>
          </div>

          {/* Right Sidebar: Sources & Suggested Follow-ups */}
          <aside className="hidden xl:flex w-[300px] shrink-0 border-l border-slate-200/80 dark:border-slate-800 bg-white dark:bg-[#0c111c] p-4 flex-col gap-4 overflow-y-auto transition-colors">
            <section className="rounded-2xl border border-slate-200/80 dark:border-slate-800 p-4 bg-white dark:bg-[#111726]">
              <div className="flex items-center gap-2 mb-3">
                <Link2 className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-900 dark:text-slate-100">Verified Sources</h2>
              </div>
              {latestCitations.length ? (
                <div className="space-y-2">
                  {latestCitations.slice(0, 3).map((citation, index) => (
                    <a
                      key={`${citation.document_id || citation.document_title}-${index}`}
                      href={citation.source_url || citation.pdf_page_link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block rounded-xl bg-slate-50 dark:bg-[#161d2d] p-2.5 hover:bg-purple-50 dark:hover:bg-purple-950/40 border border-slate-100 dark:border-slate-800 transition-colors"
                    >
                      <p className="text-xs font-semibold text-slate-800 dark:text-slate-200 line-clamp-2">{citation.document_title}</p>
                      <p className="mt-1 text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500 font-mono">
                        {citation.go_number || `Page ${citation.page}`}
                      </p>
                    </a>
                  ))}
                </div>
              ) : (
                <div className="py-4 text-center">
                  <div className="mx-auto mb-2 flex h-9 w-9 items-center justify-center rounded-xl bg-purple-50 dark:bg-purple-950/60 text-purple-600 dark:text-purple-400">
                    <FileText className="h-4 w-4" />
                  </div>
                  <p className="text-xs leading-relaxed text-slate-500 dark:text-slate-400">Sources from verified government records will appear here.</p>
                  <button
                    type="button"
                    onClick={onOpenUpload}
                    className="mt-3 text-xs font-semibold text-purple-700 dark:text-purple-400 hover:underline"
                  >
                    Add an order
                  </button>
                </div>
              )}
            </section>

            <section className="rounded-2xl border border-slate-200/80 dark:border-slate-800 p-4 bg-white dark:bg-[#111726]">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-900 dark:text-slate-100 mb-3">Suggested follow-ups</h2>
              <div className="space-y-2">
                {[
                  'Show the source document for this answer.',
                  'Which department issued this order?',
                  'Are there any amendments or superseding orders?',
                ].map((question) => (
                  <button
                    key={question}
                    type="button"
                    onClick={() => sendMessage(question)}
                    className="w-full rounded-xl bg-slate-50 dark:bg-[#161d2d] px-3 py-2 text-left text-xs leading-snug text-slate-700 dark:text-slate-300 hover:bg-purple-50 dark:hover:bg-purple-950/40 hover:text-purple-700 dark:hover:text-purple-300 border border-slate-100 dark:border-slate-800 transition-colors"
                  >
                    {question}
                  </button>
                ))}
              </div>
            </section>

            <p className="px-1 text-[10px] leading-relaxed text-slate-400 dark:text-slate-500">
              Responses are sovereignly grounded only in approved Uttarakhand administrative records.
            </p>
          </aside>
        </div>
      )}

      {/* ── DOCKED BOTTOM INPUT (ONLY WHEN CHAT ACTIVE) ─────────────── */}
      {hasMessages && (
        <div className="p-3 sm:p-4 border-t border-slate-200/80 dark:border-slate-800 bg-white dark:bg-[#0c111c] transition-colors">
          <div className="max-w-3xl w-full mx-auto bg-white dark:bg-[#111726] rounded-2xl border border-slate-200 dark:border-slate-800 shadow-md p-3 focus-within:border-purple-400 dark:focus-within:border-purple-600 focus-within:shadow-lg transition-all">
            <div className="flex items-center gap-2.5">
              <Sparkles className="w-4 h-4 text-purple-600 dark:text-purple-400 shrink-0" />
              <textarea
                rows={1}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={composerPlaceholder}
                className="w-full bg-transparent text-sm text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 outline-none resize-none pt-0.5"
              />
            </div>

            <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-100 dark:border-slate-800/80 flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={onOpenUpload}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-slate-200 dark:border-slate-800 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                  title="Upload order PDF"
                >
                  <Paperclip className="w-3 h-3 text-slate-400" />
                  <span>Attach</span>
                </button>

                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setDeptMenuOpen(!deptMenuOpen)}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-slate-200 dark:border-slate-800 text-xs font-semibold text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
                  >
                    <span className="max-w-[120px] truncate">{currentDeptLabel}</span>
                    <ChevronDown className="w-3 h-3 text-slate-400" />
                  </button>

                  {deptMenuOpen && (
                    <div className="absolute left-0 bottom-full mb-1 w-60 bg-white dark:bg-[#131926] rounded-xl border border-slate-200 dark:border-slate-800 shadow-xl py-1 z-30 max-h-52 overflow-y-auto">
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedDept('ALL');
                          setDeptMenuOpen(false);
                        }}
                        className="w-full text-left px-3 py-1.5 text-xs text-slate-700 dark:text-slate-300 hover:bg-purple-50 dark:hover:bg-purple-950/40 flex items-center justify-between"
                      >
                        <span>All Departments</span>
                        {selectedDept === 'ALL' && <Check className="w-3 h-3 text-purple-600 dark:text-purple-400" />}
                      </button>
                      {departments.map((d) => (
                        <button
                          key={d.id}
                          type="button"
                          onClick={() => {
                            setSelectedDept(d.id);
                            setDeptMenuOpen(false);
                          }}
                          className="w-full text-left px-3 py-1.5 text-xs text-slate-700 dark:text-slate-300 hover:bg-purple-50 dark:hover:bg-purple-950/40 flex items-center justify-between"
                        >
                          <span className="truncate pr-2">{d.label}</span>
                          {selectedDept === d.id && <Check className="w-3 h-3 text-purple-600 dark:text-purple-400 shrink-0" />}
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                {/* Deep Think Mode Toggle Button */}
                <button
                  type="button"
                  onClick={handleToggleDeepThink}
                  className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-semibold transition-all ${
                    deepThinkEnabled
                      ? 'border-purple-500/60 bg-purple-50 text-purple-700 dark:bg-purple-950/50 dark:border-purple-500/70 dark:text-purple-300 shadow-xs ring-1 ring-purple-400/30'
                      : 'border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800'
                  }`}
                  title={
                    deepThinkEnabled
                      ? 'Deep Think reasoning mode active'
                      : 'Enable Deep Think reasoning mode'
                  }
                >
                  <Brain
                    className={`w-3 h-3 ${
                      deepThinkEnabled ? 'text-purple-600 dark:text-purple-400 animate-pulse' : 'text-slate-400'
                    }`}
                  />
                  <span>Deep Think</span>
                  {deepThinkEnabled && (
                    <span className="w-1.5 h-1.5 rounded-full bg-purple-500 animate-ping" />
                  )}
                </button>
              </div>

              <div className="flex items-center gap-2.5">
                <label className="flex items-center gap-1.5 cursor-pointer select-none">
                  <div
                    onClick={() => setCitationEnabled(!citationEnabled)}
                    className={`w-7 h-4 rounded-full transition-colors relative flex items-center p-0.5 ${
                      citationEnabled ? 'bg-purple-600' : 'bg-slate-200 dark:bg-slate-700'
                    }`}
                  >
                    <div
                      className={`w-3 h-3 rounded-full bg-white shadow-xs transition-transform ${
                        citationEnabled ? 'translate-x-3' : 'translate-x-0'
                      }`}
                    />
                  </div>
                  <span className="text-xs text-slate-600 dark:text-slate-400 font-medium">Citation</span>
                </label>

                <VoiceControls voice={voice} hasAnswer={!!lastAnswer.text} />

                {isLoading ? (
                  <button
                    type="button"
                    onClick={handleStop}
                    className="p-1.5 rounded-lg bg-red-600 hover:bg-red-700 active:scale-95 text-white transition-all shadow-xs animate-in fade-in"
                    title="Stop generation (Click to cancel)"
                  >
                    <Square className="w-3.5 h-3.5 fill-current" />
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => sendMessage(input)}
                    disabled={!input.trim()}
                    className="p-1.5 rounded-lg bg-slate-900 dark:bg-purple-600 text-white hover:bg-slate-800 dark:hover:bg-purple-500 active:scale-95 disabled:bg-slate-200 dark:disabled:bg-slate-800 disabled:text-slate-400 disabled:cursor-not-allowed transition-all"
                    title="Send query (Enter)"
                  >
                    <ArrowUp className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
