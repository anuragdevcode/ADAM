'use client';

import React from 'react';
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
 * Full dark mode support and micro-animations.
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

  const micTitle = voiceMode
    ? PHASE_LABEL[phase]
    : isRecording
    ? 'Recording… release to send'
    : 'Hold to speak';

  const micClass = voiceMode
    ? isRecording
      ? 'bg-rose-500 text-white shadow-sm'
      : isSpeaking
      ? 'bg-purple-600 text-white shadow-sm'
      : 'bg-purple-50 dark:bg-purple-950/50 text-purple-600 dark:text-purple-400'
    : isRecording
    ? 'bg-rose-500 text-white shadow-sm animate-pulse'
    : isTranscribing
    ? 'bg-slate-100 dark:bg-slate-800 text-slate-400 cursor-wait'
    : 'text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800/60';

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
          className="h-7 px-1.5 text-[11px] font-medium rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-[#131926] text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800 outline-none cursor-pointer"
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
          className={`relative p-2 rounded-xl transition-all disabled:cursor-default ${micClass}`}
        >
          {isRecording && (
            <span
              aria-hidden
              className="absolute inset-0 rounded-xl ring-2 ring-rose-400/70 transition-transform duration-100"
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
          className={`flex items-center gap-1 px-2.5 py-1.5 text-xs font-semibold rounded-lg border transition-colors disabled:opacity-50 ${
            voiceMode
              ? 'text-white bg-gradient-to-r from-purple-600 to-indigo-600 border-transparent shadow-sm'
              : 'text-purple-700 dark:text-purple-300 bg-purple-50 dark:bg-purple-950/50 hover:bg-purple-100 dark:hover:bg-purple-900/60 border-purple-200/80 dark:border-purple-800/60'
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
              className={`p-2 rounded-xl transition-all ${
                ttsEnabled
                  ? 'text-purple-600 dark:text-purple-400 bg-purple-50/80 dark:bg-purple-950/50'
                  : 'text-slate-400 dark:text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800/60'
              }`}
            >
              {ttsEnabled ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
            </button>

            {ttsEnabled && hasAnswer && (
              <button
                type="button"
                onClick={isSpeaking ? stopSpeaking : speakLatest}
                title={isSpeaking ? 'Stop reading' : 'Read answer aloud'}
                className="flex items-center gap-1 px-2.5 py-1 text-xs font-semibold rounded-lg text-purple-700 dark:text-purple-300 bg-purple-50 dark:bg-purple-950/50 hover:bg-purple-100 dark:hover:bg-purple-900/60 border border-purple-200/80 dark:border-purple-800/60 transition-colors"
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
          className="flex items-center gap-1.5 text-[11px] leading-tight text-purple-700 dark:text-purple-400"
        >
          {isThinking ? (
            <Brain className="w-3 h-3" />
          ) : (
            <span
              aria-hidden
              className={`inline-block w-1.5 h-1.5 rounded-full ${
                isRecording ? 'bg-rose-500 animate-pulse' : isSpeaking ? 'bg-purple-600 animate-pulse' : 'bg-purple-300'
              }`}
            />
          )}
          <span>{PHASE_LABEL[phase]}</span>
          {status && <span className="text-slate-400">· {engineLabel}</span>}
        </p>
      )}

      {error && (
        <p role="alert" className="max-w-64 text-right text-[10px] leading-tight text-rose-600 dark:text-rose-400">
          {error}
        </p>
      )}
    </div>
  );
}
