"""ADAM Capability Fabric & Agent Tooling Layer.

Provides dynamic discovery, understanding, selection, invocation, verification,
and combination of tools, data sources, graph traversals, sandbox compute,
MCP bridges, and A2A specialist agents.
"""

from adam.capabilities.a2a import (
    A2ABudget,
    A2ARecursionError,
    A2AResponseEnvelope,
    A2ASpecialistCoordinator,
    A2ATaskContract,
    A2ATaskStatus,
    ComplianceAuditSpecialist,
    PrecedentGraphSpecialist,
    QuantitativeAnalysisSpecialist,
    WebResearchSpecialist,
)
from adam.capabilities.governance import (
    AirGappedSovereigntyViolationError,
    ApprovalBoundaryRequiredError,
    CapabilityGovernanceEngine,
    CapabilitySecurityViolationError,
)
from adam.capabilities.mcp import (
    AdamMcpServer,
    McpCallToolResult,
    McpClientAdapter,
    McpContentItem,
    McpResource,
)
from adam.capabilities.models import (
    CapabilityDescriptor,
    CapabilityInvocationRequest,
    CapabilityInvocationResult,
    CapabilityPermissions,
    CapabilityType,
    CostModel,
    InvocationStatus,
    RiskLevel,
)
from adam.capabilities.registry import (
    CapabilityRegistry,
    GLOBAL_CAPABILITY_REGISTRY,
)
from adam.capabilities.router import (
    CapabilityRouter,
    EvidenceStoppingEvaluator,
    StoppingAssessment,
)

__all__ = [
    # Models
    "CapabilityType",
    "RiskLevel",
    "InvocationStatus",
    "CostModel",
    "CapabilityPermissions",
    "CapabilityDescriptor",
    "CapabilityInvocationRequest",
    "CapabilityInvocationResult",
    # Registry
    "CapabilityRegistry",
    "GLOBAL_CAPABILITY_REGISTRY",
    # Governance
    "CapabilityGovernanceEngine",
    "CapabilitySecurityViolationError",
    "AirGappedSovereigntyViolationError",
    "ApprovalBoundaryRequiredError",
    # MCP
    "AdamMcpServer",
    "McpClientAdapter",
    "McpCallToolResult",
    "McpContentItem",
    "McpResource",
    # A2A
    "A2ATaskContract",
    "A2AResponseEnvelope",
    "A2ATaskStatus",
    "A2ABudget",
    "A2ARecursionError",
    "A2ASpecialistCoordinator",
    "PrecedentGraphSpecialist",
    "QuantitativeAnalysisSpecialist",
    "WebResearchSpecialist",
    "ComplianceAuditSpecialist",
    # Router & Stopping
    "CapabilityRouter",
    "EvidenceStoppingEvaluator",
    "StoppingAssessment",
]
