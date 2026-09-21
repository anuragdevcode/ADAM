'use client';

import { useState, useRef, useEffect, useCallback, useId } from 'react';
import { streamChat, getSessionHistory } from '@/lib/api';
import type { ChatMessage, DepartmentItem } from '@/lib/types';
import CitationCard from './CitationCard';
import CurrencyBanner from './CurrencyBanner';
import VoiceControls from './VoiceControls';
import { useVoiceConversation, type VoiceAnswer } from '@/lib/useVoiceConversation';
import { Markdown } from '@/lib/markdown';
import {
  Sparkles,
  Paperclip,
  ChevronDown,
  ArrowUp,
  Check,
  ChevronRight,
  FileText,
  Link2,
  Banknote,
  Landmark,
  Clock,
  LifeBuoy,
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
      'What is the prescribed timeline for disposing of online land mutation and varasat applications?',
    icon: Landmark,
  },
  {
    title: 'Secretariat working hours and holiday schedule',
    dept: 'General Administration',
    query: 'What are the official working hours for the Uttarakhand Civil Secretariat?',
    icon: Clock,
  },
  {
    title: 'SDRF ex-gratia relief norms for loss of life',
    dept: 'Disaster Management',
    query: 'What ex-gratia relief is payable from the SDRF in case of loss of life?',
    icon: LifeBuoy,
  },
];

export default function ChatWindow({
  userId,
  sessionId,
  onSessionCreated,
  userName = 'Officer',
  clearanceLevel,
  modelId,
  departments,
  onOpenUpload,
}: ChatWindowProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  // Latest completed answer; `seq` bumps every turn so voice mode can tell a
  // new answer from a repeated one.
  const [lastAnswer, setLastAnswer] = useState<VoiceAnswer>({ text: '', seq: 0 });
  const [citationEnabled, setCitationEnabled] = useState(true);
  const [selectedDept, setSelectedDept] = useState<string>('ALL');
  const [deptMenuOpen, setDeptMenuOpen] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const locallyStartedSession = useRef<string | null>(null);
  const idPrefix = useId();

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
    async (queryText: string) => {
      const q = queryText.trim();
      if (!q || isLoading) return;

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
            onToken: (text) => {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId ? { ...m, content: m.content + text } : m,
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
            onDone: (meta) => {
              setMessages((prev) => {
                const updated = prev.map((m) =>
                  m.id === assistantMsgId
                    ? {
                        ...m,
                        isStreaming: false,
                        isNoAnswer: meta.is_no_answer,
                        isHighRisk: meta.is_high_risk,
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
            onError: (msg) => {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? { ...m, content: `Notice: ${msg}`, isStreaming: false }
                    : m,
                ),
              );
            },
          },
          ctrl.signal,
        );
      } finally {
        setIsLoading(false);
      }
    },
    [isLoading, sessionId, userId, clearanceLevel, selectedDept, modelId, onSessionCreated, idPrefix, citationEnabled],
  );

  // Voice state lives here (not in VoiceControls) because the composer is
  // re-mounted when the layout switches from the empty state to the docked bar.
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
      ? 'Listening… speak your question'
      : voice.phase === 'transcribing'
      ? 'Transcribing…'
      : 'Ask about Uttarakhand Government Orders, circulars, or statutory rules…';

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
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
    <div className="flex flex-col h-full bg-white overflow-hidden relative">
      {/* ── EMPTY / WELCOME STATE ────────────────────────────────────── */}
      {!hasMessages ? (
        <div className="flex-1 overflow-y-auto px-5 sm:px-8 py-10 flex flex-col items-center justify-center min-h-0 bg-[radial-gradient(ellipse_at_top,#faf7ff_0%,#fff_48%)]">
          <div className="max-w-[860px] w-full flex flex-col items-center text-center my-auto">
            {/* 3D Purple Glowing Sphere */}
            <div className="purple-orb mb-5 shadow-2xl" />

            {/* Greetings */}
            <h1 className="text-3xl sm:text-4xl font-semibold text-[#1d2939] tracking-tight mb-2">
              Good Afternoon, {userName}
            </h1>
            <h2 className="text-xl sm:text-2xl font-normal text-gray-600 mb-8">
              What&apos;s on <span className="text-[#a855f7] font-medium">your mind?</span>
            </h2>

            {/* Main Floating Search / Prompt Card */}
            <div className="w-full bg-white rounded-2xl border border-[#e4e7ec] shadow-[0_12px_30px_rgba(16,24,40,0.06)] p-4 text-left transition-all focus-within:border-purple-300 focus-within:shadow-[0_12px_32px_rgba(124,58,237,0.12)] mb-8">
              <div className="flex items-start gap-2.5">
                <Sparkles className="w-4 h-4 text-gray-400 mt-1 shrink-0" />
                <textarea
                  rows={2}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={composerPlaceholder}
                  disabled={isLoading}
                  className="w-full bg-transparent text-sm text-gray-800 placeholder-gray-400 outline-none resize-none pt-0.5 leading-relaxed"
                />
              </div>

              {/* Bottom Actions Toolbar inside prompt card */}
              <div className="flex items-center justify-between mt-3 pt-2 border-t border-gray-50 flex-wrap gap-2">
                {/* Left side: Attach + Department filter */}
                <div className="flex items-center gap-2 relative">
                  <button
                    type="button"
                    onClick={onOpenUpload}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[#e4e7ec] text-xs font-medium text-gray-600 hover:border-gray-300 hover:bg-gray-50 transition-colors"
                    title="Upload official order PDF for verification"
                  >
                    <Paperclip className="w-3.5 h-3.5 text-gray-400" />
                    <span>Attach Order</span>
                  </button>

                  <div className="relative">
                    <button
                      type="button"
                      onClick={() => setDeptMenuOpen(!deptMenuOpen)}
                      className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-[#e4e7ec] text-xs font-medium text-gray-600 hover:border-gray-300 hover:bg-gray-50 transition-colors"
                    >
                      <span className="max-w-[130px] truncate">{currentDeptLabel}</span>
                      <ChevronDown className="w-3 h-3 text-gray-400 shrink-0" />
                    </button>

                    {deptMenuOpen && (
                      <div className="absolute left-0 bottom-full mb-1 w-64 bg-white rounded-2xl border border-gray-100 shadow-xl py-1.5 z-30 max-h-56 overflow-y-auto">
                        <div className="px-3 py-1 text-[10px] uppercase font-semibold text-gray-400">
                          Scope Department
                        </div>
                        <button
                          type="button"
                          onClick={() => {
                            setSelectedDept('ALL');
                            setDeptMenuOpen(false);
                          }}
                          className="w-full text-left px-3 py-1.5 text-xs text-gray-700 hover:bg-purple-50 hover:text-purple-700 flex items-center justify-between"
                        >
                          <span>All Departments</span>
                          {selectedDept === 'ALL' && <Check className="w-3 h-3 text-purple-600" />}
                        </button>
                        {departments.map((d) => (
                          <button
                            key={d.id}
                            type="button"
                            onClick={() => {
                              setSelectedDept(d.id);
                              setDeptMenuOpen(false);
                            }}
                            className="w-full text-left px-3 py-1.5 text-xs text-gray-700 hover:bg-purple-50 hover:text-purple-700 flex items-center justify-between"
                          >
                            <span className="truncate pr-2">{d.label}</span>
                            {selectedDept === d.id && <Check className="w-3 h-3 text-purple-600 shrink-0" />}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </div>

                {/* Right side: Citation Toggle + Voice + Submit */}
                <div className="flex items-center gap-3">
                  {/* Citation Switch */}
                  <label className="flex items-center gap-1.5 cursor-pointer select-none">
                    <div
                      onClick={() => setCitationEnabled(!citationEnabled)}
                      className={`w-8 h-4.5 rounded-full transition-colors relative flex items-center p-0.5 ${
                        citationEnabled ? 'bg-purple-600' : 'bg-gray-200'
                      }`}
                    >
                      <div
                        className={`w-3.5 h-3.5 rounded-full bg-white shadow-xs transition-transform ${
                          citationEnabled ? 'translate-x-3.5' : 'translate-x-0'
                        }`}
                      />
                    </div>
                    <span className="text-xs text-gray-500 font-medium">Citation</span>
                  </label>

                  {/* Voice Controls */}
                  <VoiceControls voice={voice} hasAnswer={!!lastAnswer.text} />

                  {/* Submit Up-Arrow Button */}
                  <button
                    type="button"
                    onClick={() => sendMessage(input)}
                    disabled={isLoading || !input.trim()}
                    className="p-2 rounded-lg bg-[#292c33] text-white hover:bg-[#17191d] active:scale-95 disabled:bg-gray-200 disabled:text-gray-400 disabled:cursor-not-allowed transition-all shadow-sm"
                    title="Send query"
                  >
                    <ArrowUp className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>

            {/* Example Prompts Header */}
            <div className="w-full text-left mb-3">
              <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider">
                EXPLORE VERIFIED UTTARAKHAND PUBLIC RECORDS
              </p>
            </div>

            {/* 4 Cards Grid with Real GO Queries */}
            <div className="w-full grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-left">
              {EXAMPLE_CARDS.map((card, idx) => {
                const IconComponent = card.icon;
                return (
                  <div
                    key={idx}
                    onClick={() => sendMessage(card.query)}
                    className="bg-white/80 hover:bg-white hover:-translate-y-0.5 hover:shadow-md border border-[#eaecf0] rounded-xl p-4 transition-all cursor-pointer flex flex-col justify-between h-32 group"
                  >
                    <div>
                      <span className="text-[10px] font-semibold text-purple-700 uppercase tracking-wide block mb-1">
                        {card.dept}
                      </span>
                      <p className="text-xs text-gray-700 leading-snug font-medium group-hover:text-gray-900 transition-colors line-clamp-3">
                        {card.title}
                      </p>
                    </div>
                    <div className="flex items-center justify-between text-gray-400 group-hover:text-purple-600 pt-2 border-t border-gray-100/60">
                      <IconComponent className="w-4 h-4" />
                      <ChevronRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      ) : (
        /* ── ACTIVE CHAT MESSAGES VIEW ─────────────────────────────── */
        <div className="flex-1 flex min-h-0 bg-[#fcfcfd]">
        <div className="flex-1 overflow-y-auto px-5 sm:px-8 py-8 space-y-6 min-w-0">
          <div className="max-w-4xl w-full mx-auto space-y-6">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
              >
                {/* User Message */}
                {msg.role === 'user' ? (
                  <div className="bg-[#292c33] text-white rounded-2xl rounded-tr-md px-5 py-3 text-sm max-w-xl shadow-sm leading-relaxed whitespace-pre-wrap">
                    {msg.content}
                  </div>
                ) : (
                  /* Assistant Message */
                  <div className="w-full max-w-3xl bg-white rounded-2xl border border-[#eaecf0] p-5 shadow-[0_2px_8px_rgba(16,24,40,0.04)]">
                    <div className="flex items-center gap-2 mb-3 flex-wrap">
                      <div className="w-6 h-6 rounded-full bg-gradient-to-tr from-purple-500 to-indigo-600 flex items-center justify-center text-white shadow-xs">
                        <Sparkles className="w-3.5 h-3.5" />
                      </div>
                      <span className="text-xs font-semibold text-gray-800">ADAM Assistant</span>
                      <span className="text-[10px] text-gray-400">• Uttarakhand Records Repository</span>
                      {msg.modelId?.toLowerCase().includes('gemini') ? (
                        <span className="ml-auto inline-flex items-center gap-1.5 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-indigo-50 text-indigo-700 border border-indigo-200 shadow-xs">
                          <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse" />
                          ☁️ Google Gemini 3.6 Flash
                        </span>
                      ) : msg.modelId ? (
                        <span className="ml-auto inline-flex items-center gap-1.5 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 shadow-xs">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                          ⚡ {msg.modelId}
                        </span>
                      ) : null}
                    </div>

                    <div className="text-sm text-gray-800 leading-relaxed">
                      <Markdown text={msg.content} />
                      {msg.isStreaming && (
                        <span className="inline-block w-1.5 h-4 ml-1 bg-purple-600 animate-pulse rounded-full align-middle" />
                      )}
                    </div>

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
                      <div className="mt-4 pt-3 border-t border-gray-100">
                        <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider mb-2">
                          Sources &amp; Precedents
                        </p>
                        {msg.citations.map((c, i) => (
                          <CitationCard key={i} citation={c} index={i} />
                        ))}
                      </div>
                    )}

                    {/* Search Suggestions if No Answer */}
                    {msg.suggestions && msg.suggestions.length > 0 && (
                      <div className="mt-3 p-3 rounded-xl bg-purple-50/70 border border-purple-100 text-xs text-purple-900">
                        <p className="font-semibold mb-1">Search suggestions:</p>
                        <ul className="list-disc list-inside space-y-0.5 text-purple-800">
                          {msg.suggestions.map((s, i) => (
                            <li key={i}>{s}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
            <div ref={scrollRef} />
          </div>
        </div>
        <aside className="hidden xl:flex w-[300px] shrink-0 border-l border-[#eaecf0] bg-white p-4 flex-col gap-4 overflow-y-auto">
          <section className="rounded-xl border border-[#eaecf0] p-4">
            <div className="flex items-center gap-2 mb-3">
              <Link2 className="w-4 h-4 text-purple-600" />
              <h2 className="text-sm font-semibold text-[#1d2939]">Sources</h2>
            </div>
            {latestCitations.length ? (
              <div className="space-y-2">
                {latestCitations.slice(0, 3).map((citation, index) => (
                  <a
                    key={`${citation.document_id || citation.document_title}-${index}`}
                    href={citation.source_url || citation.pdf_page_link}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block rounded-lg bg-[#f8fafc] p-2.5 hover:bg-purple-50 transition-colors"
                  >
                    <p className="text-xs font-medium text-[#344054] line-clamp-2">{citation.document_title}</p>
                    <p className="mt-1 text-[10px] uppercase tracking-wide text-[#667085]">
                      {citation.go_number || `Page ${citation.page}`}
                    </p>
                  </a>
                ))}
              </div>
            ) : (
              <div className="py-3 text-center">
                <div className="mx-auto mb-2 flex h-9 w-9 items-center justify-center rounded-lg bg-purple-50">
                  <FileText className="h-4 w-4 text-purple-600" />
                </div>
                <p className="text-xs leading-relaxed text-[#667085]">Sources from verified records will appear here.</p>
                <button
                  type="button"
                  onClick={onOpenUpload}
                  className="mt-3 text-xs font-semibold text-purple-700 hover:text-purple-800"
                >
                  Add an order
                </button>
              </div>
            )}
          </section>
          <section className="rounded-xl border border-[#eaecf0] p-4">
            <h2 className="text-sm font-semibold text-[#1d2939]">Suggested follow-ups</h2>
            <div className="mt-3 space-y-2">
              {[
                'Show the source document for this answer.',
                'Which department issued this order?',
                'Are there any amendments or superseding orders?',
              ].map((question) => (
                <button
                  key={question}
                  type="button"
                  onClick={() => sendMessage(question)}
                  className="w-full rounded-lg bg-[#f8fafc] px-3 py-2 text-left text-xs leading-snug text-[#475467] hover:bg-purple-50 hover:text-purple-800 transition-colors"
                >
                  {question}
                </button>
              ))}
            </div>
          </section>
          <p className="px-1 text-[10px] leading-relaxed text-[#98a2b3]">
            Responses are grounded only in approved public records.
          </p>
        </aside>
        </div>
      )}

      {/* ── DOCKED BOTTOM INPUT (ONLY WHEN CHAT ACTIVE) ─────────────── */}
      {hasMessages && (
        <div className="p-3 sm:p-4 border-t border-[#eaecf0] bg-white">
          <div className="max-w-3xl w-full mx-auto bg-white rounded-2xl border border-[#dfe3ea] shadow-[0_8px_24px_rgba(16,24,40,0.06)] p-3 focus-within:border-purple-300 focus-within:shadow-[0_8px_26px_rgba(124,58,237,0.1)] transition-all">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-gray-400 shrink-0" />
              <textarea
                rows={1}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={composerPlaceholder}
                disabled={isLoading}
                className="w-full bg-transparent text-sm text-gray-800 placeholder-gray-400 outline-none resize-none pt-0.5"
              />
            </div>

            <div className="flex items-center justify-between mt-2 pt-2 border-t border-gray-50 flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={onOpenUpload}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-gray-200 text-xs font-medium text-gray-600 hover:bg-gray-50"
                  title="Upload order PDF"
                >
                  <Paperclip className="w-3 h-3 text-gray-400" />
                  <span>Attach</span>
                </button>
                <div className="relative">
                  <button
                    type="button"
                    onClick={() => setDeptMenuOpen(!deptMenuOpen)}
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg border border-gray-200 text-xs font-medium text-gray-600 hover:bg-gray-50"
                  >
                    <span className="max-w-[120px] truncate">{currentDeptLabel}</span>
                    <ChevronDown className="w-3 h-3 text-gray-400" />
                  </button>

                  {deptMenuOpen && (
                    <div className="absolute left-0 bottom-full mb-1 w-60 bg-white rounded-xl border border-gray-100 shadow-xl py-1 z-30 max-h-52 overflow-y-auto">
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedDept('ALL');
                          setDeptMenuOpen(false);
                        }}
                        className="w-full text-left px-3 py-1.5 text-xs text-gray-700 hover:bg-purple-50 flex items-center justify-between"
                      >
                        <span>All Departments</span>
                        {selectedDept === 'ALL' && <Check className="w-3 h-3 text-purple-600" />}
                      </button>
                      {departments.map((d) => (
                        <button
                          key={d.id}
                          type="button"
                          onClick={() => {
                            setSelectedDept(d.id);
                            setDeptMenuOpen(false);
                          }}
                          className="w-full text-left px-3 py-1.5 text-xs text-gray-700 hover:bg-purple-50 flex items-center justify-between"
                        >
                          <span className="truncate pr-2">{d.label}</span>
                          {selectedDept === d.id && <Check className="w-3 h-3 text-purple-600 shrink-0" />}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-2.5">
                <label className="flex items-center gap-1.5 cursor-pointer select-none">
                  <div
                    onClick={() => setCitationEnabled(!citationEnabled)}
                    className={`w-7 h-4 rounded-full transition-colors relative flex items-center p-0.5 ${
                      citationEnabled ? 'bg-purple-600' : 'bg-gray-200'
                    }`}
                  >
                    <div
                      className={`w-3 h-3 rounded-full bg-white shadow-xs transition-transform ${
                        citationEnabled ? 'translate-x-3' : 'translate-x-0'
                      }`}
                    />
                  </div>
                  <span className="text-xs text-gray-500 font-medium">Citation</span>
                </label>

                <VoiceControls voice={voice} hasAnswer={!!lastAnswer.text} />

                <button
                  type="button"
                  onClick={() => sendMessage(input)}
                  disabled={isLoading || !input.trim()}
                  className="p-1.5 rounded-lg bg-[#292c33] text-white hover:bg-[#17191d] active:scale-95 disabled:bg-gray-200 disabled:text-gray-400 disabled:cursor-not-allowed transition-all"
                  title="Send query"
                >
                  <ArrowUp className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
