"""Governance, air-gapped isolation, and approval boundary guards for Capability Fabric."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from adam.capabilities.models import (
    CapabilityDescriptor,
    CapabilityInvocationRequest,
    InvocationStatus,
    RiskLevel,
)
from adam.rag.models import UserContext
from adam.vocabularies import Classification

logger = logging.getLogger(__name__)

# Numeric order of clearance levels for comparative enforcement
CLEARANCE_RANKS: Dict[str, int] = {
    Classification.PUBLIC.value: 1,
    Classification.INTERNAL.value: 2,
    Classification.RESTRICTED.value: 3,
    Classification.CONFIDENTIAL.value: 4,
}


class CapabilitySecurityViolationError(PermissionError):
    """Raised when an unauthorized or forbidden capability is requested."""
    pass


class AirGappedSovereigntyViolationError(PermissionError):
    """Raised when a network or external capability is attempted under classified clearance."""
    pass


class ApprovalBoundaryRequiredError(PermissionError):
    """Raised when an unapproved high-risk capability requires human administrative confirmation."""
    pass


class CapabilityGovernanceEngine:
    """Evaluates security, classification clearance, air-gapped sovereignty, and approval boundaries."""

    @classmethod
    def evaluate_clearance(
        cls,
        descriptor: CapabilityDescriptor,
        user_context: Optional[UserContext],
    ) -> Tuple[bool, Optional[str]]:
        """Verify user's clearance meets the capability's minimum clearance requirements."""
        if not user_context:
            if descriptor.permissions.min_clearance_level != Classification.PUBLIC.value:
                return False, f"Anonymous access denied: requires {descriptor.permissions.min_clearance_level} clearance."
            return True, None

        if user_context.is_admin():
            return True, None

        user_clearance = user_context.clearance_level or Classification.PUBLIC.value
        user_rank = CLEARANCE_RANKS.get(user_clearance, 1)
        req_rank = CLEARANCE_RANKS.get(descriptor.permissions.min_clearance_level, 1)

        if user_rank < req_rank:
            return (
                False,
                f"Clearance Denied: User clearance '{user_clearance}' is insufficient. "
                f"Requires at least '{descriptor.permissions.min_clearance_level}'.",
            )

        return True, None

    @classmethod
    def evaluate_air_gapped_policy(
        cls,
        descriptor: CapabilityDescriptor,
        user_context: Optional[UserContext],
    ) -> Tuple[bool, Optional[str]]:
        """Enforce strict Air-Gapped Data Sovereignty Boundary.
        
        Under RESTRICTED or CONFIDENTIAL clearances, all external network capabilities
        (web search, page fetching, remote MCP connections) are strictly barred.
        """
        if not user_context:
            return True, None

        user_clearance = user_context.clearance_level or Classification.PUBLIC.value
        is_classified = user_clearance in (
            Classification.RESTRICTED.value,
            Classification.CONFIDENTIAL.value,
        )

        if is_classified:
            if descriptor.requires_network or not descriptor.permissions.is_air_gapped_compatible:
                return (
                    False,
                    f"Air-Gapped Policy Violation: Capability '{descriptor.id}' requires external network "
                    f"access, which is strictly prohibited for {user_clearance} clearance "
                    "under Uttarakhand Air-Gapped Data Sovereignty Policy.",
                )

        return True, None

    @classmethod
    def evaluate_approval_boundary(
        cls,
        descriptor: CapabilityDescriptor,
        request: CapabilityInvocationRequest,
    ) -> Tuple[bool, Optional[str]]:
        """Verify whether human confirmation / approval token is needed before execution."""
        if not descriptor.requires_approval and descriptor.risk != RiskLevel.CRITICAL:
            return True, None

        # Check for valid approval token in request
        if request.approval_token and request.approval_token.startswith("APPROVED:"):
            return True, None

        reason = (
            f"Approval Boundary Required: Capability '{descriptor.id}' is classified as "
            f"{descriptor.risk.value} risk and requires explicit human administrative authorization."
        )
        return False, reason
