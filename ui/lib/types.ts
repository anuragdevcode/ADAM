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
  air_gapped_restricted?: boolean;
  source?: 'canonical' | 'discovered';
  attestation_status?: 'approved' | 'limited' | 'checking' | 'unavailable' | null;
  attestation_version?: string | null;
  capabilities?: {
    streaming?: boolean;
    structured_output?: boolean;
    hindi?: boolean;
    english?: boolean;
    citation_format?: boolean;
    instruction_following?: boolean;
    tool_calling?: boolean;
  } | null;
  display_group?: 'LOCAL' | 'REMOTE';
  provider_display?: string;
}

export interface ProviderRegistrationRequest {
  name: string;
  endpoint_url: string;
  display_name?: string;
}

export interface ProviderRegistrationResult {
  provider_id: string;
  display_name: string;
  protocol: string;
  status: string;
  models: ModelInfo[];
}

export interface ModelDiscoveryResult {
  discovered_count: number;
  new_models: ModelInfo[];
  canonical_skipped: number;
  message: string;
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
  owner_contact?: string;
  source_type?: 'WEBSITE' | 'DATABASE' | 'FILE_UPLOAD' | 'CUSTOM' | string;
  permitted_domains: string[];
  permitted_path_prefixes?: string[];
  base_url: string;
  config_json?: Record<string, unknown>;
  status: string;
  refresh_cadence: string;
  rate_limit_per_minute?: number;
  access_classification: string;
  document_count: number;
  last_run_at?: string | null;
  last_run_status?: string | null;
  active_job_id?: string | null;
  active_job_status?: string | null;
  created_at?: string | null;
}

export interface SourcePreset {
  preset_id: string;
  name: string;
  connector_id: string;
  connector_class: string;
  source_type: string;
  department_id: string;
  department_name: string;
  permitted_domains: string[];
  permitted_path_prefixes: string[];
  base_url: string;
  description: string;
  rate_limit_per_minute: number;
  refresh_cadence: string;
  access_classification: string;
  batch_dir?: string;
}

export interface IngestionJobItemRecord {
  id: string;
  source_id: string;
  source_name: string;
  status: 'QUEUED' | 'DISCOVERY' | 'PROCESSING' | 'DRAINING' | 'PAUSED' | 'CANCELLING' | 'CANCELLED' | 'COMPLETED' | 'PARTIAL_SUCCESS' | 'FAILED' | string;
  job_type: 'FULL' | 'INCREMENTAL' | 'RETRY' | string;
  current_stage: string;
  count_found: number;
  count_ingested: number;
  count_skipped: number;
  count_failed: number;
  progress_pct: number;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
}

export interface IngestionJobDetail extends IngestionJobItemRecord {
  checkpoint?: Record<string, unknown>;
  failures?: Array<{ item_key: string; error: string; timestamp: string }>;
  metrics?: Record<string, unknown>;
}

export interface IngestionItemDetail {
  id: string;
  item_key: string;
  title?: string | null;
  status: 'PENDING' | 'PROCESSING' | 'SUCCESS' | 'SKIPPED' | 'FAILED' | string;
  sha256?: string | null;
  document_id?: string | null;
  version_id?: string | null;
  error_message?: string | null;
  retry_count: number;
  duration_ms?: number | null;
  created_at?: string | null;
}

export interface PaginatedJobItemsResponse {
  job_id: string;
  total: number;
  page: number;
  page_size: number;
  items: IngestionItemDetail[];
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

export interface RagBenchmarkData {
  total_queries: number;
  answer_bearing_queries: number;
  recall_at_10: number;
  recall_at_10_target?: number;
  citation_page_precision: number;
  citation_page_precision_target?: number;
  no_answer_refusal_rate: number;
  no_answer_refusal_target?: number;
  acl_leak_count: number;
  acl_leak_target?: number;
  gate_passed: boolean;
  by_department: Record<string, { total: number; accuracy: number }>;
  by_language: Record<string, { total: number; accuracy: number }>;
  reranker_ablation?: {
    pure_rrf_recall_at_10: number;
    pure_rrf_precision: number;
    pure_rrf_latency_ms: number;
    reranker_recall_at_10: number;
    reranker_precision: number;
    reranker_latency_ms: number;
    parity_achieved: boolean;
    decision: string;
  };
}

// ── System Introspection & Self-Model Types ─────────────────────────────────

export interface SystemInfoSnapshot {
  name: string;
  version: string;
  jurisdiction: string;
  air_gapped: boolean;
  environment: string;
  current_time_utc: string;
}

export interface ActiveModelSnapshot {
  id: string;
  name: string;
  family: string;
  serving_runtime: string;
  quantization: string;
  context_window: number;
  memory_footprint_mb: number;
  is_loaded: boolean;
  is_cloud: boolean;
  air_gapped_restricted: boolean;
  supports_reasoning: boolean;
  backend_resolved: string;
}

export interface ActiveHarnessSnapshot {
  profile_name: string;
  family_name: string;
  temperature_range: number[];
  max_tokens_budget: number;
  thinking_enabled: boolean;
  thinking_budget: number;
  stop_sequences: string[];
}

export interface ToolCapabilitySnapshot {
  allowed_tools: Array<{
    name: string;
    description: string;
    parameters: string[];
  }>;
  forbidden_tools: string[];
  guardrail_invariants: string[];
}

export interface DataSourceSnapshot {
  total_sources: number;
  total_documents: number;
  total_chunks: number;
  approved_connectors: string[];
  registered_departments: string[];
}

export interface WorkerConcurrencySnapshot {
  is_busy: boolean;
  active_task: string | null;
  active_task_id: string | null;
  elapsed_seconds: number;
  mutual_exclusion_enforced: boolean;
  active_ingestion_jobs: number;
}

export interface LastExecutionSnapshot {
  session_id: string | null;
  query_text_redacted: string | null;
  detected_intent: string | null;
  model_id: string | null;
  total_latency_ms: number;
  per_stage_latency_ms: Record<string, number>;
  was_refused: boolean;
  refusal_reason: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  validation_passed: boolean;
  validation_errors: string[];
  tool_calls: Array<Record<string, unknown>>;
  timestamp: string | null;
}

export interface SystemSnapshot {
  system_info: SystemInfoSnapshot;
  active_model: ActiveModelSnapshot;
  active_harness: ActiveHarnessSnapshot;
  tool_capabilities: ToolCapabilitySnapshot;
  data_sources: DataSourceSnapshot;
  worker_concurrency: WorkerConcurrencySnapshot;
  last_execution: LastExecutionSnapshot | null;
}

// ── Advanced Settings Types ────────────────────────────────────────────────────

export type AdvancedSettingsPreset = 'PRECISE' | 'BALANCED' | 'THOROUGH' | 'CUSTOM';

export interface GenerationSettings {
  temperature_rag: number;
  temperature_conversational: number;
  max_tokens_rag: number;
  max_tokens_conversational: number;
  top_p: number;
  top_k_sampling: number;
  min_p: number;
  context_size: number;
  max_rag_prompt_passages: number;
  thinking_enabled: boolean;
  thinking_budget: number;
}

export interface RetrievalSettings {
  top_k: number;
  enable_rerank: boolean;
  bm25_weight: number;
  vector_min_similarity: number;
  min_score_threshold: number;
  min_passages: number;
  max_passages: number;
}

export interface PerformanceSettings {
  environment_profile: 'MACBOOK_AIR_8GB' | 'DEV_SERVER' | 'GOV_PRODUCTION';
  cache_ttl_seconds: number;
  cache_max_entries: number;
}

export interface VoiceSettings {
  default_voice_language: 'hi' | 'en' | 'hi-en';
  tts_enabled_default: boolean;
}

export interface AdvancedSettingsBundle {
  preset: AdvancedSettingsPreset;
  generation: GenerationSettings;
  retrieval: RetrievalSettings;
  performance: PerformanceSettings;
  voice: VoiceSettings;
}

export interface SettingFieldMetadata {
  label: string;
  description: string;
  type: 'float' | 'int' | 'bool' | 'enum';
  min?: number;
  max?: number;
  step?: number;
  options?: Array<{ value: string; label: string }>;
  impact: 'accuracy' | 'speed' | 'memory';
  default: number | boolean | string;
}

export interface AdvancedSettingsResponse {
  current: AdvancedSettingsBundle;
  defaults: AdvancedSettingsBundle;
  presets: Record<AdvancedSettingsPreset, AdvancedSettingsBundle>;
  metadata: Record<string, SettingFieldMetadata>;
}
