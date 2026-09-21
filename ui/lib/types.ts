// Types mirroring the complete ADAM Python backend schemas and domain models

export interface Citation {
  document_title: string;
  department: string;
  document_id?: string | null;
  go_number?: string | null;
  gazette_number?: string | null;
  version_hash: string;
  issue_date?: string | null;
  page: number;
  section?: string | null;
  source_url: string;
  retrieval_timestamp: string;
  pdf_page_link: string;
  bbox?: number[] | null;
  currency_banner?: string | null;
  disclaimer: string;
}

export type CurrencyStatus = 'CURRENT' | 'AMENDED' | 'SUPERSEDED' | 'UNCERTAIN';

export interface ChatTurn {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  cited_chunk_ids: string[];
  model_id?: string | null;
}

export interface SessionInfo {
  session_id: string;
  user_id: string;
  created_at: string;
  expires_at: string;
  is_active: boolean;
  turn_count: number;
}

export interface SttResult {
  transcript: string;
  language: string;
  confidence: number;
}

/** Mirrors GET /api/voice/status — which speech engines the server offers. */
export interface VoiceStatus {
  stt: { available: boolean; provider: string; engine: string };
  tts: { available: boolean; provider: string; engine: string; media_type: string };
}

/** Spoken-language setting shared by STT and TTS (BCP-47 tags). */
export type VoiceLanguage = 'hi-IN' | 'en-IN';

/** Phases of the hands-free voice conversation loop. */
export type VoicePhase = 'idle' | 'listening' | 'transcribing' | 'thinking' | 'speaking';

export interface ChatErrorDetails {
  title: string;
  message: string;
  category?: 'ollama_offline' | 'model_not_pulled' | 'gemini_key_missing' | 'gemini_api_error' | 'rate_limit' | 'network' | 'general';
  suggestedAction?: 'configure_gemini' | 'start_ollama' | 'pull_model' | 'retry' | 'switch_model';
  commandHint?: string | null;
  raw?: string;
}

export interface OperationalStatusEvent {
  sequence: number;
  type: string;
  stage: string;
  status: 'running' | 'completed' | 'warning' | 'failed';
  message: string;
  duration_ms?: number | null;
  timestamp: number;
  trace_id?: string;
  data?: {
    candidate_count?: number;
    selected_count?: number;
    records_considered?: number;
    duration_ms?: number;
    banner_count?: number;
    citation_count?: number;
    query_language?: string;
    is_out_of_jurisdiction?: boolean;
    is_high_risk?: boolean;
    model_name?: string;
    suggested_action?: string;
    command_hint?: string;
    [key: string]: string | number | boolean | null | undefined;
  };
}

export interface StateTransitionTrailItem {
  from: string;
  to: string;
  at: string;
  notes?: string | null;
  duration_ms?: number;
  stage?: string | null;
  abstention_reason?: string | null;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  banners?: string[];
  suggestions?: string[];
  isStreaming?: boolean;
  isNoAnswer?: boolean;
  isHighRisk?: boolean;
  modelId?: string;
  error?: ChatErrorDetails;
  operationalEvents?: OperationalStatusEvent[];
  stateHistory?: StateTransitionTrailItem[];
  perStageLatency?: Record<string, number>;
  abstentionReason?: string | null;
  latencyMs?: number;
}

export interface StreamCallbacks {
  onStart?: (sessionId: string, modelId: string) => void;
  onStatus?: (event: OperationalStatusEvent) => void;
  onTrail?: (trail: {
    state_history: StateTransitionTrailItem[];
    per_stage_latency?: Record<string, number>;
    abstention_reason?: string | null;
    latency_ms?: number;
  }) => void;
  onToken?: (text: string) => void;
  onCitations?: (citations: Citation[]) => void;
  onBanners?: (banners: string[]) => void;
  onSuggestions?: (suggestions: string[]) => void;
  onDone?: (meta: {
    latency_ms: number;
    validation_passed: boolean;
    is_no_answer: boolean;
    is_high_risk: boolean;
    state_history?: StateTransitionTrailItem[];
    per_stage_latency?: Record<string, number>;
    abstention_reason?: string | null;
  }) => void;
  onError?: (error: ChatErrorDetails | string) => void;
}

export interface AuditMetrics {
  total_executions: number;
  avg_latency_ms: number;
  avg_stage_latencies_ms: Record<string, number>;
  abstention_count: number;
  abstention_rate_pct: number;
  abstention_reasons: Record<string, number>;
}

// ── Model Registry Types ───────────────────────────────────────────────────

export interface ModelInfo {
  id: string;
  name: string;
  revision: string;
  quantization: string;
  file_size_mb: number;
  context_window: number;
  languages: string[];
  is_primary: boolean;
  is_fallback: boolean;
  is_comparator: boolean;
  license_id: string;
  license_status: string;
  requires_legal_review?: boolean;
  is_supported?: boolean;
  status: string;
  serving_runtime: string;
  is_installed: boolean;
  unavailable_reason?: string | null;
  is_cloud?: boolean;
}

// ── Controlled Vocabularies ────────────────────────────────────────────────

export interface DepartmentItem {
  id: string;
  label: string;
}

export interface VocabularyData {
  departments: DepartmentItem[];
  classifications: string[];
  doc_types: string[];
  precedent_types: string[];
}

// ── Document Repository Types ──────────────────────────────────────────────

export interface DocumentSummary {
  id: string;
  title: string;
  department_id: string;
  classification: string;
  doc_type: string;
  lifecycle_status: string;
  source_id: string;
  go_number?: string | null;
  issued_on?: string | null;
  version_id?: string | null;
  sha256?: string | null;
  provenance_status: string;
  page_count: number;
  created_at?: string | null;
}

export interface DocumentPageDetail {
  id: string;
  page_number: number;
  word_count: number;
  is_scanned: boolean;
  scan_quality_score?: number | null;
  detected_language: string;
  review_status: string;
  text_preview: string;
}

export interface DocumentDetail extends DocumentSummary {
  version?: {
    id?: string | null;
    go_number?: string | null;
    sha256?: string | null;
    provenance_status?: string | null;
    byte_size: number;
  } | null;
  attributes?: {
    subject?: string | null;
    issuing_authority_title?: string | null;
    signatory_name?: string | null;
    order_number?: string | null;
    order_date?: string | null;
  } | null;
  pages: DocumentPageDetail[];
  precedents: Array<{
    id: string;
    raw_citation_text: string;
    cited_order_number?: string | null;
    cited_act_or_rule?: string | null;
    relation_type: string;
  }>;
}

// ── Precedent Reference Types ──────────────────────────────────────────────

export interface PrecedentItem {
  id: string;
  source_document_id?: string | null;
  source_title: string;
  source_go_number?: string | null;
  source_department_id?: string | null;
  relation_type: string;
  cited_order_number?: string | null;
  cited_act_or_rule?: string | null;
  target_document_id?: string | null;
  target_title?: string | null;
  raw_citation_text: string;
  created_at?: string | null;
}

// ── Sources & Ingestion Types ──────────────────────────────────────────────

export interface SourceItem {
  id: string;
  name: string;
  department_id: string;
  owner_name: string;
  permitted_domains: string[];
  base_url: string;
  status: string;
  refresh_cadence: string;
  access_classification: string;
  document_count: number;
  created_at?: string | null;
}

// ── Audit & Diagnostics Types ──────────────────────────────────────────────

export interface AuditRecord {
  id: string;
  session_id: string;
  user_id: string;
  user_role: string;
  clearance_level: string;
  query_text: string;
  model_id?: string | null;
  retrieval_pass_count: number;
  answer_pass_count: number;
  is_no_answer: boolean;
  is_high_risk: boolean;
  validation_passed: boolean;
  latency_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  state_transitions: Array<{
    timestamp: string;
    from_state: string;
    to_state: string;
    trigger: string;
  }>;
  tool_calls: Array<{
    tool: string;
    arguments: Record<string, unknown>;
  }>;
  created_at?: string | null;
}

// ── Human-in-the-loop Review QA Types ──────────────────────────────────────

export interface ReviewPageItem {
  id: string;
  version_id: string;
  document_id?: string | null;
  document_title: string;
  go_number?: string | null;
  page_number: number;
  word_count: number;
  is_scanned: boolean;
  text_confidence?: number | null;
  review_status: string;
  clean_text: string;
  ocr_text: string;
  selected_text: string;
}

// ── User Context & Preferences ─────────────────────────────────────────────

export interface UserProfile {
  user_id: string;
  roles: string[];
  department_id?: string | null;
  clearance_level: string;
  is_admin: boolean;
}

export interface UserPreferenceData {
  opt_in: boolean;
  purpose?: string | null;
  preferences: Record<string, unknown>;
  updated_at?: string | null;
}
