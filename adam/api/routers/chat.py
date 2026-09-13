"""Streaming SSE chat endpoint supporting model selection and department scoping."""

import asyncio
import json
from typing import AsyncGenerator, Optional
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from adam.agent.state_machine import AgentStateMachine
from adam.api.deps import get_db, get_user_context
from adam.model.registry import ModelRegistry
from adam.rag.models import UserContext

from fastapi import APIRouter, Depends, Header

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
        try:
            if req.model_id and not ModelRegistry(db).get(req.model_id):
                raise ValueError(f"Unknown model artifact '{req.model_id}'.")
            agent = AgentStateMachine(
                db,
                model_id=req.model_id,
                backend=req.backend,
                api_key=effective_gemini_key,
            )

            response = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: agent.run(
                    query=req.query,
                    user_context=user_ctx,
                    session_id=req.session_id,
                ),
            )

            # 1. Start Event
            yield f"event: start\ndata: {json.dumps({'session_id': response.session_id, 'model_id': response.model_id, 'query': req.query})}\n\n"

            # 2. Simulated Token Streaming
            words = response.answer.split()
            for i, word in enumerate(words):
                space = " " if i < len(words) - 1 else ""
                yield f"event: token\ndata: {json.dumps({'text': word + space})}\n\n"
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
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
