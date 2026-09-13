'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchVoiceStatus, synthesizeSpeech, transcribeAudio } from './api';
import type { VoiceLanguage, VoicePhase, VoiceStatus } from './types';
import {
  browserRecognitionSupported,
  browserSynthesisSupported,
  listenWithBrowser,
  loadVoiceLanguage,
  microphoneSupported,
  playAudioBlob,
  recordUntilSilence,
  saveVoiceLanguage,
  shortLanguage,
  speakWithBrowser,
  taskError,
  toSpeechText,
  type VoiceTask,
} from './voice';

export interface VoiceAnswer {
  /** Final answer text of the most recent completed turn. */
  text: string;
  /** Increments per completed turn so identical answers are still spoken. */
  seq: number;
}

export interface UseVoiceConversationOptions {
  /** Submit a finished transcript to the chat pipeline. */
  onTranscript: (text: string) => void;
  /** Live partial transcript while the officer is still talking. */
  onInterim?: (text: string) => void;
  /** True while the agent is streaming an answer. */
  isBusy: boolean;
  /** The latest completed answer, spoken back in voice mode / when TTS is on. */
  answer: VoiceAnswer;
}

export interface VoiceConversation {
  status: VoiceStatus | null;
  phase: VoicePhase;
  /** Hands-free loop: listen → answer → speak → listen … */
  voiceMode: boolean;
  toggleVoiceMode: () => void;
  /** Read answers aloud in text mode too. */
  ttsEnabled: boolean;
  toggleTts: () => void;
  language: VoiceLanguage;
  setLanguage: (lang: VoiceLanguage) => void;
  /** Microphone input level 0–1 while recording (server STT only). */
  level: number;
  error: string | null;
  /** Hold-to-talk outside voice mode. */
  startPushToTalk: () => void;
  stopPushToTalk: () => void;
  /** Read the latest answer aloud / stop whatever is playing. */
  speakLatest: () => void;
  stopSpeaking: () => void;
  /** Cut the spoken answer short and go straight back to listening. */
  interrupt: () => void;
  /** Stop listening now and send whatever was heard (voice mode). */
  finishTurn: () => void;
  /** Whether the browser can do speech at all (mic or Web Speech API). */
  inputSupported: boolean;
  /** Short human label of the engines in use, e.g. "Groq · ElevenLabs". */
  engineLabel: string;
}

const EMPTY_TURN_LIMIT = 2;

function describeEngine(status: VoiceStatus | null, kind: 'stt' | 'tts'): string {
  const provider = status?.[kind].provider;
  switch (provider) {
    case 'groq':
      return 'Groq Whisper';
    case 'faster_whisper':
      return 'Whisper (local)';
    case 'elevenlabs':
      return 'ElevenLabs';
    case 'piper':
      return 'Piper';
    default:
      return 'Browser';
  }
}

export function useVoiceConversation({
  onTranscript,
  onInterim,
  isBusy,
  answer,
}: UseVoiceConversationOptions): VoiceConversation {
  const [status, setStatus] = useState<VoiceStatus | null>(null);
  const [phase, setPhaseState] = useState<VoicePhase>('idle');
  const [voiceMode, setVoiceModeState] = useState(false);
  const [ttsEnabled, setTtsEnabled] = useState(false);
  const [language, setLanguageState] = useState<VoiceLanguage>('hi-IN');
  const [level, setLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);
  // Assume support until mounted so SSR and the first client render agree.
  const [inputSupported, setInputSupported] = useState(true);

  // Refs mirror state that async callbacks need to read without going stale.
  const phaseRef = useRef<VoicePhase>('idle');
  const voiceModeRef = useRef(false);
  const languageRef = useRef<VoiceLanguage>('hi-IN');
  const statusRef = useRef<VoiceStatus | null>(null);
  const taskRef = useRef<VoiceTask<unknown> | null>(null);
  const ttsEnabledRef = useRef(false);
  const spokenSeqRef = useRef(0);
  const emptyTurnsRef = useRef(0);
  const onTranscriptRef = useRef(onTranscript);
  const onInterimRef = useRef(onInterim);
  onTranscriptRef.current = onTranscript;
  onInterimRef.current = onInterim;

  const setPhase = useCallback((p: VoicePhase) => {
    phaseRef.current = p;
    setPhaseState(p);
  }, []);

  const setVoiceMode = useCallback((on: boolean) => {
    voiceModeRef.current = on;
    setVoiceModeState(on);
  }, []);

  const setLanguage = useCallback((lang: VoiceLanguage) => {
    languageRef.current = lang;
    setLanguageState(lang);
    saveVoiceLanguage(lang);
  }, []);

  useEffect(() => {
    const lang = loadVoiceLanguage();
    languageRef.current = lang;
    setLanguageState(lang);
    setInputSupported(microphoneSupported() || browserRecognitionSupported());
    let cancelled = false;
    fetchVoiceStatus().then((s) => {
      if (cancelled) return;
      statusRef.current = s;
      setStatus(s);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  /** Cancel whatever recording / playback is in flight. */
  const cancelCurrentTask = useCallback(() => {
    taskRef.current?.cancel();
    taskRef.current = null;
    setLevel(0);
  }, []);

  const serverSttReady = useCallback(
    () => !!statusRef.current?.stt.available && microphoneSupported(),
    [],
  );
  const serverTtsReady = useCallback(() => !!statusRef.current?.tts.available, []);

  const stopVoiceMode = useCallback(
    (message?: string) => {
      cancelCurrentTask();
      setVoiceMode(false);
      setPhase('idle');
      if (message) setError(message);
    },
    [cancelCurrentTask, setPhase, setVoiceMode],
  );

  // ── Listening ──────────────────────────────────────────────────────────

  const submitTranscript = useCallback(
    (text: string) => {
      emptyTurnsRef.current = 0;
      setPhase('thinking');
      onTranscriptRef.current(text);
    },
    [setPhase],
  );

  const listen = useCallback(async () => {
    if (!voiceModeRef.current) return;
    setError(null);
    setPhase('listening');

    const finishEmpty = (task: VoiceTask<unknown>) => {
      const err = taskError(task);
      if (err) {
        stopVoiceMode(err.message);
        return;
      }
      emptyTurnsRef.current += 1;
      if (emptyTurnsRef.current >= EMPTY_TURN_LIMIT) {
        stopVoiceMode('No speech detected. Tap the voice button to start again.');
        return;
      }
      void listen();
    };

    if (serverSttReady()) {
      const task = recordUntilSilence({ onLevel: setLevel });
      taskRef.current = task;
      const blob = await task.promise;
      if (taskRef.current !== task) return; // superseded (toggle / interrupt)
      taskRef.current = null;
      setLevel(0);
      if (!blob) {
        finishEmpty(task);
        return;
      }
      setPhase('transcribing');
      try {
        const result = await transcribeAudio(blob, shortLanguage(languageRef.current));
        if (!voiceModeRef.current) return;
        if (!result.transcript.trim()) {
          finishEmpty(task);
          return;
        }
        submitTranscript(result.transcript.trim());
      } catch (err) {
        if (!voiceModeRef.current) return;
        stopVoiceMode(err instanceof Error ? err.message : 'Speech-to-text failed.');
      }
      return;
    }

    if (browserRecognitionSupported()) {
      const task = listenWithBrowser(languageRef.current, (t) => onInterimRef.current?.(t));
      taskRef.current = task;
      const text = await task.promise;
      if (taskRef.current !== task) return;
      taskRef.current = null;
      if (!text) {
        finishEmpty(task);
        return;
      }
      submitTranscript(text);
      return;
    }

    stopVoiceMode(
      'This browser has no speech recognition. Use Chrome/Edge, or set GROQ_API_KEY on the server.',
    );
  }, [setPhase, stopVoiceMode, submitTranscript, serverSttReady]);

  // ── Speaking ───────────────────────────────────────────────────────────

  const afterSpeaking = useCallback(() => {
    if (voiceModeRef.current) void listen();
    else setPhase('idle');
  }, [listen, setPhase]);

  const speak = useCallback(
    async (text: string, seq: number) => {
      spokenSeqRef.current = seq;
      const spoken = toSpeechText(text);
      if (!spoken) {
        afterSpeaking();
        return;
      }
      cancelCurrentTask();
      setPhase('speaking');

      let task: VoiceTask<void> | null = null;
      if (serverTtsReady()) {
        try {
          const blob = await synthesizeSpeech(spoken, shortLanguage(languageRef.current));
          if (phaseRef.current !== 'speaking') return; // interrupted meanwhile
          // Engines with nothing to say return a 44-byte silent WAV.
          if (blob.size > 44) task = playAudioBlob(blob);
        } catch (err) {
          if (phaseRef.current !== 'speaking') return;
          console.warn('Server TTS failed, using browser voice:', err);
          if (!browserSynthesisSupported()) {
            setError(err instanceof Error ? err.message : 'Text-to-speech failed.');
          }
        }
      }
      if (!task && browserSynthesisSupported()) task = speakWithBrowser(spoken, languageRef.current);
      if (!task) {
        afterSpeaking();
        return;
      }
      taskRef.current = task;
      await task.promise;
      if (taskRef.current !== task) return; // interrupted
      taskRef.current = null;
      afterSpeaking();
    },
    [afterSpeaking, cancelCurrentTask, setPhase, serverTtsReady],
  );

  const stopSpeaking = useCallback(() => {
    if (phaseRef.current !== 'speaking') return;
    cancelCurrentTask();
    afterSpeaking();
  }, [afterSpeaking, cancelCurrentTask]);

  const speakLatest = useCallback(() => {
    if (!answer.text) return;
    void speak(answer.text, answer.seq);
  }, [answer, speak]);

  // Answers arrive through props; decide what to do when a turn completes.
  useEffect(() => {
    if (isBusy) return;
    const fresh = answer.seq !== spokenSeqRef.current && !!answer.text;

    if (voiceModeRef.current && phaseRef.current === 'thinking') {
      if (fresh) {
        void speak(answer.text, answer.seq);
        return;
      }
      // The turn ended without a new answer (send rejected / error event):
      // give React a beat to deliver one, then go back to listening.
      const timer = setTimeout(() => {
        if (voiceModeRef.current && phaseRef.current === 'thinking') void listen();
      }, 600);
      return () => clearTimeout(timer);
    }

    // Text mode with read-aloud on: a newer answer takes over from one still playing.
    if (!voiceModeRef.current && ttsEnabled && fresh && phaseRef.current !== 'listening') {
      void speak(answer.text, answer.seq);
    }
  }, [isBusy, answer, ttsEnabled, speak, listen]);

  // A typed message sent while listening: stop the mic and wait for the answer.
  useEffect(() => {
    if (isBusy && voiceModeRef.current && phaseRef.current === 'listening') {
      cancelCurrentTask();
      setPhase('thinking');
    }
  }, [isBusy, cancelCurrentTask, setPhase]);

  // ── Controls ───────────────────────────────────────────────────────────

  const toggleVoiceMode = useCallback(() => {
    if (voiceModeRef.current) {
      stopVoiceMode();
      return;
    }
    if (!microphoneSupported() && !browserRecognitionSupported()) {
      setError('This browser cannot capture speech.');
      return;
    }
    setError(null);
    emptyTurnsRef.current = 0;
    // Skip the current answer so voice mode does not start by re-reading it.
    spokenSeqRef.current = answer.seq;
    setVoiceMode(true);
    if (isBusy) setPhase('thinking');
    else void listen();
  }, [answer.seq, isBusy, listen, setPhase, setVoiceMode, stopVoiceMode]);

  const interrupt = useCallback(() => {
    cancelCurrentTask();
    if (voiceModeRef.current) void listen();
    else setPhase('idle');
  }, [cancelCurrentTask, listen, setPhase]);

  const toggleTts = useCallback(() => {
    const next = !ttsEnabledRef.current;
    ttsEnabledRef.current = next;
    setTtsEnabled(next);
    if (!next && phaseRef.current === 'speaking' && !voiceModeRef.current) {
      cancelCurrentTask();
      setPhase('idle');
    }
  }, [cancelCurrentTask, setPhase]);

  const startPushToTalk = useCallback(() => {
    if (voiceModeRef.current || phaseRef.current === 'transcribing') return;
    cancelCurrentTask();
    setError(null);
    setPhase('listening');

    const handleEmpty = (task: VoiceTask<unknown>) => {
      const err = taskError(task);
      setError(err ? err.message : 'Nothing was heard. Hold the mic and speak.');
      setPhase('idle');
    };

    if (serverSttReady()) {
      // Held recording: silence is decided by the officer releasing the button.
      const task = recordUntilSilence({ onLevel: setLevel, silenceMs: 60000, noSpeechTimeoutMs: 60000 });
      taskRef.current = task;
      void task.promise.then(async (blob) => {
        if (taskRef.current !== task) return;
        taskRef.current = null;
        setLevel(0);
        if (!blob) return handleEmpty(task);
        setPhase('transcribing');
        try {
          const result = await transcribeAudio(blob, shortLanguage(languageRef.current));
          setPhase('idle');
          if (result.transcript.trim()) onTranscriptRef.current(result.transcript.trim());
          else setError('No speech was recognised.');
        } catch (err) {
          setPhase('idle');
          setError(err instanceof Error ? err.message : 'Speech-to-text failed.');
        }
      });
      return;
    }

    if (browserRecognitionSupported()) {
      const task = listenWithBrowser(languageRef.current, (t) => onInterimRef.current?.(t));
      taskRef.current = task;
      void task.promise.then((text) => {
        if (taskRef.current !== task) return;
        taskRef.current = null;
        setPhase('idle');
        if (text) onTranscriptRef.current(text);
        else handleEmpty(task);
      });
      return;
    }

    setPhase('idle');
    setError('This browser has no speech recognition. Use Chrome/Edge, or set GROQ_API_KEY on the server.');
  }, [cancelCurrentTask, setPhase, serverSttReady]);

  const stopPushToTalk = useCallback(() => {
    if (voiceModeRef.current) return;
    taskRef.current?.stop();
  }, []);

  const finishTurn = useCallback(() => {
    if (phaseRef.current === 'listening') taskRef.current?.stop();
  }, []);

  // Tear everything down when the chat unmounts.
  useEffect(() => {
    return () => {
      taskRef.current?.cancel();
      if (browserSynthesisSupported()) window.speechSynthesis.cancel();
    };
  }, []);

  const engineLabel = `${describeEngine(status, 'stt')} · ${describeEngine(status, 'tts')}`;

  return {
    status,
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
  };
}
