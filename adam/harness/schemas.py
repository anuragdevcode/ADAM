"""Structured schemas for intermediate LLM operations.

Provides schemas for structured tasks such as intent classification, citation
mapping, and parameter extraction without forcing structured output constraints
onto open-ended creative or conversational text generation.
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class IntentExtractionSchema(BaseModel):
    """Schema for intermediate intent and entity extraction."""
    intent: str = Field(description="Detected administrative intent category")
    department: Optional[str] = Field(None, description="Extracted department identifier")
    go_number: Optional[str] = Field(None, description="Extracted Government Order identifier")
    is_high_risk: bool = Field(False, description="Whether the prompt requires human authority brief")
    requires_citation: bool = Field(True, description="Whether statutory or factual citations are required")


class CitationMappingSchema(BaseModel):
    """Schema mapping claimed statements to passage identifiers."""
    claim: str = Field(description="The factual claim asserted")
    passage_index: int = Field(description="The 1-based index of the supporting passage")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Confidence of the attribution")


class ModelStructuredDecision(BaseModel):
    """Schema for deterministic gate evaluation by the model when requested."""
    status: str = Field(description="Evaluation outcome: APPROVED, LIMITED, or REJECTED")
    reasons: List[str] = Field(default_factory=list, description="Reasoning factors")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Supplementary fields")
