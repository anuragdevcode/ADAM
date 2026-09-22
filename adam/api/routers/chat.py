"""Streaming SSE chat endpoint supporting model selection and department scoping."""

import asyncio
import json
import re
import uuid
from typing import AsyncGenerator, Optional
from fastapi import APIRouter, Depends, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from adam.agent.state_machine import AgentStateMachine
from adam.api.deps import get_db, get_user_context
from adam.model.registry import ModelRegistry
from adam.observability.events import OperationalEvent
from adam.observability.serializer import PublicEventSerializer
from adam.rag.models import UserContext

router = APIRouter()


class ChatRequest(BaseModel):
    model_config = {"protected_namespaces": ()}

    query: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    model_id: Optional[str] = None
    backend: Optional[str] = None
    department_id: Optional[str] = None
    api_key: Optional[str] = None


@router.post("/chat")
async def chat_endpoint(
    req: ChatRequest,
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(get_user_context),
    x_gemini_api_key: Optional[str] = Header(None),
    x_adam_settings_preset: Optional[str] = Header(None),
    x_adam_top_k: Optional[str] = Header(None),
    x_adam_max_tokens: Optional[str] = Header(None),
    x_adam_temperature: Optional[str] = Header(None),
):
    """Stream response tokens and citations using Server-Sent Events (SSE)."""
    # Scope department if explicitly requested in payload
    if req.department_id and req.department_id != "ALL":
        user_ctx.department_id = req.department_id

    effective_gemini_key = x_gemini_api_key or req.api_key

    # Build AdvancedSettingsBundle from optional headers
    _settings_bundle = None
    try:
        from adam.settings.advanced_settings import (
            AdvancedSettingsManager, AdvancedSettingsBundle,
            PRESET_BUNDLES, AdvancedSettingsPreset, DEFAULT_BUNDLE,
        )
        user_id = getattr(user_ctx, "user_id", "anonymous") or "anonymous"
        # Start from DB-persisted settings (or defaults)
        manager = AdvancedSettingsManager(db, user_id=user_id)
        _settings_bundle = manager.load()

        # Apply per-request header overrides
        if x_adam_settings_preset:
            try:
                preset = AdvancedSettingsPreset(x_adam_settings_preset.upper())
                _settings_bundle = AdvancedSettingsBundle.from_dict(PRESET_BUNDLES[preset].to_dict())
            except (ValueError, KeyError):
                pass
        if x_adam_top_k:
            try:
                _settings_bundle.retrieval.top_k = max(3, min(20, int(x_adam_top_k)))
            except (ValueError, TypeError):
                pass
        if x_adam_max_tokens:
            try:
                _settings_bundle.generation.max_tokens_rag = max(256, min(4096, int(x_adam_max_tokens)))
            except (ValueError, TypeError):
                pass
        if x_adam_temperature:
            try:
                _settings_bundle.generation.temperature_rag = max(0.0, min(0.2, float(x_adam_temperature)))
            except (ValueError, TypeError):
                pass
    except Exception:
        _settings_bundle = None  # Fall back to defaults on any error

    async def generate() -> AsyncGenerator[str, None]:
        session_id = req.session_id
        if not session_id:
            from adam.memory.session import SessionManager
            sm = SessionManager(db)
            new_sess = sm.create_session(
                user_id=user_ctx.user_id,
                classification_ceiling=user_ctx.clearance_level,
            )
            session_id = new_sess.id

        event_queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        trace_id = session_id or f"tr_{uuid.uuid4().hex[:12]}"
        start_event_emitted = False
        captured_session_id = session_id

        def on_event(event: OperationalEvent) -> None:
            nonlocal captured_session_id
            if event.data and event.data.get("session_id"):
                captured_session_id = event.data["session_id"]
            serialized = PublicEventSerializer.serialize(event)
            if serialized:
                loop.call_soon_threadsafe(event_queue.put_nowait, ("status", serialized, captured_session_id))

        def token_callback(chunk: str) -> None:
            if chunk:
                loop.call_soon_threadsafe(event_queue.put_nowait, ("token", {"text": chunk}, None))

        try:
            from adam.model.policy import validate_air_gapped_model_policy, AirGappedSovereigntyViolationError
            allowed_air_gap, air_gap_reason = validate_air_gapped_model_policy(
                model_id=req.model_id,
                clearance_level=user_ctx.clearance_level,
                backend=req.backend,
            )
            if not allowed_air_gap:
                raise AirGappedSovereigntyViolationError(air_gap_reason)

            if req.model_id and not ModelRegistry(db).get(req.model_id):
                raise ValueError(f"Unknown model artifact '{req.model_id}'.")
            agent = AgentStateMachine(
                db,
                model_id=req.model_id,
                backend=req.backend,
                api_key=effective_gemini_key,
            )

            async def run_agent():
                def _invoke_agent():
                    run_kwargs = {
                        "query": req.query,
                        "user_context": user_ctx,
                        "session_id": session_id,
                        "on_event": on_event,
                        "trace_id": trace_id,
                    }
                    import inspect
                    try:
                        target_func = getattr(agent.run, "side_effect", None) or agent.run
                        sig = inspect.signature(target_func)
                        if "token_callback" in sig.parameters:
                            run_kwargs["token_callback"] = token_callback
                        if "settings_bundle" in sig.parameters and _settings_bundle is not None:
                            run_kwargs["settings_bundle"] = _settings_bundle
                    except Exception:
                        pass
                    return agent.run(**run_kwargs)

                return await loop.run_in_executor(None, _invoke_agent)

            run_task = asyncio.create_task(run_agent())

            # Stream operational status events and live tokens in real time as state machine transitions
            tokens_streamed = 0
            while not run_task.done():
                try:
                    kind, payload, sid = await asyncio.wait_for(event_queue.get(), timeout=0.03)
                    if kind == "status":
                        if not start_event_emitted and sid:
                            yield f"event: start\ndata: {json.dumps({'session_id': sid, 'model_id': req.model_id or 'qwen2.5:3b', 'query': req.query, 'trace_id': trace_id})}\n\n"
                            start_event_emitted = True
                        yield f"event: status\ndata: {json.dumps(payload)}\n\n"
                    elif kind == "token":
                        if not start_event_emitted:
                            eff_sid = captured_session_id or req.session_id or trace_id
                            yield f"event: start\ndata: {json.dumps({'session_id': eff_sid, 'model_id': req.model_id or 'qwen2.5:3b', 'query': req.query, 'trace_id': trace_id})}\n\n"
                            start_event_emitted = True
                        tokens_streamed += 1
                        yield f"event: token\ndata: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    continue

            # Drain any remaining queued events
            while not event_queue.empty():
                kind, payload, sid = event_queue.get_nowait()
                if kind == "status":
                    if not start_event_emitted and sid:
                        yield f"event: start\ndata: {json.dumps({'session_id': sid, 'model_id': req.model_id or 'qwen2.5:3b', 'query': req.query, 'trace_id': trace_id})}\n\n"
                        start_event_emitted = True
                    yield f"event: status\ndata: {json.dumps(payload)}\n\n"
                elif kind == "token":
                    if not start_event_emitted:
                        eff_sid = captured_session_id or req.session_id or trace_id
                        yield f"event: start\ndata: {json.dumps({'session_id': eff_sid, 'model_id': req.model_id or 'qwen2.5:3b', 'query': req.query, 'trace_id': trace_id})}\n\n"
                        start_event_emitted = True
                    tokens_streamed += 1
                    yield f"event: token\ndata: {json.dumps(payload)}\n\n"

            response = await run_task

            # 1. Start Event (ensure emitted if not already done)
            if not start_event_emitted:
                yield f"event: start\ndata: {json.dumps({'session_id': response.session_id, 'model_id': response.model_id, 'query': req.query, 'trace_id': trace_id})}\n\n"
                start_event_emitted = True

            # 2. Simulated Token Streaming Fallback
            # If no live tokens were streamed (e.g. non-streaming fallback runtime or mock),
            # stream the full answer word-by-word.
            if tokens_streamed == 0 and response.answer:
                for chunk in re.findall(r"\s*\S+\s*", response.answer):
                    yield f"event: token\ndata: {json.dumps({'text': chunk})}\n\n"
                    await asyncio.sleep(0.015)

            # 3. Citations Event
            citations_data = [cit.to_dict() for cit in response.citations]
            yield f"event: citations\ndata: {json.dumps(citations_data)}\n\n"

            # 4. Currency / Precedent Alerts
            if response.currency_banners:
                yield f"event: banners\ndata: {json.dumps(response.currency_banners)}\n\n"

            # 5. Search Suggestions if No Answer
            if response.search_suggestions:
                yield f"event: suggestions\ndata: {json.dumps(response.search_suggestions)}\n\n"

            # 6. Reasoning Trail & State Transition History
            state_history_data = [
                t.to_dict() if hasattr(t, "to_dict") else {
                    "from": getattr(t, "from_state", ""),
                    "to": getattr(t, "to_state", ""),
                    "at": getattr(t, "timestamp", ""),
                    "notes": getattr(t, "notes", None),
                    "duration_ms": getattr(t, "duration_ms", 0.0),
                    "stage": getattr(t, "stage", None),
                    "abstention_reason": getattr(t, "abstention_reason", None),
                }
                for t in response.state_history
            ]
            trail_payload = {
                "state_history": state_history_data,
                "per_stage_latency": getattr(response, "per_stage_latency_ms", {}),
                "abstention_reason": getattr(response, "abstention_reason", None),
                "latency_ms": response.latency_ms,
                "plan": getattr(response, "plan", None),
                "computation_results": getattr(response, "computation_results", []),
                "research_summary": getattr(response, "research_summary", None),
                "subagents": getattr(response, "subagents", []),
            }
            yield f"event: trail\ndata: {json.dumps(trail_payload)}\n\n"

            # 7. Agentic Execution Plan, Sandbox Calculations, and Research Orchestration
            if getattr(response, "plan", None):
                yield f"event: plan\ndata: {json.dumps(response.plan)}\n\n"
            if getattr(response, "computation_results", None):
                yield f"event: calculations\ndata: {json.dumps(response.computation_results)}\n\n"
            if getattr(response, "research_summary", None) or getattr(response, "subagents", None):
                yield f"event: research\ndata: {json.dumps({'summary': getattr(response, 'research_summary', None), 'subagents': getattr(response, 'subagents', [])})}\n\n"

            # 8. Completion Event with Latency & Diagnostics
            done_payload = {
                "latency_ms": response.latency_ms,
                "validation_passed": response.validation_passed,
                "is_no_answer": response.is_no_answer,
                "is_high_risk": response.is_high_risk,
                "state_history": state_history_data,
                "per_stage_latency": getattr(response, "per_stage_latency_ms", {}),
                "abstention_reason": getattr(response, "abstention_reason", None),
                "plan": getattr(response, "plan", None),
                "computation_results": getattr(response, "computation_results", []),
                "research_summary": getattr(response, "research_summary", None),
                "subagents": getattr(response, "subagents", []),
            }
            yield f"event: done\ndata: {json.dumps(done_payload)}\n\n"

        except Exception as e:
            while not event_queue.empty():
                try:
                    item = event_queue.get_nowait()
                    if isinstance(item, tuple) and len(item) >= 2 and item[0] == "status":
                        yield f"event: status\ndata: {json.dumps(item[1])}\n\n"
                except Exception:
                    break
            raw_err = str(e)
            if effective_gemini_key and effective_gemini_key in raw_err:
                raw_err = raw_err.replace(effective_gemini_key, "[REDACTED_KEY]")

            lower_err = raw_err.lower()
            category = "general"
            suggested_action = "retry"
            title = "AI Model Error"
            cmd_hint = None

            if "cannot connect to local ollama" in lower_err or "ollama server is offline" in lower_err or "connection refused" in lower_err:
                category = "ollama_offline"
                title = "Local Ollama Service Offline"
                suggested_action = "start_ollama"
                cmd_hint = "ollama serve"
            elif "not downloaded in local ollama" in lower_err or "not downloaded in ollama" in lower_err or "not pulled" in lower_err:
                category = "model_not_pulled"
                title = "Local Model Not Downloaded"
                suggested_action = "pull_model"
                m = re.search(r"['\"](.*?)['\"]", raw_err)
                tag = m.group(1) if m else "qwen2.5:3b"
                cmd_hint = f"ollama pull {tag}"
            elif "gemini api key is not configured" in lower_err or "api key cannot be empty" in lower_err:
                category = "gemini_key_missing"
                title = "Gemini API Key Required"
                suggested_action = "configure_gemini"
            elif "gemini api returned status 400" in lower_err or "gemini api returned status 403" in lower_err or "invalid api key" in lower_err or "api_key_invalid" in lower_err:
                category = "gemini_api_error"
                title = "Invalid Gemini API Key"
                suggested_action = "configure_gemini"
            elif "gemini api returned status 429" in lower_err or "resource_exhausted" in lower_err or "rate limit" in lower_err:
                category = "rate_limit"
                title = "API Rate Limit Exceeded"
                suggested_action = "retry"
            elif "gemini api returned status 404" in lower_err:
                category = "gemini_api_error"
                title = "Gemini Model Unavailable"
                suggested_action = "configure_gemini"
            elif "air-gapped" in lower_err or "sovereignty" in lower_err:
                category = "air_gapped_policy_violation"
                title = "Air-Gapped Sovereignty Policy Enforcement"
                suggested_action = "switch_to_local_model"
                cmd_hint = "Switch to local Ollama (qwen2.5:3b)"

            error_payload = {
                "message": raw_err,
                "title": title,
                "category": category,
                "suggested_action": suggested_action,
                "command_hint": cmd_hint,
            }
            yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
