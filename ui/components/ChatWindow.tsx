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
  Paperclip,
  ChevronDown,
  ArrowUp,
  Check,
  ArrowRight,
  FileText,
  Link2,
  Banknote,
  Landmark,
  Clock,
  LifeBuoy,
  ShieldCheck,
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

/**
 * Starter queries mirror the orders actually present in the seeded pilot
 * corpus, so a first click returns a cited answer rather than an abstention.
 */
const EXAMPLE_CARDS = [
  {
    title: 'Revised Dearness Allowance rate for State employees',
    dept: 'Finance & Treasury',
    query: 'What is the revised Dearness Allowance rate for Uttarakhand State employees?',
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
  // Sessions created by this component already hold their full messages in
  // state; re-fetching them would drop streamed-only fields (see the effect).
  const locallyStartedSession = useRef<string | null>(null);
  const idPrefix = useId();

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (!sessionId) {
      setMessages([]);
      return;
    }
    // Starting a thread assigns a session id, which lands here as a prop
    // change. Reloading history at that point would replace the live messages
    // with the server's role/content-only turns, discarding the citations,
    // banners and suggestions that arrived over the stream.
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
            onStart: (sid) => {
              if (!activeSessionId) {
                activeSessionId = sid;
                locallyStartedSession.current = sid;
                onSessionCreated(sid);
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

  /* One composer definition serves both the welcome screen and the docked bar,
     so the two can never drift apart. */
  const composer = (
    <div
      className={`w-full bg-surface rounded-panel border border-line shadow-md transition-shadow
                  focus-within:border-brand-border focus-within:shadow-lg ${
                    hasMessages ? 'p-3' : 'p-4'
                  }`}
    >
      <textarea
        rows={hasMessages ? 1 : 2}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={composerPlaceholder}
        disabled={isLoading}
        aria-label="Ask a question about Uttarakhand public records"
        className="w-full bg-transparent text-sm text-ink placeholder-ink-faint outline-none resize-none leading-relaxed disabled:opacity-60"
      />

      <div className="flex items-center justify-between mt-2.5 pt-2.5 border-t border-line flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onOpenUpload}
            className="inline-flex items-center gap-1.5 h-7 px-2.5 rounded-lg border border-line text-2xs font-medium text-ink-secondary hover:bg-surface-sunken transition-colors"
            title="Upload an official order PDF for verification"
          >
            <Paperclip className="w-3 h-3 text-ink-faint" />
            <span>Attach</span>
          </button>

          <div className="relative">
            <button
              type="button"
              onClick={() => setDeptMenuOpen(!deptMenuOpen)}
              aria-haspopup="listbox"
              aria-expanded={deptMenuOpen}
              className="inline-flex items-center gap-1 h-7 px-2.5 rounded-lg border border-line text-2xs font-medium text-ink-secondary hover:bg-surface-sunken transition-colors"
            >
              <span className="max-w-[130px] truncate">{currentDeptLabel}</span>
              <ChevronDown className="w-3 h-3 text-ink-faint shrink-0" />
            </button>

            {deptMenuOpen && (
              <div
                role="listbox"
                className="absolute left-0 bottom-full mb-1.5 w-64 bg-surface rounded-card border border-line shadow-xl py-1.5 z-30 max-h-56 overflow-y-auto animate-fade-rise"
              >
                <div className="px-3 py-1 text-2xs uppercase tracking-wider font-semibold text-ink-faint">
                  Scope department
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setSelectedDept('ALL');
                    setDeptMenuOpen(false);
                  }}
                  className="w-full text-left px-3 py-1.5 text-xs text-ink-secondary hover:bg-brand-soft flex items-center justify-between"
                >
                  <span>All Departments</span>
                  {selectedDept === 'ALL' && <Check className="w-3 h-3 text-brand" />}
                </button>
                {departments.map((d) => (
                  <button
                    key={d.id}
                    type="button"
                    onClick={() => {
                      setSelectedDept(d.id);
                      setDeptMenuOpen(false);
                    }}
                    className="w-full text-left px-3 py-1.5 text-xs text-ink-secondary hover:bg-brand-soft flex items-center justify-between"
                  >
                    <span className="truncate pr-2">{d.label}</span>
                    {selectedDept === d.id && <Check className="w-3 h-3 text-brand shrink-0" />}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            role="switch"
            aria-checked={citationEnabled}
            onClick={() => setCitationEnabled(!citationEnabled)}
            className="flex items-center gap-1.5 select-none"
            title="Show source citations with each answer"
          >
            <span
              className={`w-7 h-4 rounded-full transition-colors relative flex items-center p-0.5 ${
                citationEnabled ? 'bg-brand' : 'bg-line-strong'
              }`}
            >
              <span
                className={`w-3 h-3 rounded-full bg-white shadow-xs transition-transform ${
                  citationEnabled ? 'translate-x-3' : 'translate-x-0'
                }`}
              />
            </span>
            <span className="text-2xs text-ink-muted font-medium">Citations</span>
          </button>

          <VoiceControls voice={voice} hasAnswer={!!lastAnswer.text} />

          <button
            type="button"
            onClick={() => sendMessage(input)}
            disabled={isLoading || !input.trim()}
            className="p-2 rounded-lg bg-brand text-ink-onBrand hover:bg-brand-hover active:bg-brand-active disabled:bg-surface-sunken disabled:text-ink-faint disabled:cursor-not-allowed transition-colors shadow-xs"
            title="Send query"
            aria-label="Send query"
          >
            <ArrowUp className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex flex-col h-full bg-surface overflow-hidden relative">
      {!hasMessages ? (
        /* ── Welcome state ───────────────────────────────────────────── */
        <div className="flex-1 overflow-y-auto px-5 sm:px-8 py-10 flex flex-col items-center justify-center min-h-0">
          <div className="max-w-thread w-full flex flex-col items-center text-center my-auto">
            <div className="adam-seal mb-6" aria-hidden />

            <h1 className="text-3xl sm:text-[34px] font-semibold text-ink tracking-tight mb-2.5 leading-tight">
              Uttarakhand Records Assistant
            </h1>
            <p className="text-sm text-ink-muted max-w-lg mb-1.5 leading-relaxed">
              Ask a question in Hindi or English. Every answer is grounded in approved
              government orders and returned with its source citation.
            </p>
            <div className="inline-flex items-center gap-1.5 mb-8 text-2xs text-ink-faint">
              <ShieldCheck className="w-3.5 h-3.5 text-ok" />
              <span>
                Signed in as <span className="font-medium text-ink-muted">{userName}</span> ·{' '}
                {clearanceLevel} clearance
              </span>
            </div>

            <div className="w-full text-left mb-8">{composer}</div>

            <div className="w-full text-left mb-3">
              <p className="text-2xs font-semibold text-ink-faint uppercase tracking-wider">
                Start with a verified record
              </p>
            </div>

            <div className="w-full grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-left">
              {EXAMPLE_CARDS.map((card, idx) => {
                const IconComponent = card.icon;
                return (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => sendMessage(card.query)}
                    className="group bg-surface hover:bg-surface-subtle border border-line hover:border-brand-border
                               rounded-card p-3.5 transition-all hover:shadow-md hover:-translate-y-0.5
                               flex flex-col justify-between h-[132px] text-left"
                  >
                    <div>
                      <span className="inline-flex w-7 h-7 rounded-lg bg-brand-soft items-center justify-center mb-2.5">
                        <IconComponent className="w-3.5 h-3.5 text-brand" />
                      </span>
                      <span className="block text-2xs font-semibold text-ink-faint uppercase tracking-wide mb-1">
                        {card.dept}
                      </span>
                      <p className="text-xs text-ink-secondary leading-snug font-medium group-hover:text-ink transition-colors line-clamp-2">
                        {card.title}
                      </p>
                    </div>
                    <ArrowRight className="w-3.5 h-3.5 text-ink-faint group-hover:text-brand group-hover:translate-x-0.5 transition-all self-end" />
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      ) : (
        /* ── Active thread ───────────────────────────────────────────── */
        <div className="flex-1 flex min-h-0 bg-surface-subtle">
          <div className="flex-1 overflow-y-auto px-5 sm:px-8 py-8 min-w-0">
            <div className="max-w-thread w-full mx-auto space-y-6">
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex flex-col animate-fade-rise ${
                    msg.role === 'user' ? 'items-end' : 'items-start'
                  }`}
                >
                  {msg.role === 'user' ? (
                    <div className="bg-brand text-ink-onBrand rounded-panel rounded-tr-md px-4 py-2.5 text-sm max-w-xl shadow-sm leading-relaxed whitespace-pre-wrap">
                      {msg.content}
                    </div>
                  ) : (
                    <div className="w-full bg-surface rounded-panel border border-line p-5 shadow-sm">
                      <div className="flex items-center gap-2 mb-3 pb-3 border-b border-line">
                        <span className="w-6 h-6 rounded-lg bg-brand flex items-center justify-center text-ink-onBrand shrink-0">
                          <ShieldCheck className="w-3.5 h-3.5" />
                        </span>
                        <span className="text-xs font-semibold text-ink">ADAM</span>
                        <span className="text-2xs text-ink-faint">
                          Uttarakhand Records Repository
                        </span>
                        {msg.isNoAnswer && (
                          <span className="ml-auto px-2 py-0.5 rounded-full bg-warn-soft text-warn text-[10px] font-semibold uppercase tracking-wide">
                            No answer in corpus
                          </span>
                        )}
                      </div>

                      <div
                        className={`text-sm text-ink-secondary leading-relaxed ${
                          msg.isStreaming ? 'stream-caret' : ''
                        }`}
                      >
                        <Markdown text={msg.content} />
                      </div>

                      {msg.banners && msg.banners.length > 0 && (
                        <div className="mt-3 space-y-2">
                          {msg.banners.map((b, i) => (
                            <CurrencyBanner key={i} message={b} />
                          ))}
                        </div>
                      )}

                      {msg.citations && msg.citations.length > 0 && (
                        <div className="mt-4 pt-3 border-t border-line">
                          <p className="text-2xs font-semibold text-ink-faint uppercase tracking-wider mb-2">
                            Sources &amp; precedents
                          </p>
                          <div className="space-y-2">
                            {msg.citations.map((c, i) => (
                              <CitationCard key={i} citation={c} index={i} />
                            ))}
                          </div>
                        </div>
                      )}

                      {msg.suggestions && msg.suggestions.length > 0 && (
                        <div className="mt-3 p-3 rounded-card bg-brand-soft border border-brand-border">
                          <p className="text-xs font-semibold text-brand-active mb-1.5">
                            Try narrowing your question:
                          </p>
                          <ul className="space-y-1">
                            {msg.suggestions.map((s, i) => (
                              <li key={i}>
                                <button
                                  type="button"
                                  onClick={() => sendMessage(s)}
                                  className="text-xs text-brand hover:text-brand-active hover:underline text-left"
                                >
                                  {s}
                                </button>
                              </li>
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

          {/* Context sidebar */}
          <aside className="hidden xl:flex w-[300px] shrink-0 border-l border-line bg-surface p-4 flex-col gap-4 overflow-y-auto">
            <section className="rounded-card border border-line p-4">
              <div className="flex items-center gap-2 mb-3">
                <Link2 className="w-4 h-4 text-brand" />
                <h2 className="text-xs font-semibold text-ink uppercase tracking-wide">Sources</h2>
              </div>
              {latestCitations.length ? (
                <div className="space-y-2">
                  {latestCitations.slice(0, 3).map((citation, index) => (
                    <a
                      key={`${citation.document_id || citation.document_title}-${index}`}
                      href={citation.source_url || citation.pdf_page_link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="block rounded-lg bg-surface-sunken p-2.5 hover:bg-brand-soft transition-colors"
                    >
                      <p className="text-xs font-medium text-ink-secondary line-clamp-2">
                        {citation.document_title}
                      </p>
                      <p className="mt-1 text-2xs uppercase tracking-wide text-ink-muted tabular">
                        {citation.go_number || `Page ${citation.page}`}
                      </p>
                    </a>
                  ))}
                </div>
              ) : (
                <div className="py-3 text-center">
                  <div className="mx-auto mb-2 flex h-9 w-9 items-center justify-center rounded-lg bg-brand-soft">
                    <FileText className="h-4 w-4 text-brand" />
                  </div>
                  <p className="text-xs leading-relaxed text-ink-muted">
                    Sources from verified records will appear here.
                  </p>
                  <button
                    type="button"
                    onClick={onOpenUpload}
                    className="mt-3 text-xs font-semibold text-brand hover:text-brand-hover"
                  >
                    Add an order
                  </button>
                </div>
              )}
            </section>

            <section className="rounded-card border border-line p-4">
              <h2 className="text-xs font-semibold text-ink uppercase tracking-wide">
                Suggested follow-ups
              </h2>
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
                    className="w-full rounded-lg bg-surface-sunken px-3 py-2 text-left text-xs leading-snug text-ink-secondary hover:bg-brand-soft hover:text-brand-active transition-colors"
                  >
                    {question}
                  </button>
                ))}
              </div>
            </section>

            <p className="px-1 text-2xs leading-relaxed text-ink-faint">
              Responses are grounded only in approved public records.
            </p>
          </aside>
        </div>
      )}

      {/* Docked composer, shown once a thread is under way */}
      {hasMessages && (
        <div className="p-3 sm:p-4 border-t border-line bg-surface">
          <div className="max-w-thread w-full mx-auto">{composer}</div>
        </div>
      )}
    </div>
  );
}
