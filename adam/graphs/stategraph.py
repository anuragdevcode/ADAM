"""Declarative StateGraph Workflow Engine for ADAM.

Enables composable, node-and-edge agent execution graphs with typed state,
conditional routing, cycle guards, and step-level telemetry.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

END = "__end__"
START = "__start__"


@dataclass
class NodeExecutionRecord:
    """Telemetry record for an executed graph node."""
    node_name: str
    step_number: int
    duration_ms: float
    state_keys_modified: List[str]
    error: Optional[str] = None


@dataclass
class StateGraphResult:
    """Execution output of a compiled state graph."""
    final_state: Dict[str, Any]
    execution_path: List[str]
    records: List[NodeExecutionRecord] = field(default_factory=list)
    total_steps: int = 0
    total_duration_ms: float = 0.0
    terminated_early: bool = False
    termination_reason: Optional[str] = None


class ConditionalEdge:
    """A conditional router determining next node based on state."""

    def __init__(
        self,
        router_fn: Callable[[Dict[str, Any]], str],
        path_map: Dict[str, str],
    ):
        self.router_fn = router_fn
        self.path_map = path_map

    def resolve_next_node(self, state: Dict[str, Any]) -> str:
        condition_key = self.router_fn(state)
        next_node = self.path_map.get(condition_key, END)
        return next_node


class StateGraph:
    """Builder for declarative agent execution graphs."""

    def __init__(self):
        self.nodes: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {}
        self.edges: Dict[str, str] = {}
        self.conditional_edges: Dict[str, ConditionalEdge] = {}
        self.entry_point: Optional[str] = None
        self.finish_nodes: Set[str] = {END}

    def add_node(
        self,
        name: str,
        fn: Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> StateGraph:
        """Register a node function."""
        if name in (START, END):
            raise ValueError(f"Reserved node name: {name}")
        self.nodes[name] = fn
        return self

    def add_edge(self, from_node: str, to_node: str) -> StateGraph:
        """Add a deterministic directed edge between two nodes."""
        if from_node != START and from_node not in self.nodes:
            raise ValueError(f"Unknown source node: {from_node}")
        if to_node != END and to_node not in self.nodes:
            raise ValueError(f"Unknown target node: {to_node}")
        self.edges[from_node] = to_node
        return self

    def add_conditional_edges(
        self,
        from_node: str,
        router_fn: Callable[[Dict[str, Any]], str],
        path_map: Dict[str, str],
    ) -> StateGraph:
        """Add conditional routing edges from a node."""
        if from_node not in self.nodes:
            raise ValueError(f"Unknown source node: {from_node}")
        self.conditional_edges[from_node] = ConditionalEdge(router_fn, path_map)
        return self

    def set_entry_point(self, node_name: str) -> StateGraph:
        """Set initial entry node."""
        if node_name not in self.nodes:
            raise ValueError(f"Entry node '{node_name}' not registered.")
        self.entry_point = node_name
        self.edges[START] = node_name
        return self

    def set_finish_point(self, node_name: str) -> StateGraph:
        """Mark a node as a terminating leaf."""
        if node_name not in self.nodes:
            raise ValueError(f"Finish node '{node_name}' not registered.")
        self.edges[node_name] = END
        self.finish_nodes.add(node_name)
        return self

    def compile(self) -> CompiledStateGraph:
        """Validate and compile graph into an executable runner."""
        if not self.entry_point:
            raise ValueError("StateGraph requires an entry point before compilation.")
        return CompiledStateGraph(
            nodes=dict(self.nodes),
            edges=dict(self.edges),
            conditional_edges=dict(self.conditional_edges),
            entry_point=self.entry_point,
            finish_nodes=set(self.finish_nodes),
        )


class CompiledStateGraph:
    """Compiled, thread-safe runner for StateGraph workflows."""

    def __init__(
        self,
        nodes: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]],
        edges: Dict[str, str],
        conditional_edges: Dict[str, ConditionalEdge],
        entry_point: str,
        finish_nodes: Set[str],
    ):
        self.nodes = nodes
        self.edges = edges
        self.conditional_edges = conditional_edges
        self.entry_point = entry_point
        self.finish_nodes = finish_nodes

    def invoke(
        self,
        initial_state: Dict[str, Any],
        max_steps: int = 20,
    ) -> StateGraphResult:
        """Execute the workflow graph starting from entry_point until END or max_steps."""
        start_time = time.perf_counter()
        state = dict(initial_state)
        current_node = self.entry_point
        execution_path: List[str] = []
        records: List[NodeExecutionRecord] = []
        step_number = 0
        terminated_early = False
        termination_reason = None

        while current_node != END and step_number < max_steps:
            step_number += 1
            execution_path.append(current_node)
            node_fn = self.nodes.get(current_node)

            if not node_fn:
                terminated_early = True
                termination_reason = f"Node '{current_node}' not found."
                break

            node_start = time.perf_counter()
            keys_before = set(state.keys())
            error = None

            try:
                updates = node_fn(state)
                if isinstance(updates, dict):
                    state.update(updates)
            except Exception as e:
                logger.error("Error executing node %s: %s", current_node, e)
                error = str(e)
                state["last_error"] = error
                terminated_early = True
                termination_reason = f"Exception in node {current_node}: {error}"

            duration_ms = (time.perf_counter() - node_start) * 1000.0
            modified_keys = [k for k in state.keys() if k not in keys_before or state[k] != updates.get(k)]
            records.append(
                NodeExecutionRecord(
                    node_name=current_node,
                    step_number=step_number,
                    duration_ms=round(duration_ms, 2),
                    state_keys_modified=modified_keys,
                    error=error,
                )
            )

            if terminated_early:
                break

            # Resolve next node
            if current_node in self.conditional_edges:
                current_node = self.conditional_edges[current_node].resolve_next_node(state)
            elif current_node in self.edges:
                current_node = self.edges[current_node]
            else:
                current_node = END

        if step_number >= max_steps and current_node != END:
            terminated_early = True
            termination_reason = f"Graph step ceiling reached ({max_steps} steps)."

        total_duration = (time.perf_counter() - start_time) * 1000.0
        return StateGraphResult(
            final_state=state,
            execution_path=execution_path,
            records=records,
            total_steps=step_number,
            total_duration_ms=round(total_duration, 2),
            terminated_early=terminated_early,
            termination_reason=termination_reason,
        )
