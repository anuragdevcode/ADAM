'use client';

import type { VoiceConversation } from '@/lib/useVoiceConversation';
import { VOICE_LANGUAGES } from '@/lib/voice';
import type { VoiceLanguage } from '@/lib/types';
import { AudioLines, Mic, Volume2, VolumeX, Square, Play, Loader2, Brain } from 'lucide-react';

interface VoiceControlsProps {
  voice: VoiceConversation;
  /** Whether there is an answer available to read aloud. */
  hasAnswer: boolean;
}

const PHASE_LABEL: Record<VoiceConversation['phase'], string> = {
  idle: 'Voice mode on',
  listening: 'Listening… tap mic when done',
  transcribing: 'Transcribing…',
  thinking: 'Thinking…',
  speaking: 'Speaking — tap mic to interrupt',
};

/**
 * Voice controls for the chat composer.
 *
 * All state lives in `useVoiceConversation` (owned by ChatWindow) so the loop
 * survives this component being re-mounted when the layout switches from the
 * empty state to the docked composer.
 */
export default function VoiceControls({ voice, hasAnswer }: VoiceControlsProps) {
  const {
    phase,
    voiceMode,
    toggleVoiceMode,
    ttsEnabled,
    toggleTts,
    language,
    setLanguage,
    level,
    error,
    startPushToTalk,
    stopPushToTalk,
    speakLatest,
    stopSpeaking,
    interrupt,
    finishTurn,
    inputSupported,
    engineLabel,
    status,
  } = voice;

  const isRecording = phase === 'listening';
  const isTranscribing = phase === 'transcribing';
  const isSpeaking = phase === 'speaking';
  const isThinking = phase === 'thinking';

  // Inside voice mode the mic button reflects the loop phase and doubles as
  // the interrupt control; outside it is a plain hold-to-talk button.
  const micTitle = voiceMode
    ? PHASE_LABEL[phase]
    : isRecording
    ? 'Recording… release to send'
    : 'Hold to speak';

  const micClass = voiceMode
    ? isRecording
      ? 'bg-danger text-white shadow-sm'
      : isSpeaking
      ? 'bg-brand text-ink-onBrand shadow-sm'
      : 'bg-brand-soft text-brand'
    : isRecording
    ? 'bg-danger text-white shadow-sm'
    : isTranscribing
    ? 'bg-surface-sunken text-ink-faint cursor-wait'
    : 'text-ink-faint hover:text-ink-secondary hover:bg-surface-sunken';

  const micIcon = isTranscribing || isThinking ? (
    <Loader2 className="w-4 h-4 animate-spin" />
  ) : voiceMode && isSpeaking ? (
    <AudioLines className="w-4 h-4" />
  ) : (
    <Mic className="w-4 h-4" />
  );

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-center gap-1.5">
        {/* Spoken language (shared by STT and TTS) */}
        <select
          value={language}
          onChange={(e) => setLanguage(e.target.value as VoiceLanguage)}
          title="Spoken language"
          aria-label="Spoken language"
          className="h-7 px-1.5 text-2xs font-medium rounded-lg border border-line bg-surface text-ink-secondary hover:bg-surface-sunken outline-none cursor-pointer"
        >
          {VOICE_LANGUAGES.map((l) => (
            <option key={l.value} value={l.value}>
              {l.label}
            </option>
          ))}
        </select>

        {/* Mic: hold-to-talk, or the live phase indicator in voice mode */}
        <button
          type="button"
          onPointerDown={voiceMode ? undefined : startPushToTalk}
          onPointerUp={voiceMode ? undefined : stopPushToTalk}
          onPointerCancel={voiceMode ? undefined : stopPushToTalk}
          onPointerLeave={voiceMode || !isRecording ? undefined : stopPushToTalk}
          onClick={voiceMode ? (isSpeaking ? interrupt : isRecording ? finishTurn : undefined) : undefined}
          disabled={!inputSupported || (!voiceMode && isTranscribing) || (voiceMode && !isSpeaking && !isRecording)}
          title={inputSupported ? micTitle : 'Speech input is not supported in this browser'}
          aria-label={micTitle}
          className={`relative p-2 rounded-xl transition-colors disabled:cursor-default ${micClass}`}
        >
          {isRecording && (
            <span
              aria-hidden
              className="absolute inset-0 rounded-xl ring-2 ring-[var(--danger)] transition-transform duration-100"
              style={{ transform: `scale(${1 + Math.min(level, 1) * 0.35})`, opacity: 0.4 + level * 0.6 }}
            />
          )}
          <span className="relative">{micIcon}</span>
        </button>

        {/* Hands-free conversation toggle */}
        <button
          type="button"
          onClick={toggleVoiceMode}
          disabled={!inputSupported}
          title={voiceMode ? 'End voice conversation' : 'Start voice conversation (talk, listen, repeat)'}
          aria-pressed={voiceMode}
          className={`flex items-center gap-1 h-7 px-2.5 text-2xs font-semibold rounded-lg border transition-colors disabled:opacity-50 ${
            voiceMode
              ? 'text-ink-onBrand bg-brand border-transparent shadow-xs'
              : 'text-brand bg-brand-soft hover:bg-brand-softHover border-brand-border'
          }`}
        >
          {voiceMode ? <Square className="w-3 h-3 fill-current" /> : <AudioLines className="w-3.5 h-3.5" />}
          <span>{voiceMode ? 'End' : 'Voice'}</span>
        </button>

        {/* Text-mode extras: read-aloud toggle and Listen/Stop */}
        {!voiceMode && (
          <>
            <button
              type="button"
              onClick={toggleTts}
              title={ttsEnabled ? 'Voice output enabled' : 'Enable voice output'}
              aria-pressed={ttsEnabled}
              className={`p-2 rounded-xl transition-colors ${
                ttsEnabled
                  ? 'text-brand bg-brand-soft'
                  : 'text-ink-faint hover:text-ink-secondary hover:bg-surface-sunken'
              }`}
            >
              {ttsEnabled ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
            </button>

            {ttsEnabled && hasAnswer && (
              <button
                type="button"
                onClick={isSpeaking ? stopSpeaking : speakLatest}
                title={isSpeaking ? 'Stop reading' : 'Read answer aloud'}
                className="flex items-center gap-1 h-7 px-2.5 text-2xs font-semibold rounded-lg text-brand bg-brand-soft hover:bg-brand-softHover border border-brand-border transition-colors"
              >
                {isSpeaking ? (
                  <>
                    <Square className="w-3 h-3 fill-current" />
                    <span>Stop</span>
                  </>
                ) : (
                  <>
                    <Play className="w-3 h-3 fill-current" />
                    <span>Listen</span>
                  </>
                )}
              </button>
            )}
          </>
        )}
      </div>

      {voiceMode && (
        <p
          role="status"
          aria-live="polite"
          className="flex items-center gap-1.5 text-2xs leading-tight text-brand"
        >
          {isThinking ? (
            <Brain className="w-3 h-3" />
          ) : (
            <span
              aria-hidden
              className={`inline-block w-1.5 h-1.5 rounded-full ${
                isRecording
                  ? 'bg-danger animate-pulse'
                  : isSpeaking
                  ? 'bg-brand animate-pulse'
                  : 'bg-brand-border'
              }`}
            />
          )}
          <span>{PHASE_LABEL[phase]}</span>
          {status && <span className="text-ink-faint">· {engineLabel}</span>}
        </p>
      )}

      {error && (
        <p role="alert" className="max-w-64 text-right text-[10px] leading-tight text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
