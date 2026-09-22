"""Secure, isolated Python execution sandbox for deterministic calculations, formulas, and date arithmetic.

Per Phase 04 & Agentic Problem-Solving specification:
- Strictly isolated execution for financial formulas, DA revision math, pension calculations, and date intervals.
- Hard AST validation rejects unauthorized imports, dunder attribute inspection, OS/network calls, and filesystem access.
- Bounded runtime (2.0s timeout) and bounded memory/output buffer (16KB ceiling).
"""

from __future__ import annotations

import ast
import contextlib
import datetime
import decimal
import io
import json
import math
import re
import statistics
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set


class SandboxSecurityError(PermissionError):
    """Raised when code violates AST whitelist or attempts unauthorized access."""
    pass


class SandboxTimeoutError(TimeoutError):
    """Raised when script execution exceeds the maximum CPU/wall-clock limit."""
    pass


@dataclass
class SandboxExecutionResult:
    """Outcome of sandbox execution."""
    success: bool
    output: str
    value: Any
    execution_time_ms: float
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "value": str(self.value) if self.value is not None else None,
            "execution_time_ms": round(self.execution_time_ms, 2),
            "error": self.error,
        }


class _SecurityAstValidator(ast.NodeVisitor):
    """Inspects AST to ensure code contains only safe mathematical and analytical operations."""

    BANNED_CALLS: Set[str] = {
        "open",
        "eval",
        "exec",
        "compile",
        "exit",
        "quit",
        "input",
        "__import__",
        "globals",
        "locals",
        "vars",
        "dir",
        "getattr",
        "setattr",
        "delattr",
        "hasattr",
        "breakpoint",
        "help",
        "memoryview",
    }

    def visit_Import(self, node: ast.Import) -> None:
        raise SandboxSecurityError(
            f"Security Violation: Explicit import '{ast.unparse(node)}' is forbidden in computation sandbox. "
            "Safe math, date, decimal, and statistics modules are pre-loaded."
        )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        raise SandboxSecurityError(
            f"Security Violation: Explicit import '{ast.unparse(node)}' is forbidden in computation sandbox. "
            "Safe math, date, decimal, and statistics modules are pre-loaded."
        )

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("_"):
            raise SandboxSecurityError(
                f"Security Violation: Access to private or special attribute '{node.attr}' is forbidden."
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        # Check direct calls like open(...)
        if isinstance(node.func, ast.Name):
            if node.func.id in self.BANNED_CALLS:
                raise SandboxSecurityError(
                    f"Security Violation: Call to restricted function '{node.func.id}()' is strictly prohibited."
                )
        self.generic_visit(node)


def _subprocess_sandbox_worker(
    code: str,
    context_vars: Optional[Dict[str, Any]],
    result_queue: Any,
    max_output_chars: int,
    memory_limit_bytes: int = 256 * 1024 * 1024,
) -> None:
    """Isolated child process worker executing sandboxed code with resource ceilings."""
    # Apply OS resource limits on POSIX platforms
    try:
        import resource
        if hasattr(resource, "RLIMIT_AS"):
            resource.setrlimit(resource.RLIMIT_AS, (memory_limit_bytes, memory_limit_bytes))
    except Exception:
        pass

    stdout_buffer = io.StringIO()
    try:
        tree = SecurePythonSandbox.validate_code(code)
        exec_globals = SecurePythonSandbox.get_safe_globals()
        if context_vars:
            for k, v in context_vars.items():
                if not k.startswith("_"):
                    exec_globals[k] = v

        exec_globals["__result_val__"] = None
        if tree.body and isinstance(tree.body[-1], ast.Expr):
            last_expr = tree.body[-1].value
            assign_node = ast.Assign(
                targets=[ast.Name(id="__result_val__", ctx=ast.Store())],
                value=last_expr,
            )
            ast.copy_location(assign_node, tree.body[-1])
            tree.body[-1] = assign_node
            ast.fix_missing_locations(tree)

        compiled = compile(tree, filename="<sandbox>", mode="exec")
        with contextlib.redirect_stdout(stdout_buffer):
            exec(compiled, exec_globals)

        result_val = exec_globals.get("__result_val__")
        output = stdout_buffer.getvalue()[:max_output_chars]
        result_queue.put({
            "success": True,
            "output": output,
            "value": result_val,
            "error": None,
        })
    except Exception as err:
        output = stdout_buffer.getvalue()[:max_output_chars]
        result_queue.put({
            "success": False,
            "output": output,
            "value": None,
            "error": f"{type(err).__name__}: {str(err)}",
        })


class SecurePythonSandbox:
    """Isolated Python execution environment for administrative and financial computations."""

    DEFAULT_TIMEOUT_SECONDS: float = 2.0
    MAX_OUTPUT_CHARS: int = 16384

    # Safe built-in functions
    SAFE_BUILTINS: Dict[str, Any] = {
        "abs": abs,
        "all": all,
        "any": any,
        "bin": bin,
        "bool": bool,
        "complex": complex,
        "dict": dict,
        "divmod": divmod,
        "enumerate": enumerate,
        "filter": filter,
        "float": float,
        "format": format,
        "frozenset": frozenset,
        "hex": hex,
        "int": int,
        "isinstance": isinstance,
        "issubclass": issubclass,
        "iter": iter,
        "len": len,
        "list": list,
        "map": map,
        "max": max,
        "min": min,
        "next": next,
        "oct": oct,
        "ord": ord,
        "pow": pow,
        "print": print,
        "range": range,
        "reversed": reversed,
        "round": round,
        "set": set,
        "slice": slice,
        "sorted": sorted,
        "str": str,
        "sum": sum,
        "tuple": tuple,
        "zip": zip,
        "True": True,
        "False": False,
        "None": None,
    }

    @classmethod
    def get_safe_globals(cls) -> Dict[str, Any]:
        """Construct isolated namespace with pre-imported standard math and analytical libraries."""
        return {
            "__builtins__": cls.SAFE_BUILTINS,
            "math": math,
            "datetime": datetime.datetime,
            "date": datetime.date,
            "timedelta": datetime.timedelta,
            "timezone": datetime.timezone,
            "Decimal": decimal.Decimal,
            "decimal": decimal,
            "json": json,
            "re": re,
            "statistics": statistics,
        }

    @classmethod
    def validate_code(cls, code: str) -> ast.AST:
        """Parse code into AST and verify that no dangerous operations exist."""
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            raise ValueError(f"Syntax error in computation script: {e}") from e

        validator = _SecurityAstValidator()
        validator.visit(tree)
        return tree

    def __init__(self, timeout_seconds: Optional[float] = None, use_subprocess: bool = True):
        self.timeout_seconds = timeout_seconds or self.DEFAULT_TIMEOUT_SECONDS
        self.use_subprocess = use_subprocess

    def __call__(self, code: str, **kwargs) -> SandboxExecutionResult:
        return self.execute(code, **kwargs)

    @classmethod
    def _execute_in_thread(
        cls,
        code: str,
        tree: ast.AST,
        timeout: float,
        start_time: float,
        context_vars: Optional[Dict[str, Any]] = None,
    ) -> SandboxExecutionResult:
        """In-process thread execution fallback."""
        exec_globals = cls.get_safe_globals()
        if context_vars:
            for k, v in context_vars.items():
                if not k.startswith("_"):
                    exec_globals[k] = v

        captured_value_holder = {"__result_val__": None}
        exec_globals["__result_val__"] = None

        if tree.body and isinstance(tree.body[-1], ast.Expr):
            last_expr = tree.body[-1].value
            assign_node = ast.Assign(
                targets=[ast.Name(id="__result_val__", ctx=ast.Store())],
                value=last_expr,
            )
            ast.copy_location(assign_node, tree.body[-1])
            tree.body[-1] = assign_node
            ast.fix_missing_locations(tree)

        compiled_code = compile(tree, filename="<sandbox>", mode="exec")

        stdout_buffer = io.StringIO()
        exec_error: Optional[Exception] = None
        finished = threading.Event()

        def _worker():
            nonlocal exec_error
            try:
                with contextlib.redirect_stdout(stdout_buffer):
                    exec(compiled_code, exec_globals)
                    captured_value_holder["__result_val__"] = exec_globals.get("__result_val__")
            except Exception as e:
                exec_error = e
            finally:
                finished.set()

        worker_thread = threading.Thread(target=_worker, daemon=True, name="sandbox-exec")
        worker_thread.start()

        finished.wait(timeout=timeout)
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        if not finished.is_set():
            return SandboxExecutionResult(
                success=False,
                output=stdout_buffer.getvalue()[: cls.MAX_OUTPUT_CHARS],
                value=None,
                execution_time_ms=elapsed_ms,
                error=f"Execution timed out after {timeout} seconds.",
            )

        raw_output = stdout_buffer.getvalue()
        if len(raw_output) > cls.MAX_OUTPUT_CHARS:
            raw_output = raw_output[: cls.MAX_OUTPUT_CHARS] + "\n...[output truncated]"

        if exec_error:
            return SandboxExecutionResult(
                success=False,
                output=raw_output,
                value=None,
                execution_time_ms=elapsed_ms,
                error=f"{type(exec_error).__name__}: {str(exec_error)}",
            )

        final_val = captured_value_holder.get("__result_val__")
        return SandboxExecutionResult(
            success=True,
            output=raw_output.strip(),
            value=final_val,
            execution_time_ms=elapsed_ms,
            error=None,
        )

    @classmethod
    def execute(
        cls,
        code: str,
        timeout_seconds: Optional[float] = None,
        context_vars: Optional[Dict[str, Any]] = None,
        prefer_subprocess: bool = True,
    ) -> SandboxExecutionResult:
        """Execute Python calculation script with process-level isolation and strict resource limits."""
        start_time = time.perf_counter()
        if isinstance(cls, type):
            eff_cls = cls
            timeout = timeout_seconds or eff_cls.DEFAULT_TIMEOUT_SECONDS
        else:
            eff_cls = cls.__class__
            timeout = timeout_seconds or getattr(cls, "timeout_seconds", eff_cls.DEFAULT_TIMEOUT_SECONDS)

        # 1. AST Security Validation (static analysis happens first)
        try:
            tree = cls.validate_code(code)
        except Exception as err:
            return SandboxExecutionResult(
                success=False,
                output="",
                value=None,
                execution_time_ms=(time.perf_counter() - start_time) * 1000.0,
                error=str(err),
            )

        # 2. Try isolated child process execution for true OS-level memory/CPU bounds
        if prefer_subprocess:
            try:
                import multiprocessing
                ctx = multiprocessing.get_context("spawn")
                result_queue = ctx.Queue()

                process = ctx.Process(
                    target=_subprocess_sandbox_worker,
                    args=(code, context_vars, result_queue, eff_cls.MAX_OUTPUT_CHARS),
                    daemon=True,
                )
                process.start()
                process.join(timeout=timeout)

                elapsed_ms = (time.perf_counter() - start_time) * 1000.0

                if process.is_alive():
                    # Process exceeded hard timeout: forcefully terminate to prevent resource starvation
                    process.terminate()
                    process.join(timeout=0.2)
                    if process.is_alive():
                        process.kill()
                    return SandboxExecutionResult(
                        success=False,
                        output="",
                        value=None,
                        execution_time_ms=elapsed_ms,
                        error=f"Execution timed out after {timeout} seconds.",
                    )

                if not result_queue.empty():
                    res = result_queue.get_nowait()
                    return SandboxExecutionResult(
                        success=res["success"],
                        output=res["output"].strip(),
                        value=res["value"],
                        execution_time_ms=elapsed_ms,
                        error=res["error"],
                    )
            except Exception:
                # Subprocess creation failed (e.g. pickling error or restricted environment), fall through to thread
                pass

        # 3. In-process thread execution fallback
        return cls._execute_in_thread(
            code=code,
            tree=tree,
            timeout=timeout,
            start_time=start_time,
            context_vars=context_vars,
        )
