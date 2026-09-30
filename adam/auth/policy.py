"""Role-based policy engine for ADAM access control and capability gating (S14)."""

from dataclasses import dataclass
from typing import List, Set


@dataclass(frozen=True)
class RoleCapabilities:
    """Capabilities granted by role assignment."""
    can_access_web: bool = False
    allow_web_research: bool = False
    max_sessions: int = 10
    allowed_classifications: Set[str] = None


ROLE_CAPABILITY_MAP = {
    "ADMIN": RoleCapabilities(
        can_access_web=True,
        allow_web_research=True,
        max_sessions=1000,
        allowed_classifications={"PUBLIC", "INTERNAL", "RESTRICTED", "CONFIDENTIAL", "ADMIN"},
    ),
    "OFFICER": RoleCapabilities(
        can_access_web=True,
        allow_web_research=True,
        max_sessions=100,
        allowed_classifications={"PUBLIC", "INTERNAL", "RESTRICTED"},
    ),
    "RECORDS_OFFICER": RoleCapabilities(
        can_access_web=False,
        allow_web_research=False,
        max_sessions=50,
        allowed_classifications={"PUBLIC", "INTERNAL", "RESTRICTED"},
    ),
    "RESEARCHER": RoleCapabilities(
        can_access_web=True,
        allow_web_research=True,
        max_sessions=50,
        allowed_classifications={"PUBLIC", "INTERNAL"},
    ),
    "REVIEWER": RoleCapabilities(
        can_access_web=False,
        allow_web_research=False,
        max_sessions=20,
        allowed_classifications={"PUBLIC", "INTERNAL"},
    ),
    "OPERATOR": RoleCapabilities(
        can_access_web=False,
        allow_web_research=False,
        max_sessions=20,
        allowed_classifications={"PUBLIC", "INTERNAL"},
    ),
    "AUDITOR": RoleCapabilities(
        can_access_web=False,
        allow_web_research=False,
        max_sessions=50,
        allowed_classifications={"PUBLIC", "INTERNAL", "RESTRICTED"},
    ),
    "PUBLIC": RoleCapabilities(
        can_access_web=False,
        allow_web_research=False,
        max_sessions=5,
        allowed_classifications={"PUBLIC"},
    ),
}


def get_role_policy(roles: List[str]) -> RoleCapabilities:
    """Compute aggregated capabilities across assigned roles."""
    if not roles:
        return ROLE_CAPABILITY_MAP["PUBLIC"]

    can_access_web = False
    allow_web_research = False
    max_sessions = 5
    allowed_classes: Set[str] = set()

    for r in roles:
        cap = ROLE_CAPABILITY_MAP.get(r.upper(), ROLE_CAPABILITY_MAP["PUBLIC"])
        can_access_web = can_access_web or cap.can_access_web
        allow_web_research = allow_web_research or cap.allow_web_research
        max_sessions = max(max_sessions, cap.max_sessions)
        if cap.allowed_classifications:
            allowed_classes.update(cap.allowed_classifications)

    return RoleCapabilities(
        can_access_web=can_access_web,
        allow_web_research=allow_web_research,
        max_sessions=max_sessions,
        allowed_classifications=allowed_classes or {"PUBLIC"},
    )
