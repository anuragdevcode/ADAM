"""Cycle and Loop Detection Engine for ADAM Agentic Execution.

Guarantees deterministic termination by intercepting duplicate tool executions,
detecting repeating cyclic patterns (e.g., A -> B -> A -> B), and capping per-action
frequency ceilings.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class ActionSignature:
    """Canonical representation of an executed action step."""
    step_id: int
    action_type: str
    args_digest: str
    action_signature: str
    timestamp: float


class CycleDetector:
    """Monitors action history to prevent infinite loops, cyclic oscillations,

    and redundant tool invocations.
    """

    def __init__(self, max_cycle_length: int = 3, max_action_frequency: int = 3):
        self.max_cycle_length = max_cycle_length
        self.max_action_frequency = max_action_frequency
        self.history: List[ActionSignature] = []
        self.seen_signatures: Set[str] = set()
        self.action_counts: Dict[str, int] = {}

    @classmethod
    def compute_args_digest(cls, args: Dict[str, Any]) -> str:
        """Create a deterministic hash from argument dictionary."""
        try:
            serialized = json.dumps(args, sort_keys=True, default=str)
        except Exception:
            serialized = str(sorted(args.items()))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:12]

    def record_action(
        self,
        step_id: int,
        action_type: str,
        tool_args: Dict[str, Any],
        timestamp: float,
    ) -> ActionSignature:
        """Record an executed action into history."""
        args_digest = self.compute_args_digest(tool_args)
        full_sig = f"{action_type}:{args_digest}"

        sig = ActionSignature(
            step_id=step_id,
            action_type=action_type,
            args_digest=args_digest,
            action_signature=full_sig,
            timestamp=timestamp,
        )
        self.history.append(sig)
        self.seen_signatures.add(full_sig)
        self.action_counts[action_type] = self.action_counts.get(action_type, 0) + 1
        return sig

    def is_exact_duplicate(self, action_type: str, tool_args: Dict[str, Any]) -> bool:
        """Check if this exact action and argument combination has already been executed."""
        digest = self.compute_args_digest(tool_args)
        sig = f"{action_type}:{digest}"
        return sig in self.seen_signatures

    def is_frequency_exceeded(self, action_type: str, custom_limit: Optional[int] = None) -> bool:
        """Check if an action type has reached its allowed invocation quota."""
        limit = custom_limit if custom_limit is not None else self.max_action_frequency
        return self.action_counts.get(action_type, 0) >= limit

    def detect_cycle(self) -> Optional[Tuple[int, List[str]]]:
        """Detect trailing repeating cycles of length k (where 2 <= k <= max_cycle_length).

        Returns:
            Tuple of (cycle_length, cycle_signatures) if a cycle is found, else None.
        """
        sigs = [s.action_signature for s in self.history]
        total = len(sigs)

        for k in range(2, min(self.max_cycle_length + 1, (total // 2) + 1)):
            trailing = sigs[-k:]
            preceding = sigs[-2 * k : -k]
            if trailing == preceding:
                return (k, trailing)

        return None

    def should_terminate(
        self,
        action_type: str,
        tool_args: Dict[str, Any],
        custom_frequency_limit: Optional[int] = None,
    ) -> Tuple[bool, Optional[str]]:
        """Comprehensive pre-execution check: returns (should_terminate, reason)."""
        # 1. Exact duplicate check
        if self.is_exact_duplicate(action_type, tool_args):
            return True, f"Duplicate tool call suppressed: {action_type}"

        # 2. Action frequency ceiling
        if self.is_frequency_exceeded(action_type, custom_frequency_limit):
            return True, f"Action frequency ceiling reached for '{action_type}'"

        # 3. Cyclic oscillation check
        cycle = self.detect_cycle()
        if cycle:
            cycle_len, pattern = cycle
            return True, f"Cyclic execution detected (length={cycle_len}): {' -> '.join(pattern)}"

        return False, None

    def reset(self) -> None:
        """Reset internal history and counters."""
        self.history.clear()
        self.seen_signatures.clear()
        self.action_counts.clear()
