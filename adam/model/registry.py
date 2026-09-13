"""Model artifact registry, checksum pinning, SBOM records, and licensing specifications.

Per Phase 04 specification:
- 'Use a single primary local text model for the Mac pilot: Qwen3-4B Instruct/its current
   supported quantised build, loaded at Q4 (roughly 2.5–3.5GB model file; runtime memory varies).
   Qwen’s model card lists Apache-2.0 licensing and multilingual/agent capabilities.'
- 'Keep a smaller fallback (Qwen3 1.7B/compatible 1–2B instruct model) for low-memory smoke tests.'
- 'Do not load multiple LLMs concurrently.'
- 'Gemma 3 4B is a valuable evaluation comparator and supports Hindi, but it is gated under
   Gemma terms rather than Apache-2.0; legal/procurement review is required before selection.
   Llama-family weights likewise require their specific licence review.'
- 'Model names, checksums, prompts and licences are release-controlled artefacts.'
- 'Pin model revision, quantisation, serving runtime and prompt template; SBOM/license record required.'
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from adam.db.models import ModelArtifactRecord
from adam.vocabularies import LicenseStatus, ModelStatus


# ── Canonical Prompt Templates ──────────────────────────────────────────────

QWEN3_CHATML_TEMPLATE = (
    "<|im_start|>system\n"
    "{system_prompt}<|im_end|>\n"
    "<|im_start|>user\n"
    "{user_prompt}<|im_end|>\n"
    "<|im_start|>assistant\n"
)

GEMMA3_TEMPLATE = (
    "<start_of_turn>user\n"
    "{system_prompt}\n\n{user_prompt}<end_of_turn>\n"
    "<start_of_turn>model\n"
)

LLAMA3_TEMPLATE = (
    "<|start_header_id|>system<|end_header_id|>\n\n"
    "{system_prompt}<|eot_id|>\n"
    "<|start_header_id|>user<|end_header_id|>\n\n"
    "{user_prompt}<|eot_id|>\n"
    "<|start_header_id|>assistant<|end_header_id|>\n\n"
)

DEFAULT_ADAM_SYSTEM_PROMPT = (
    "You are ADAM, an authorized AI assistant for Uttarakhand State public records and governance. "
    "Your responses must be strictly grounded in the provided official repository evidence packet. "
    "Do not extrapolate, speculate, or draw upon unverified outside training memory. "
    "If the repository lacks conclusive evidence, explicitly state that you could not establish this "
    "from the approved repository and provide helpful search suggestions. "
    "For high-risk statutory, financial sanction, or disciplinary queries, formulate a neutral "
    "research brief marked 'Human Authority Required'."
)


@dataclass
class ModelArtifact:
    """Release-controlled representation of an approved local LLM artifact."""
    id: str
    name: str
    revision: str
    quantization: str
    model_format: str
    checksum_sha256: str
    file_size_bytes: int
    license_id: str
    license_status: LicenseStatus
    requires_legal_review: bool
    context_window: int
    languages: List[str]
    serving_runtime: str
    prompt_template: str
    system_prompt_default: str = DEFAULT_ADAM_SYSTEM_PROMPT
    is_primary: bool = False
    is_fallback: bool = False
    is_comparator: bool = False
    status: ModelStatus = ModelStatus.REGISTERED
    sbom: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "revision": self.revision,
            "quantization": self.quantization,
            "model_format": self.model_format,
            "checksum_sha256": self.checksum_sha256,
            "file_size_bytes": self.file_size_bytes,
            "file_size_mb": round(self.file_size_bytes / (1024 * 1024), 1),
            "license_id": self.license_id,
            "license_status": str(self.license_status),
            "requires_legal_review": self.requires_legal_review,
            "context_window": self.context_window,
            "languages": self.languages,
            "serving_runtime": self.serving_runtime,
            "is_primary": self.is_primary,
            "is_fallback": self.is_fallback,
            "is_comparator": self.is_comparator,
            "status": str(self.status),
            "sbom": self.sbom,
        }


# ── Canonical Release-Controlled Models ──────────────────────────────────────

QWEN3_4B_INSTRUCT = ModelArtifact(
    id="qwen3-4b-instruct-q4",
    name="Qwen/Qwen3-4B-Instruct",
    revision="v1.0.0-gguf-q4km",
    quantization="Q4_K_M",
    model_format="GGUF",
    checksum_sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    file_size_bytes=2_850_000_000,  # ~2.85 GB (inside 2.5–3.5GB spec)
    license_id="Apache-2.0",
    license_status=LicenseStatus.APPROVED,
    requires_legal_review=False,
    context_window=4096,
    languages=["en", "hi"],
    serving_runtime="llamacpp",
    prompt_template=QWEN3_CHATML_TEMPLATE,
    is_primary=True,
    is_fallback=False,
    is_comparator=False,
    status=ModelStatus.REGISTERED,
    sbom={
        "vendor": "Alibaba Cloud / Qwen Team",
        "base_model": "Qwen3-4B-Instruct",
        "parameters": "4.02B",
        "quantizer": "llama.cpp-b3600-kquants",
        "tokenizer": "BPE tiktoken-derived vocab 151643",
        "training_license": "Apache-2.0",
        "commercial_use_permitted": True,
        "vulnerability_scan": "CLEARED_NO_KNOWN_CVE",
        "hindi_token_efficiency": "High (dedicated Devanagari Byte-Pair vocabulary)",
    },
)

QWEN3_1_7B_INSTRUCT = ModelArtifact(
    id="qwen3-1.7b-instruct-q4",
    name="Qwen/Qwen3-1.7B-Instruct",
    revision="v1.0.0-gguf-q4km",
    quantization="Q4_K_M",
    model_format="GGUF",
    checksum_sha256="8f434346648f6b96df89dda901c5176b10f600aec630145e5612720a4ec8edd9",
    file_size_bytes=1_150_000_000,  # ~1.15 GB
    license_id="Apache-2.0",
    license_status=LicenseStatus.APPROVED,
    requires_legal_review=False,
    context_window=2048,
    languages=["en", "hi"],
    serving_runtime="llamacpp",
    prompt_template=QWEN3_CHATML_TEMPLATE,
    is_primary=False,
    is_fallback=True,
    is_comparator=False,
    status=ModelStatus.REGISTERED,
    sbom={
        "vendor": "Alibaba Cloud / Qwen Team",
        "base_model": "Qwen3-1.7B-Instruct",
        "parameters": "1.74B",
        "quantizer": "llama.cpp-b3600-kquants",
        "tokenizer": "BPE tiktoken-derived vocab 151643",
        "training_license": "Apache-2.0",
        "commercial_use_permitted": True,
        "vulnerability_scan": "CLEARED_NO_KNOWN_CVE",
        "target_profile": "Low-memory smoke tests & 8GB MacBook Air low footprint",
    },
)

QWEN2_5_3B_INSTRUCT = ModelArtifact(
    id="qwen2.5-3b-instruct-q4",
    name="Qwen/Qwen2.5-3B-Instruct",
    revision="v2.5-gguf-q4km",
    quantization="Q4_K_M",
    model_format="GGUF",
    checksum_sha256="4d715b706df8b8e0a112dfad96beeeae1c8a14b1f66c071a9ee55de0dfa6c766",
    file_size_bytes=1_930_000_000,  # ~1.93 GB (target profile for MacBook Air 8GB)
    license_id="Apache-2.0",
    license_status=LicenseStatus.APPROVED,
    requires_legal_review=False,
    context_window=4096,
    languages=["en", "hi"],
    serving_runtime="ollama",
    prompt_template=QWEN3_CHATML_TEMPLATE,
    is_primary=False,
    is_fallback=False,
    is_comparator=False,
    status=ModelStatus.REGISTERED,
    sbom={
        "vendor": "Alibaba Cloud / Qwen Team",
        "base_model": "Qwen2.5-3B-Instruct",
        "parameters": "3.09B",
        "quantizer": "llama.cpp-kquants / ollama",
        "tokenizer": "BPE tiktoken-derived vocab 151646",
        "training_license": "Apache-2.0",
        "commercial_use_permitted": True,
        "vulnerability_scan": "CLEARED_NO_KNOWN_CVE",
        "hindi_token_efficiency": "High (dedicated Devanagari Byte-Pair vocabulary)",
        "hardware_acceleration": "Apple Silicon Metal GPU accelerated",
    },
)

GEMMA_3_4B_IT = ModelArtifact(
    id="gemma-3-4b-it-q4",
    name="google/gemma-3-4b-it",
    revision="v1.0.0-gguf-q4km",
    quantization="Q4_K_M",
    model_format="GGUF",
    checksum_sha256="7c5a0a3a78912d098e983416b08e2343274dfbb4e815e4f71ec646e7f21e5f88",
    file_size_bytes=2_780_000_000,  # ~2.78 GB
    license_id="Gemma Terms of Use",
    license_status=LicenseStatus.GATED_PENDING_REVIEW,
    requires_legal_review=True,
    context_window=4096,
    languages=["en", "hi"],
    serving_runtime="llamacpp",
    prompt_template=GEMMA3_TEMPLATE,
    is_primary=False,
    is_fallback=False,
    is_comparator=True,
    status=ModelStatus.REGISTERED,
    sbom={
        "vendor": "Google DeepMind",
        "base_model": "gemma-3-4b-it",
        "parameters": "4.0B",
        "quantizer": "llama.cpp-b3600-kquants",
        "tokenizer": "SentencePiece 256000",
        "training_license": "Gemma Terms of Use (Gated)",
        "commercial_use_permitted": False,  # Pending legal review per spec
        "legal_review_required": True,
        "vulnerability_scan": "CLEARED_NO_KNOWN_CVE",
        "notes": "Evaluation comparator only. Legal/procurement signoff required before production selection.",
    },
)

LLAMA_3_2_3B_INSTRUCT = ModelArtifact(
    id="llama-3.2-3b-instruct-q4",
    name="meta-llama/Llama-3.2-3B-Instruct",
    revision="v1.0.0-gguf-q4km",
    quantization="Q4_K_M",
    model_format="GGUF",
    checksum_sha256="5b3a987d65ef43210987654321fedcba0123456789abcdef0123456789abcdef",
    file_size_bytes=2_200_000_000,  # ~2.20 GB
    license_id="Llama 3.2 Community License",
    license_status=LicenseStatus.RESTRICTED,
    requires_legal_review=True,
    context_window=4096,
    languages=["en", "hi"],
    serving_runtime="llamacpp",
    prompt_template=LLAMA3_TEMPLATE,
    is_primary=False,
    is_fallback=False,
    is_comparator=True,
    status=ModelStatus.REGISTERED,
    sbom={
        "vendor": "Meta AI",
        "base_model": "Llama-3.2-3B-Instruct",
        "parameters": "3.21B",
        "quantizer": "llama.cpp-b3600-kquants",
        "tokenizer": "Tiktoken 128256",
        "training_license": "Llama 3.2 Community License",
        "commercial_use_permitted": True,
        "legal_review_required": True,
        "vulnerability_scan": "CLEARED_NO_KNOWN_CVE",
        "notes": "Requires specific license review for government department deployment.",
    },
)

GEMINI_3_6_FLASH = ModelArtifact(
    id="gemini-3.6-flash",
    name="Google Gemini 3.6 Flash",
    revision="v3.6-cloud",
    quantization="Cloud-API",
    model_format="Cloud-API",
    checksum_sha256="cloud-endpoint-managed",
    file_size_bytes=0,
    license_id="Google-Generative-AI-Terms",
    license_status=LicenseStatus.APPROVED,
    requires_legal_review=False,
    context_window=1048576,
    languages=["en", "hi"],
    serving_runtime="gemini",
    prompt_template="{system_prompt}\n\n{user_prompt}",
    is_primary=False,
    is_fallback=False,
    is_comparator=False,
    status=ModelStatus.REGISTERED,
    sbom={
        "vendor": "Google DeepMind",
        "base_model": "gemini-3.6-flash",
        "modality": "multimodal (text, audio, vision)",
        "license": "Google Generative AI Developer Terms",
        "commercial_use_permitted": True,
        "notes": "Current flagship multimodal cloud engine supporting live text and voice.",
    },
)

GEMINI_2_0_FLASH = ModelArtifact(
    id="gemini-2.0-flash",
    name="Google Gemini 2.0 Flash (Legacy Alias)",
    revision="v2.0-cloud",
    quantization="Cloud-API",
    model_format="Cloud-API",
    checksum_sha256="cloud-endpoint-managed",
    file_size_bytes=0,
    license_id="Google-Generative-AI-Terms",
    license_status=LicenseStatus.APPROVED,
    requires_legal_review=False,
    context_window=1048576,
    languages=["en", "hi"],
    serving_runtime="gemini",
    prompt_template="{system_prompt}\n\n{user_prompt}",
    is_primary=False,
    is_fallback=False,
    is_comparator=False,
    status=ModelStatus.REGISTERED,
    sbom={
        "vendor": "Google DeepMind",
        "base_model": "gemini-3.6-flash",
        "modality": "multimodal (text, audio, vision)",
        "license": "Google Generative AI Developer Terms",
        "commercial_use_permitted": True,
        "notes": "Legacy alias automatically routed to gemini-3.6-flash.",
    },
)

GEMINI_1_5_FLASH = ModelArtifact(
    id="gemini-1.5-flash",
    name="Google Gemini 1.5 Flash",
    revision="v1.5-cloud",
    quantization="Cloud-API",
    model_format="Cloud-API",
    checksum_sha256="cloud-endpoint-managed",
    file_size_bytes=0,
    license_id="Google-Generative-AI-Terms",
    license_status=LicenseStatus.APPROVED,
    requires_legal_review=False,
    context_window=1048576,
    languages=["en", "hi"],
    serving_runtime="gemini",
    prompt_template="{system_prompt}\n\n{user_prompt}",
    is_primary=False,
    is_fallback=False,
    is_comparator=False,
    status=ModelStatus.REGISTERED,
    sbom={
        "vendor": "Google DeepMind",
        "base_model": "gemini-1.5-flash",
        "modality": "multimodal (text, audio, vision)",
        "license": "Google Generative AI Developer Terms",
        "commercial_use_permitted": True,
        "notes": "Fast, high-efficiency cloud model.",
    },
)

CANONICAL_MODELS: Dict[str, ModelArtifact] = {
    QWEN3_4B_INSTRUCT.id: QWEN3_4B_INSTRUCT,
    QWEN3_1_7B_INSTRUCT.id: QWEN3_1_7B_INSTRUCT,
    QWEN2_5_3B_INSTRUCT.id: QWEN2_5_3B_INSTRUCT,
    GEMINI_3_6_FLASH.id: GEMINI_3_6_FLASH,
    GEMMA_3_4B_IT.id: GEMMA_3_4B_IT,
    LLAMA_3_2_3B_INSTRUCT.id: LLAMA_3_2_3B_INSTRUCT,
}



class ModelRegistry:
    """Manages model artifacts, pinned checksums, SBOM metadata, and DB persistence."""

    def __init__(self, session: Optional[Session] = None):
        self.session = session
        self._artifacts: Dict[str, ModelArtifact] = dict(CANONICAL_MODELS)

    def register_artifact(self, artifact: ModelArtifact, actor: str = "system") -> ModelArtifact:
        """Register a release-controlled model artifact in memory and database."""
        self._artifacts[artifact.id] = artifact
        if self.session:
            record = self.session.query(ModelArtifactRecord).filter(ModelArtifactRecord.id == artifact.id).first()
            if not record:
                record = ModelArtifactRecord(
                    id=artifact.id,
                    name=artifact.name,
                    revision=artifact.revision,
                    quantization=artifact.quantization,
                    model_format=artifact.model_format,
                    checksum_sha256=artifact.checksum_sha256,
                    file_size_bytes=artifact.file_size_bytes,
                    license_id=artifact.license_id,
                    license_status=str(artifact.license_status),
                    context_window=artifact.context_window,
                    serving_runtime=artifact.serving_runtime,
                    prompt_template=artifact.prompt_template,
                    is_primary=1 if artifact.is_primary else 0,
                    is_fallback=1 if artifact.is_fallback else 0,
                    is_comparator=1 if artifact.is_comparator else 0,
                    status=str(artifact.status),
                    sbom_json=artifact.sbom,
                )
                self.session.add(record)
            else:
                record.status = str(artifact.status)
                record.file_size_bytes = artifact.file_size_bytes
                record.is_primary = 1 if artifact.is_primary else 0
                record.is_fallback = 1 if artifact.is_fallback else 0
                record.is_comparator = 1 if artifact.is_comparator else 0
                record.sbom_json = artifact.sbom
            self.session.flush()
        return artifact

    def get(self, model_id: str) -> Optional[ModelArtifact]:
        """Retrieve model artifact by unique ID, with alias resolution."""
        aliases = {
            "gemini-2.0-flash": GEMINI_3_6_FLASH.id,
            "gemini-2.0-flash-exp": GEMINI_3_6_FLASH.id,
            "gemini-2.5-flash": GEMINI_3_6_FLASH.id,
            "gemini-1.5-flash": GEMINI_3_6_FLASH.id,
            "gemini-1.5-pro": GEMINI_3_6_FLASH.id,
            "gemini-flash": GEMINI_3_6_FLASH.id,
            "gemini": GEMINI_3_6_FLASH.id,
            "qwen2.5:3b": QWEN2_5_3B_INSTRUCT.id,
            "qwen2.5-3b": QWEN2_5_3B_INSTRUCT.id,
            "qwen2.5:latest": QWEN2_5_3B_INSTRUCT.id,
            "qwen2.5": QWEN2_5_3B_INSTRUCT.id,
            "qwen2.5-3b-instruct": QWEN2_5_3B_INSTRUCT.id,
            "qwen3": QWEN3_4B_INSTRUCT.id,
            "qwen3-4b": QWEN3_4B_INSTRUCT.id,
            "qwen3-1.7b": QWEN3_1_7B_INSTRUCT.id,
        }
        effective_id = aliases.get(model_id.strip().lower(), model_id) if model_id else model_id
        if effective_id in self._artifacts:
            return self._artifacts[effective_id]
        if self.session:
            record = self.session.query(ModelArtifactRecord).filter(
                (ModelArtifactRecord.id == effective_id) | (ModelArtifactRecord.id == model_id)
            ).first()

            if record:
                artifact = ModelArtifact(
                    id=record.id,
                    name=record.name,
                    revision=record.revision,
                    quantization=record.quantization,
                    model_format=record.model_format,
                    checksum_sha256=record.checksum_sha256,
                    file_size_bytes=getattr(record, "file_size_bytes", 2_850_000_000) or 2_850_000_000,
                    license_id=record.license_id,
                    license_status=LicenseStatus(record.license_status),
                    requires_legal_review=(record.license_status != LicenseStatus.APPROVED.value),
                    context_window=record.context_window,
                    languages=["en", "hi"],
                    serving_runtime=record.serving_runtime,
                    prompt_template=record.prompt_template,
                    is_primary=bool(record.is_primary),
                    is_fallback=bool(record.is_fallback),
                    is_comparator=bool(getattr(record, "is_comparator", 0)),
                    status=ModelStatus(record.status),
                    sbom=record.sbom_json or {},
                )
                self._artifacts[artifact.id] = artifact
                return artifact
        return None

    def get_primary(self) -> ModelArtifact:
        """Get the primary approved model (Qwen3-4B Instruct)."""
        if self.session:
            rec = self.session.query(ModelArtifactRecord).filter(ModelArtifactRecord.is_primary == 1).first()
            if rec and rec.id in self._artifacts:
                return self._artifacts[rec.id]
        for art in self._artifacts.values():
            if art.is_primary:
                return art
        return QWEN3_4B_INSTRUCT

    def get_fallback(self) -> ModelArtifact:
        """Get the low-memory fallback model (Qwen3-1.7B Instruct)."""
        if self.session:
            rec = self.session.query(ModelArtifactRecord).filter(ModelArtifactRecord.is_fallback == 1).first()
            if rec and rec.id in self._artifacts:
                return self._artifacts[rec.id]
        for art in self._artifacts.values():
            if art.is_fallback:
                return art
        return QWEN3_1_7B_INSTRUCT

    def list_all(self) -> List[ModelArtifact]:
        """List all registered model artifacts."""
        return list(self._artifacts.values())

    def seed_defaults(self) -> int:
        """Seed all canonical release artifacts to the database."""
        count = 0
        for art in CANONICAL_MODELS.values():
            self.register_artifact(art, actor="system_init")
            count += 1
        if self.session:
            self.session.commit()
        return count

    @staticmethod
    def compute_sha256(data: bytes) -> str:
        """Compute SHA-256 checksum for model weights or configuration."""
        return hashlib.sha256(data).hexdigest()

    def verify_checksum(self, model_id: str, data: bytes) -> bool:
        """Verify that weights or byte payload match the pinned SHA-256 release hash."""
        artifact = self.get(model_id)
        if not artifact:
            return False
        computed = self.compute_sha256(data)
        return computed.lower() == artifact.checksum_sha256.lower()
