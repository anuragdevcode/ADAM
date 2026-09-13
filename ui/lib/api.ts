import type {
  AuditRecord,
  Citation,
  ChatTurn,
  DocumentDetail,
  DocumentSummary,
  ModelInfo,
  PrecedentItem,
  ReviewPageItem,
  SessionInfo,
  SourceItem,
  SttResult,
  StreamCallbacks,
  UserProfile,
  UserPreferenceData,
  VocabularyData,
} from './types';

const API_BASE = '/api';
const GEMINI_API_KEY_STORAGE_KEY = 'adam_gemini_api_key';

export function getStoredGeminiApiKey(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return localStorage.getItem(GEMINI_API_KEY_STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setStoredGeminiApiKey(key: string): void {
  if (typeof window === 'undefined') return;
  try {
    if (key && key.trim()) {
      localStorage.setItem(GEMINI_API_KEY_STORAGE_KEY, key.trim());
    } else {
      localStorage.removeItem(GEMINI_API_KEY_STORAGE_KEY);
    }
  } catch {}
}

export function clearStoredGeminiApiKey(): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem(GEMINI_API_KEY_STORAGE_KEY);
  } catch {}
}

/**
 * Stream a chat query using SSE (Server-Sent Events) via fetch.
 * Passes model_id, department_id, and optional geminiApiKey for backend scoping.
 */
export async function streamChat(
  query: string,
  sessionId: string | null,
  userId: string,
  options: {
    userRole?: string;
    clearanceLevel?: string;
    departmentId?: string | null;
    modelId?: string | null;
    geminiApiKey?: string | null;
  } = {},
  callbacks: StreamCallbacks = {},
  signal?: AbortSignal,
): Promise<void> {
  let response: Response;
  const geminiKey = options.geminiApiKey || getStoredGeminiApiKey();
  try {
    response = await fetch(`${API_BASE}/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-User-Id': userId,
        'X-User-Role': options.userRole || 'OFFICER',
        'X-Clearance-Level': options.clearanceLevel || 'PUBLIC',
        ...(options.departmentId ? { 'X-Department-Id': options.departmentId } : {}),
        ...(geminiKey ? { 'X-Gemini-Api-Key': geminiKey } : {}),
      },
      body: JSON.stringify({
        query,
        session_id: sessionId,
        model_id: options.modelId || null,
        department_id: options.departmentId || null,
        api_key: geminiKey || null,
      }),
      signal,
    });
  } catch (err) {
    callbacks.onError?.(`Network error: ${err}`);
    return;
  }

  if (!response.ok) {
    callbacks.onError?.(`Server error: ${response.status}`);
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    callbacks.onError?.('No response body');
    return;
  }

  const decoder = new TextDecoder();
  let buffer = '';
  let currentEvent = '';

  while (true) {
    let done: boolean;
    let value: Uint8Array | undefined;
    try {
      ({ done, value } = await reader.read());
    } catch {
      break;
    }
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        const rawData = line.slice(6).trim();
        try {
          const data = JSON.parse(rawData);
          switch (currentEvent) {
            case 'start':
              callbacks.onStart?.(data.session_id, data.model_id);
              break;
            case 'token':
              callbacks.onToken?.(data.text);
              break;
            case 'citations':
              callbacks.onCitations?.(data as Citation[]);
              break;
            case 'banners':
              callbacks.onBanners?.(data as string[]);
              break;
            case 'suggestions':
              callbacks.onSuggestions?.(data as string[]);
              break;
            case 'done':
              callbacks.onDone?.(data);
              break;
            case 'error':
              callbacks.onError?.(data.message);
              break;
          }
        } catch {
          // ignore malformed lines
        }
        currentEvent = '';
      }
    }
  }
}

// ── Sessions & Conversation History ────────────────────────────────────────

export async function listSessions(userId: string): Promise<SessionInfo[]> {
  try {
    const resp = await fetch(`${API_BASE}/sessions?user_id=${encodeURIComponent(userId)}`);
    if (!resp.ok) return [];
    return resp.json();
  } catch {
    return [];
  }
}

export async function getSessionHistory(sessionId: string, userId: string): Promise<ChatTurn[]> {
  const resp = await fetch(`${API_BASE}/sessions/${sessionId}/history`, {
    headers: { 'X-User-Id': userId },
  });
  if (!resp.ok) throw new Error(`Failed to load history: ${resp.status}`);
  const data = await resp.json();
  return data.turns ?? [];
}

export async function deleteSession(sessionId: string, userId: string): Promise<boolean> {
  const resp = await fetch(`${API_BASE}/sessions/${sessionId}`, {
    method: 'DELETE',
    headers: { 'X-User-Id': userId },
  });
  return resp.ok;
}

// ── Voice Input & Output ───────────────────────────────────────────────────

export async function transcribeAudio(
  audioBlob: Blob,
  languageHint: string = 'hi',
  apiKey?: string | null,
): Promise<SttResult> {
  const form = new FormData();
  form.append('file', audioBlob, 'recording.webm');
  form.append('language_hint', languageHint);
  const geminiKey = apiKey || getStoredGeminiApiKey();
  if (geminiKey) {
    form.append('api_key', geminiKey);
  }
  const resp = await fetch(`${API_BASE}/voice/transcribe`, {
    method: 'POST',
    headers: geminiKey ? { 'X-Gemini-Api-Key': geminiKey } : {},
    body: form,
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    throw new Error(body?.error?.message || body?.detail || `Transcription failed: ${resp.status}`);
  }
  return resp.json();
}

export async function synthesizeSpeech(
  text: string,
  language: string = 'hi',
  apiKey?: string | null,
): Promise<Blob> {
  const geminiKey = apiKey || getStoredGeminiApiKey();
  const resp = await fetch(`${API_BASE}/voice/synthesize`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(geminiKey ? { 'X-Gemini-Api-Key': geminiKey } : {}),
    },
    body: JSON.stringify({ text, language }),
  });
  if (!resp.ok) {
    const body = await resp.json().catch(() => null);
    throw new Error(body?.error?.message || body?.detail || `Synthesis failed: ${resp.status}`);
  }
  return resp.blob();
}

// ── System Metadata & Vocabularies ─────────────────────────────────────────

export async function fetchModels(apiKey?: string | null): Promise<ModelInfo[]> {
  try {
    const geminiKey = apiKey || getStoredGeminiApiKey();
    const resp = await fetch(`${API_BASE}/system/models`, {
      headers: geminiKey ? { 'X-Gemini-Api-Key': geminiKey } : {},
    });
    if (!resp.ok) return [];
    return resp.json();
  } catch {
    return [];
  }
}

export async function validateGeminiKey(
  apiKey: string,
): Promise<{ valid: boolean; message: string; available_models?: string[] }> {
  try {
    const resp = await fetch(`${API_BASE}/system/validate-gemini-key`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: apiKey }),
    });
    if (!resp.ok) {
      return { valid: false, message: `Server error: ${resp.status}` };
    }
    return resp.json();
  } catch (err) {
    return { valid: false, message: `Network error: ${err}` };
  }
}

export async function fetchVocabularies(): Promise<VocabularyData> {
  try {
    const resp = await fetch(`${API_BASE}/system/vocabularies`);
    if (!resp.ok) {
      return { departments: [], classifications: [], doc_types: [], precedent_types: [] };
    }
    return resp.json();
  } catch {
    return { departments: [], classifications: [], doc_types: [], precedent_types: [] };
  }
}

// ── Document Repository ────────────────────────────────────────────────────

export async function fetchDocuments(
  params: {
    departmentId?: string | null;
    classification?: string | null;
    docType?: string | null;
    search?: string | null;
    limit?: number;
    offset?: number;
  } = {},
  headers: {
    userId?: string;
    clearanceLevel?: string;
  } = {},
): Promise<{ items: DocumentSummary[]; total: number }> {
  try {
    const query = new URLSearchParams();
    if (params.departmentId && params.departmentId !== 'ALL') query.set('department_id', params.departmentId);
    if (params.classification && params.classification !== 'ALL') query.set('classification', params.classification);
    if (params.docType && params.docType !== 'ALL') query.set('doc_type', params.docType);
    if (params.search) query.set('search', params.search);
    if (params.limit) query.set('limit', String(params.limit));
    if (params.offset) query.set('offset', String(params.offset));

    const resp = await fetch(`${API_BASE}/documents?${query.toString()}`, {
      headers: {
        'X-User-Id': headers.userId || 'anonymous',
        'X-Clearance-Level': headers.clearanceLevel || 'PUBLIC',
      },
    });
    if (!resp.ok) return { items: [], total: 0 };
    return resp.json();
  } catch {
    return { items: [], total: 0 };
  }
}

export async function fetchDocumentDetails(
  documentId: string,
  headers: {
    userId?: string;
    clearanceLevel?: string;
  } = {},
): Promise<DocumentDetail> {
  const resp = await fetch(`${API_BASE}/documents/${documentId}`, {
    headers: {
      'X-User-Id': headers.userId || 'anonymous',
      'X-Clearance-Level': headers.clearanceLevel || 'PUBLIC',
    },
  });
  if (!resp.ok) throw new Error(`Document fetch failed: ${resp.status}`);
  return resp.json();
}

export async function uploadDocument(
  formData: FormData,
  headers: {
    userId?: string;
    clearanceLevel?: string;
  } = {},
): Promise<{ success: boolean; document_id: string; title: string }> {
  const resp = await fetch(`${API_BASE}/documents/upload`, {
    method: 'POST',
    headers: {
      'X-User-Id': headers.userId || 'officer',
      'X-Clearance-Level': headers.clearanceLevel || 'PUBLIC',
    },
    body: formData,
  });
  if (!resp.ok) {
    const errData = await resp.json().catch(() => ({ detail: 'Upload failed' }));
    throw new Error(errData.detail || `Upload failed: ${resp.status}`);
  }
  return resp.json();
}

// ── Precedents ─────────────────────────────────────────────────────────────

export async function fetchPrecedents(relationType?: string, search?: string): Promise<PrecedentItem[]> {
  try {
    const query = new URLSearchParams();
    if (relationType && relationType !== 'ALL') query.set('relation_type', relationType);
    if (search) query.set('search', search);

    const resp = await fetch(`${API_BASE}/precedents?${query.toString()}`);
    if (!resp.ok) return [];
    return resp.json();
  } catch {
    return [];
  }
}

// ── Data Sources ───────────────────────────────────────────────────────────

export async function fetchSources(): Promise<SourceItem[]> {
  try {
    const resp = await fetch(`${API_BASE}/sources`);
    if (!resp.ok) return [];
    return resp.json();
  } catch {
    return [];
  }
}

export async function toggleSourceStatus(sourceId: string, userId: string = 'admin'): Promise<SourceItem> {
  const resp = await fetch(`${API_BASE}/sources/${sourceId}/toggle-status`, {
    method: 'POST',
    headers: { 'X-User-Id': userId },
  });
  if (!resp.ok) throw new Error(`Failed to toggle source status: ${resp.status}`);
  return resp.json();
}

// ── Agent Audit Logs ───────────────────────────────────────────────────────

export async function fetchExecutionAudits(limit: number = 50): Promise<AuditRecord[]> {
  try {
    const resp = await fetch(`${API_BASE}/audit/executions?limit=${limit}`);
    if (!resp.ok) return [];
    return resp.json();
  } catch {
    return [];
  }
}

// ── Review & Human-in-the-Loop QA ──────────────────────────────────────────

export async function fetchReviewPages(status?: string): Promise<ReviewPageItem[]> {
  try {
    const query = status ? `?status=${encodeURIComponent(status)}` : '';
    const resp = await fetch(`${API_BASE}/review/pages${query}`);
    if (!resp.ok) return [];
    return resp.json();
  } catch {
    return [];
  }
}

export async function approveReviewPage(pageId: string, reviewerId: string = 'officer'): Promise<boolean> {
  const resp = await fetch(`${API_BASE}/review/pages/${pageId}/approve`, {
    method: 'POST',
    headers: { 'X-User-Id': reviewerId },
  });
  return resp.ok;
}

export async function correctReviewPage(
  pageId: string,
  correctedText: string,
  reviewerId: string = 'officer',
): Promise<boolean> {
  const resp = await fetch(`${API_BASE}/review/pages/${pageId}/correct`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': reviewerId,
    },
    body: JSON.stringify({ corrected_text: correctedText, reviewer: reviewerId }),
  });
  return resp.ok;
}

// ── User Profile & Preferences ─────────────────────────────────────────────

export async function fetchUserProfile(
  userId: string,
  clearanceLevel: string = 'PUBLIC',
  departmentId?: string | null,
): Promise<UserProfile> {
  const resp = await fetch(`${API_BASE}/user/profile`, {
    headers: {
      'X-User-Id': userId,
      'X-Clearance-Level': clearanceLevel,
      ...(departmentId ? { 'X-Department-Id': departmentId } : {}),
    },
  });
  if (!resp.ok) throw new Error('Failed to load profile');
  return resp.json();
}

export async function fetchUserPreferences(userId: string): Promise<UserPreferenceData> {
  try {
    const resp = await fetch(`${API_BASE}/user/preferences`, {
      headers: { 'X-User-Id': userId },
    });
    if (!resp.ok) return { opt_in: false, preferences: {} };
    return resp.json();
  } catch {
    return { opt_in: false, preferences: {} };
  }
}

export async function saveUserPreferences(
  userId: string,
  optIn: boolean,
  purpose: string,
  preferences: Record<string, unknown>,
): Promise<boolean> {
  const resp = await fetch(`${API_BASE}/user/preferences`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-User-Id': userId,
    },
    body: JSON.stringify({ opt_in: optIn, purpose, preferences }),
  });
  return resp.ok;
}
