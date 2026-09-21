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
):
    """Stream response tokens and citations using Server-Sent Events (SSE)."""
    # Scope department if explicitly requested in payload
    if req.department_id and req.department_id != "ALL":
        user_ctx.department_id = req.department_id

    effective_gemini_key = x_gemini_api_key or req.api_key

    async def generate() -> AsyncGenerator[str, None]:
        event_queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        trace_id = req.session_id or f"tr_{uuid.uuid4().hex[:12]}"

        def on_event(event: OperationalEvent) -> None:
            serialized = PublicEventSerializer.serialize(event)
            if serialized:
                loop.call_soon_threadsafe(event_queue.put_nowait, serialized)

        try:
            if req.model_id and not ModelRegistry(db).get(req.model_id):
                raise ValueError(f"Unknown model artifact '{req.model_id}'.")
            agent = AgentStateMachine(
                db,
                model_id=req.model_id,
                backend=req.backend,
                api_key=effective_gemini_key,
            )

            async def run_agent():
                return await loop.run_in_executor(
                    None,
                    lambda: agent.run(
                        query=req.query,
                        user_context=user_ctx,
                        session_id=req.session_id,
                        on_event=on_event,
                        trace_id=trace_id,
                    ),
                )

            run_task = asyncio.create_task(run_agent())

            # Stream operational status events in real time as the state machine transitions
            while not run_task.done():
                try:
                    event_payload = await asyncio.wait_for(event_queue.get(), timeout=0.03)
                    yield f"event: status\ndata: {json.dumps(event_payload)}\n\n"
                except asyncio.TimeoutError:
                    continue

            # Drain any remaining queued operational events
            while not event_queue.empty():
                event_payload = event_queue.get_nowait()
                yield f"event: status\ndata: {json.dumps(event_payload)}\n\n"

            response = await run_task

            # 1. Start Event
            yield f"event: start\ndata: {json.dumps({'session_id': response.session_id, 'model_id': response.model_id, 'query': req.query, 'trace_id': trace_id})}\n\n"

            # 2. Simulated Token Streaming
            # Keep each word's surrounding whitespace verbatim: splitting on
            # whitespace and rejoining with single spaces flattened the answer
            # onto one line, so the Markdown structure the model produced
            # (paragraphs, bullet lists, headings) never reached the UI.
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

            # 6. Completion Event with Latency & Diagnostics
            yield f"event: done\ndata: {json.dumps({'latency_ms': response.latency_ms, 'validation_passed': response.validation_passed, 'is_no_answer': response.is_no_answer, 'is_high_risk': response.is_high_risk})}\n\n"

        except Exception as e:
            while not event_queue.empty():
                try:
                    event_payload = event_queue.get_nowait()
                    yield f"event: status\ndata: {json.dumps(event_payload)}\n\n"
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
