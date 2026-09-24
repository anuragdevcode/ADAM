"""ADAM Loop Engineering Framework.

Provides autonomous plan-execute-verify (PEV) control, cycle and loop detection,
multi-dimensional computational budgeting, and critique-driven self-correction.
"""

from adam.loops.cycles import ActionSignature, CycleDetector
from adam.loops.budget import BudgetStatus, ExecutionBudgetWatchdog
from adam.loops.refinement import (
    RefinementIteration,
    RefinementResult,
    RefinementLoopController,
)
from adam.loops.controller import LoopExecutionTrace, PlanExecuteVerifyLoop

__all__ = [
    "ActionSignature",
    "CycleDetector",
    "BudgetStatus",
    "ExecutionBudgetWatchdog",
    "RefinementIteration",
    "RefinementResult",
    "RefinementLoopController",
    "LoopExecutionTrace",
    "PlanExecuteVerifyLoop",
]
