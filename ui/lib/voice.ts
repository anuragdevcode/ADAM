/**
 * Browser-side voice primitives used by the voice conversation loop.
 *
 * Two families of engines exist:
 *  - Server engines (Groq Whisper / ElevenLabs / local faster-whisper, Piper)
 *    reached through /api/voice/*.  Recording uses MediaRecorder plus a small
 *    energy-based silence detector so the officer does not have to hold a key.
 *  - Browser engines (Web Speech API: SpeechRecognition + speechSynthesis) that
 *    need no API key at all and are used whenever the server has none.
 */

import type { VoiceLanguage } from './types';

export const VOICE_LANGUAGE_STORAGE_KEY = 'adam.voice.language';

export const VOICE_LANGUAGES: { value: VoiceLanguage; label: string }[] = [
  { value: 'hi-IN', label: 'हिन्दी' },
  { value: 'en-IN', label: 'English' },
];

/** Handle returned by every asynchronous voice operation. */
export interface VoiceTask<T> {
  /** Resolves with the result, or `null` when cancelled / nothing captured. */
  promise: Promise<T | null>;
  /** Finish early but still deliver what was captured (recording only). */
  stop: () => void;
  /** Abort and resolve with `null`. */
  cancel: () => void;
}

// ── Minimal Web Speech API typings (not part of lib.dom) ──────────────────

interface SpeechRecognitionResultLike {
  isFinal: boolean;
  0: { transcript: string };
}
interface SpeechRecognitionEventLike {
  resultIndex: number;
  results: ArrayLike<SpeechRecognitionResultLike>;
}
interface SpeechRecognitionLike {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  maxAlternatives: number;
  onresult: ((e: SpeechRecognitionEventLike) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

function getRecognitionCtor(): SpeechRecognitionCtor | null {
  if (typeof window === 'undefined') return null;
  const w = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function browserRecognitionSupported(): boolean {
  return getRecognitionCtor() !== null;
}

export function browserSynthesisSupported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window;
}

export function microphoneSupported(): boolean {
  return (
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof MediaRecorder !== 'undefined'
  );
}

export function loadVoiceLanguage(fallback: VoiceLanguage = 'hi-IN'): VoiceLanguage {
  try {
    const stored = window.localStorage.getItem(VOICE_LANGUAGE_STORAGE_KEY);
    if (stored === 'hi-IN' || stored === 'en-IN') return stored;
  } catch {
    /* storage unavailable */
  }
  return fallback;
}

export function saveVoiceLanguage(lang: VoiceLanguage): void {
  try {
    window.localStorage.setItem(VOICE_LANGUAGE_STORAGE_KEY, lang);
  } catch {
    /* storage unavailable */
  }
}

/** ISO-639-1 code the server engines expect ("hi", "en"). */
export function shortLanguage(lang: VoiceLanguage): string {
  return lang.split('-')[0];
}

// ── Speech text preparation ────────────────────────────────────────────────

/**
 * Strip Markdown and citation markers so the browser voice reads prose only.
 * The server applies the same cleanup for its own engines
 * (adam/api/voice/speech_text.py); this keeps the browser fallback consistent.
 */
export function toSpeechText(text: string): string {
  if (!text) return '';
  let out = text.replace(/```[\s\S]*?```/g, ' ');
  out = out.replace(/`([^`]*)`/g, '$1');
  out = out.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1');
  out = out.replace(/https?:\/\/\S+/g, '');
  out = out.replace(/^\s{0,3}#{1,6}\s*/gm, '');
  out = out.replace(/^\s*>\s?/gm, '');
  out = out.replace(/^\s*(?:[-*+•]|\d+[.)])\s+/gm, '');
  out = out.replace(/(\*\*|__|\*|_|~~)(?=\S)(.+?)(?<=\S)\1/g, '$2');
  out = out.replace(/(\*\*|__|\*|_|~~)(?=\S)(.+?)(?<=\S)\1/g, '$2');
  out = out.replace(/\[(?:\d+(?:\s*,\s*\d+)*|GO[-\s][^\]]*|Source:[^\]]*|§[^\]]*)\]/gi, '');
  out = out.replace(/\((?:Source|Ref|See)\s*:[^)]*\)/gi, '');
  out = out.replace(/^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/gm, '');
  out = out.replace(/^\s*([-*_]\s*){3,}$/gm, '');
  out = out.replace(/\|/g, ' ');
  out = out.replace(/[ \t]+/g, ' ');
  out = out.replace(/[ \t]+\n/g, '\n');
  out = out.replace(/\n{2,}/g, '\n');
  out = out.replace(/\s+([.,;:!?।])/g, '$1');
  return out.trim();
}

/** Split into sentence-sized chunks; long utterances stall in some browsers. */
export function splitForSpeech(text: string, maxLen = 220): string[] {
  const sentences = text.split(/(?<=[.!?।\n])\s+/);
  const chunks: string[] = [];
  let current = '';
  for (const s of sentences) {
    if (!s) continue;
    if (current && current.length + s.length + 1 > maxLen) {
      chunks.push(current.trim());
      current = s;
    } else {
      current = current ? `${current} ${s}` : s;
    }
    while (current.length > maxLen) {
      chunks.push(current.slice(0, maxLen));
      current = current.slice(maxLen);
    }
  }
  if (current.trim()) chunks.push(current.trim());
  return chunks;
}

// ── Recording with silence detection (server STT) ─────────────────────────

export interface RecordOptions {
  /** RMS level (0–1) above which audio counts as speech. */
  speechThreshold?: number;
  /** Stop this long after the last detected speech. */
  silenceMs?: number;
  /** Give up if nothing is said within this window. */
  noSpeechTimeoutMs?: number;
  /** Hard ceiling for one utterance. */
  maxDurationMs?: number;
  /** Called every ~100 ms with the current input level (0–1). */
  onLevel?: (level: number) => void;
}

function pickRecorderMimeType(): string | undefined {
  if (typeof MediaRecorder === 'undefined') return undefined;
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus'];
  return candidates.find((t) => MediaRecorder.isTypeSupported(t));
}

/**
 * Record from the microphone until the speaker pauses.
 * Resolves with the recorded blob, or `null` when nothing was said / cancelled.
 */
export function recordUntilSilence(opts: RecordOptions = {}): VoiceTask<Blob> {
  const {
    speechThreshold = 0.02,
    silenceMs = 1300,
    noSpeechTimeoutMs = 8000,
    maxDurationMs = 45000,
    onLevel,
  } = opts;

  let recorder: MediaRecorder | null = null;
  let stream: MediaStream | null = null;
  let audioCtx: AudioContext | null = null;
  let timer: ReturnType<typeof setInterval> | null = null;
  let cancelled = false;
  let resolveDone: (blob: Blob | null) => void = () => {};
  let heardSpeech = false;

  const cleanup = () => {
    if (timer) clearInterval(timer);
    timer = null;
    stream?.getTracks().forEach((t) => t.stop());
    stream = null;
    void audioCtx?.close().catch(() => {});
    audioCtx = null;
  };

  const promise = new Promise<Blob | null>((resolve) => {
    resolveDone = resolve;
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });
        if (cancelled) {
          cleanup();
          resolve(null);
          return;
        }
        const mimeType = pickRecorderMimeType();
        recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
        const chunks: Blob[] = [];
        recorder.ondataavailable = (e) => {
          if (e.data.size > 0) chunks.push(e.data);
        };
        recorder.onstop = () => {
          cleanup();
          if (cancelled || !heardSpeech || chunks.length === 0) {
            resolve(null);
            return;
          }
          resolve(new Blob(chunks, { type: recorder?.mimeType || mimeType || 'audio/webm' }));
        };
        recorder.start(250);

        // Energy-based voice activity detection.
        audioCtx = new AudioContext();
        const source = audioCtx.createMediaStreamSource(stream);
        const analyser = audioCtx.createAnalyser();
        analyser.fftSize = 1024;
        source.connect(analyser);
        const buf = new Float32Array(analyser.fftSize);
        const startedAt = Date.now();
        let lastSpeechAt = 0;

        timer = setInterval(() => {
          if (!recorder || recorder.state !== 'recording') return;
          analyser.getFloatTimeDomainData(buf);
          let sum = 0;
          for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
          const rms = Math.sqrt(sum / buf.length);
          onLevel?.(Math.min(1, rms * 8));
          const now = Date.now();
          if (rms > speechThreshold) {
            heardSpeech = true;
            lastSpeechAt = now;
          }
          if (heardSpeech && now - lastSpeechAt > silenceMs) recorder.stop();
          else if (!heardSpeech && now - startedAt > noSpeechTimeoutMs) recorder.stop();
          else if (now - startedAt > maxDurationMs) recorder.stop();
        }, 100);
      } catch (err) {
        cleanup();
        // Surface microphone permission problems through `taskError()`.
        if (!cancelled) attachError(promise, err);
        resolve(null);
      }
    })();
  });

  return {
    promise,
    stop: () => {
      if (recorder && recorder.state === 'recording') {
        // Treat a manual stop as "I am done talking" even if the detector
        // never crossed the threshold (quiet microphones).
        heardSpeech = true;
        recorder.stop();
      } else {
        cleanup();
        resolveDone(null);
      }
    },
    cancel: () => {
      cancelled = true;
      if (recorder && recorder.state === 'recording') recorder.stop();
      else {
        cleanup();
        resolveDone(null);
      }
    },
  };
}

// ── Browser speech recognition (no API key) ───────────────────────────────

/**
 * Listen with the Web Speech API until the speaker pauses.
 * Interim results stream through `onInterim`; resolves with the final text.
 */
export function listenWithBrowser(
  lang: VoiceLanguage,
  onInterim?: (text: string) => void,
): VoiceTask<string> {
  const Ctor = getRecognitionCtor();
  if (!Ctor) {
    return { promise: Promise.resolve(null), stop: () => {}, cancel: () => {} };
  }
  const rec = new Ctor();
  rec.lang = lang;
  rec.interimResults = true;
  rec.continuous = false;
  rec.maxAlternatives = 1;

  let finalText = '';
  let cancelled = false;
  let errorMessage: string | null = null;

  const promise = new Promise<string | null>((resolve) => {
    rec.onresult = (e) => {
      let interim = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) finalText += r[0].transcript;
        else interim += r[0].transcript;
      }
      onInterim?.((finalText + interim).trim());
    };
    rec.onerror = (e) => {
      // "no-speech" and "aborted" are normal ends of a quiet turn.
      if (e.error !== 'no-speech' && e.error !== 'aborted') errorMessage = e.error;
    };
    rec.onend = () => {
      if (cancelled) return resolve(null);
      if (errorMessage) {
        attachError(
          promise,
          new Error(
            errorMessage === 'not-allowed'
              ? 'Microphone access was denied.'
              : errorMessage === 'network'
              ? 'Browser speech recognition needs an internet connection.'
              : `Speech recognition error: ${errorMessage}`,
          ),
        );
        return resolve(null);
      }
      resolve(finalText.trim() || null);
    };
    try {
      rec.start();
    } catch {
      resolve(null);
    }
  });

  return {
    promise,
    stop: () => rec.stop(),
    cancel: () => {
      cancelled = true;
      rec.abort();
    },
  };
}

// Tasks resolve with `null` on failure and carry the cause on the promise so
// callers can distinguish "nothing said" from "microphone blocked".
type PromiseWithError = Promise<unknown> & { _err?: unknown };

function attachError(promise: Promise<unknown>, err: unknown): void {
  (promise as PromiseWithError)._err = err;
}

/** Read the error a voice task attached when it resolved with `null`. */
export function taskError(task: VoiceTask<unknown>): Error | null {
  const err = (task.promise as PromiseWithError)._err;
  return err instanceof Error ? err : err ? new Error(String(err)) : null;
}

// ── Playback ───────────────────────────────────────────────────────────────

/** Speak with the browser's built-in voices. Resolves when playback ends. */
export function speakWithBrowser(text: string, lang: VoiceLanguage): VoiceTask<void> {
  if (!browserSynthesisSupported()) {
    return { promise: Promise.resolve(null), stop: () => {}, cancel: () => {} };
  }
  const synth = window.speechSynthesis;
  synth.cancel();
  const chunks = splitForSpeech(text);
  let cancelled = false;

  const pickVoice = () => {
    const voices = synth.getVoices();
    const base = shortLanguage(lang);
    return (
      voices.find((v) => v.lang.replace('_', '-') === lang) ??
      voices.find((v) => v.lang.toLowerCase().startsWith(base)) ??
      null
    );
  };

  const promise = new Promise<void | null>((resolve) => {
    if (chunks.length === 0) return resolve(null);
    const voice = pickVoice();
    let remaining = chunks.length;
    chunks.forEach((chunk) => {
      const u = new SpeechSynthesisUtterance(chunk);
      u.lang = lang;
      if (voice) u.voice = voice;
      u.rate = 1;
      u.onend = () => {
        remaining -= 1;
        if (remaining === 0) resolve(cancelled ? null : undefined);
      };
      u.onerror = () => {
        remaining -= 1;
        if (remaining === 0) resolve(null);
      };
      synth.speak(u);
    });
  });

  const cancel = () => {
    cancelled = true;
    synth.cancel();
  };
  return { promise, stop: cancel, cancel };
}

/** Play an audio blob returned by the server TTS engine. */
export function playAudioBlob(blob: Blob): VoiceTask<void> {
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  let cancelled = false;

  const promise = new Promise<void | null>((resolve) => {
    const finish = (ok: boolean) => {
      URL.revokeObjectURL(url);
      resolve(ok && !cancelled ? undefined : null);
    };
    audio.onended = () => finish(true);
    audio.onerror = () => finish(false);
    audio.play().catch(() => finish(false));
  });

  const cancel = () => {
    cancelled = true;
    audio.pause();
    audio.currentTime = 0;
    // Trigger onended-equivalent cleanup for a paused element.
    audio.dispatchEvent(new Event('ended'));
  };
  return { promise, stop: cancel, cancel };
}
