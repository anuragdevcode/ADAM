"""Typed models and schemas for ADAM's Capability Fabric.

Defines:
- CapabilityType: Enum of capability modalities (tool, specialist agent, graph traversal, data source, sandbox compute, MCP bridge).
- RiskLevel: Operational risk tiers (LOW, MEDIUM, HIGH, CRITICAL).
- InvocationStatus: Execution lifecycle state.
- CostModel: Estimated latency, token weight, compute intensity, and rate limit units.
- CapabilityPermissions: Clearance requirements, allowed roles, department scopes, and air-gapped sovereignty.
- CapabilityDescriptor: Authoritative typed specification of a capability.
- CapabilityInvocationRequest / CapabilityInvocationResult: Typed request and response envelopes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable, Dict, List, Optional, Type
from pydantic import BaseModel, ConfigDict, Field

from adam.rag.models import EvidencePassage, UserContext
from adam.vocabularies import Classification


class CapabilityType(StrEnum):
    """Modality of capability."""
    TOOL = "TOOL"
    SPECIALIST_AGENT = "SPECIALIST_AGENT"
    GRAPH_TRAVERSAL = "GRAPH_TRAVERSAL"
    DATA_SOURCE = "DATA_SOURCE"
    SANDBOX_COMPUTE = "SANDBOX_COMPUTE"
    MCP_BRIDGE = "MCP_BRIDGE"


class RiskLevel(StrEnum):
    """Operational risk classification."""
    LOW = "LOW"            # Read-only search, metadata lookup, local introspection
    MEDIUM = "MEDIUM"      # Sandboxed calculation, database queries, source comparison
    HIGH = "HIGH"          # External web research, multi-hop graph expansion
    CRITICAL = "CRITICAL"  # Administrative re-indexing, clearance overrides, unmasking


class InvocationStatus(StrEnum):
    """Execution status of a capability invocation."""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    ABSTAINED = "ABSTAINED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    BLOCKED = "BLOCKED"


class CostModel(BaseModel):
    """Resource and latency cost estimation for capability routing."""
    model_config = ConfigDict(extra="ignore")

    latency_weight_ms: float = Field(default=50.0, description="Estimated typical execution latency in milliseconds")
    token_cost_weight: str = Field(default="LOW", description="Relative token consumption: LOW, MEDIUM, HIGH")
    compute_intensity: str = Field(default="LIGHT", description="CPU/RAM impact: LIGHT, MODERATE, HEAVY")
    rate_limit_units: int = Field(default=1, description="Rate limit consumption units per invocation")


class CapabilityPermissions(BaseModel):
    """Clearance, role, and sovereignty access control rules."""
    model_config = ConfigDict(extra="ignore")

    min_clearance_level: str = Field(
        default=Classification.PUBLIC.value,
        description="Minimum classification clearance required: PUBLIC, INTERNAL, RESTRICTED, CONFIDENTIAL"
    )
    allowed_roles: List[str] = Field(
        default_factory=lambda: ["CITIZEN", "OFFICER", "ADMIN", "ANONYMOUS"],
        description="Roles permitted to execute this capability"
    )
    department_scoped: bool = Field(
        default=False,
        description="Whether invocation results must be filtered to user's assigned department"
    )
    is_air_gapped_compatible: bool = Field(
        default=True,
        description="Whether capability is allowed under RESTRICTED / CONFIDENTIAL air-gapped data sovereignty policy"
    )


class CapabilityDescriptor(BaseModel):
    """Authoritative descriptor of a registered capability in the ADAM Capability Fabric."""
    model_config = ConfigDict(extra="ignore", arbitrary_types_allowed=True)

    id: str = Field(..., description="Unique capability identifier (e.g. repo_search, python_sandbox)")
    name: str = Field(..., description="Human-readable capability name")
    type: CapabilityType = Field(..., description="Modality of the capability")
    purpose: str = Field(..., description="Succinct explanation of capability purpose")
    description: str = Field(..., description="Comprehensive description including input/output semantics")
    
    # Typed schemas
    input_model: Optional[Type[BaseModel]] = Field(default=None, description="Pydantic model validating input arguments")
    output_model: Optional[Type[BaseModel]] = Field(default=None, description="Pydantic model describing structured output")
    
    # Governance & Constraints
    permissions: CapabilityPermissions = Field(default_factory=CapabilityPermissions)
    risk: RiskLevel = Field(default=RiskLevel.LOW)
    cost: CostModel = Field(default_factory=CostModel)
    limitations: List[str] = Field(default_factory=list, description="Explicit boundaries and limitations")
    
    # Behavioral conditions for intelligent decisioning
    when_to_use: str = Field(..., description="Optimal conditions and problem types for this capability")
    when_to_avoid: str = Field(default="", description="Negative constraints when this capability should NOT be picked")
    prerequisites: List[str] = Field(default_factory=list, description="Preconditions required before invoking")
    
    # Invariant flags
    is_read_only: bool = Field(default=True, description="Strict invariant: must be read-only for model agent safety")
    requires_network: bool = Field(default=False, description="Whether network communication is required")
    requires_approval: bool = Field(default=False, description="Whether human confirmation / approval boundary applies")
    
    # Callable execution handler (optional in pure schema, provided on registration)
    handler: Optional[Any] = Field(default=None, description="Underlying execution function or callable")

    def to_manifest_dict(self) -> Dict[str, Any]:
        """Serialize into transparent self-model manifest dictionary."""
        params_schema = self.input_model.model_json_schema() if self.input_model else {"type": "object", "properties": {}}
        # Clean up JSON schema title to match standard OpenAI / MCP tool specs
        params_schema = dict(params_schema)
        params_schema.pop("title", None)

        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "purpose": self.purpose,
            "description": self.description,
            "category": self.type.value.lower(),
            "when_to_use": self.when_to_use,
            "when_to_avoid": self.when_to_avoid,
            "prerequisites": self.prerequisites,
            "limitations": "; ".join(self.limitations) if self.limitations else "None",
            "risk_level": self.risk.value,
            "min_clearance": self.permissions.min_clearance_level,
            "requires_network": self.requires_network,
            "is_air_gapped_compatible": self.permissions.is_air_gapped_compatible,
            "is_read_only": self.is_read_only,
            "requires_approval": self.requires_approval,
            "cost": self.cost.model_dump(),
            "parameters": params_schema,
        }

    def to_mcp_tool_schema(self) -> Dict[str, Any]:
        """Export as standard Model Context Protocol (MCP) tool definition."""
        params_schema = self.input_model.model_json_schema() if self.input_model else {"type": "object", "properties": {}}
        params_schema = dict(params_schema)
        params_schema.pop("title", None)

        return {
            "name": self.id,
            "description": f"{self.purpose} {self.description}".strip(),
            "inputSchema": params_schema,
        }


@dataclass
class CapabilityInvocationRequest:
    """Invocation request envelope."""
    capability_id: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    user_context: Optional[UserContext] = None
    session: Optional[Any] = None
    execution_id: Optional[str] = None
    depth: int = 0
    approval_token: Optional[str] = None


@dataclass
class CapabilityInvocationResult:
    """Standardized result returned by capability execution."""
    capability_id: str
    status: InvocationStatus
    value: Any = None
    error: Optional[str] = None
    latency_ms: float = 0.0
    evidence_passages: List[EvidencePassage] = field(default_factory=list)
    provenance_nodes: List[Dict[str, Any]] = field(default_factory=list)
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    requires_approval: bool = False
    approval_prompt: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        val_summary = self.value
        if isinstance(val_summary, dict):
            val_summary = {k: v for k, v in val_summary.items() if k != "raw_passages"}

        return {
            "capability_id": self.capability_id,
            "status": self.status.value,
            "value": val_summary,
            "error": self.error,
            "latency_ms": round(self.latency_ms, 2),
            "evidence_count": len(self.evidence_passages),
            "provenance_node_count": len(self.provenance_nodes),
            "requires_approval": self.requires_approval,
            "approval_prompt": self.approval_prompt,
        }
