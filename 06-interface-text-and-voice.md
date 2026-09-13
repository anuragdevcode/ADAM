# 04 — Interface: Text Chat & Voice

**Goal of this module:** a ChatGPT-style interface for officers, with text chat as the reliable core and voice (speech-to-text, text-to-speech, and eventually speech-to-speech) as an added mode — built in that order, not simultaneously.

Build and stabilize text chat completely before starting voice. Voice adds a whole new failure surface (audio quality, accent handling, latency) on top of an already complex retrieval+generation pipeline — debugging both at once makes it hard to tell which layer broke.

---

## 1. Text interface (build first)

- [ ] Web app: Next.js/React frontend, streaming responses (token-by-token, like ChatGPT) from the Module 03 agent.
- [ ] Every answer renders with visible **citation cards**: GO number, department, date, and a link/preview to the source document (ideally with the specific paragraph highlighted, using the bounding-box data from Module 01's OCR step if available).
- [ ] Superseded/amended GOs shown with a clear status badge, not buried in prose.
- [ ] "Related GOs" suggestions (from Module 03) shown as a distinct, lower-emphasis section — officers should never confuse a suggestion with a direct answer.
- [ ] Conversation history visible and scrollable, consistent with the Mem0-backed session memory from Module 03.

## 2. Speech-to-text (voice input)

- [x] **faster-whisper** (CTranslate2 reimplementation of Whisper — up to 4x faster, lower memory) for general transcription. Hosted **Groq Whisper** (`GROQ_API_KEY`, free tier) is preferred when configured; the browser Web Speech API is the zero-setup fallback.
- [ ] If Hindi-accented officer speech is a priority, evaluate **IndicWhisper** (AI4Bharat's Whisper fine-tunes for Indian languages) against plain Whisper on real sample audio before committing to one.
- [ ] Local dev: `faster-whisper` small/medium model runs fine on CPU on the MacBook Air for testing; don't expect real-time streaming transcription on 8GB RAM — batch/chunked transcription is fine for a demo.

## 3. Text-to-speech (voice output)

- [ ] **AI4Bharat Indic-TTS** (FastPitch + HiFi-GAN, Apache 2.0) for natural Hindi voice responses — purpose-built for Indian languages rather than adapted from English TTS.
- [x] For English-only responses or as a lightweight fallback, **Piper TTS** is a good low-resource option. Hosted **ElevenLabs** (`ELEVENLABS_API_KEY`, free tier, Hindi + English) is preferred when configured; browser `speechSynthesis` is the zero-setup fallback.
- [x] Read back only the answer text, not the full citation metadata — citations stay visual (Section 1), not spoken, to keep voice responses natural.

## 4. Speech-to-speech (natural conversation mode) — phase 2

- [ ] Only attempt this after text chat and one-directional voice (STT-only or TTS-only) are both stable.
- [x] Pipeline: STT → Module 03 agent → TTS, chained with a latency budget in mind — each hop adds delay, and a government-official-facing tool needs to feel responsive, not laggy.
- [x] Consider a "typing/thinking" audio or visual cue during the retrieval+generation step so the wait doesn't feel broken.
- [x] Explicitly test interruption handling (officer starts talking while TTS is still playing) — decide on a simple behavior (e.g. new input cancels current playback) rather than leaving it undefined. Implemented: the mic is muted while ADAM speaks (no echo); tapping the mic cancels playback and returns to listening.

## 5. Step-by-step build order

1. [ ] Build the text chat UI against a mocked/static agent response first, to get streaming and citation rendering right independently.
2. [ ] Connect to the real Module 03 agent.
3. [ ] Add conversation history + Mem0-backed session continuity in the UI.
4. [x] Add speech-to-text input as an additive feature (mic button → transcribed text → same text pipeline).
5. [x] Add text-to-speech output as an additive feature (answer text → audio playback), toggleable.
6. [x] Only then attempt full speech-to-speech mode, with latency and interruption handling addressed explicitly.

## 6. Definition of done for this module

- An officer can type a question and get a cited, streamed answer with correctly rendered source references.
- Voice input and output work as optional, independently-toggleable modes without degrading the text experience.
