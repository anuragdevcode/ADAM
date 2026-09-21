"""V1 Public & Gateway Chat API endpoint conforming to 07-backend-api.md."""

import asyncio
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Header, Request, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from adam.agent.state_machine import AgentStateMachine
from adam.api.deps import get_db, get_user_context, get_trace_id
from adam.api.services.reconstruction import AnswerReconstructionService
from adam.rag.models import UserContext

router = APIRouter(prefix="/v1", tags=["v1-chat"])


class V1ChatRequest(BaseModel):
    message: str = Field(..., description="The query or instruction message from the user/officer")
    language: Optional[str] = Field(default="hi", description="Preferred response language (e.g. 'hi' or 'en')")
    collection_ids: Optional[List[str]] = Field(default=None, description="Optional collection or department scope IDs")
    session_id: Optional[str] = Field(default=None, description="Active session ID for conversation continuity")

    model_config = {"protected_namespaces": ()}


class V1Citation(BaseModel):
    document_title: str
    department: str
    document_id: Optional[str] = None
    go_number: Optional[str] = None
    gazette_number: Optional[str] = None
    version_hash: str
    issue_date: Optional[str] = None
    page: int
    section: Optional[str] = None
    source_url: str
    retrieval_timestamp: str
    pdf_page_link: str
    currency_banner: Optional[str] = None
    disclaimer: str

    model_config = {"protected_namespaces": ()}


class V1ChatResponse(BaseModel):
    answer: str
    status: str = Field(..., description="One of: answered, abstained, needs_review")
    citations: List[V1Citation] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
    trace_id: str

    model_config = {"protected_namespaces": ()}


@router.post("/chat", response_model=V1ChatResponse)
async def v1_chat(
    req: V1ChatRequest,
    request: Request,
    db: Session = Depends(get_db),
    user_ctx: UserContext = Depends(get_user_context),
) -> V1ChatResponse:
    """Core V1 Chat endpoint.

    Accepts {message, language?, collection_ids?, session_id?} and returns
    {answer, status: answered|abstained|needs_review, citations[], limitations[], trace_id}.
    Citations contain strictly ACL-approved source metadata.
    Logs answer reconstruction provenance without leaking sensitive text.
    """
    trace_id = getattr(request.state, "trace_id", None) or request.headers.get("X-Trace-Id") or "trace_default"

    # Scope department/collection if provided
    if req.collection_ids and len(req.collection_ids) > 0:
        user_ctx.department_id = req.collection_ids[0]

    # Initialize bounded agent state machine
    agent = AgentStateMachine(db)

    # Run execution synchronously in threadpool to avoid blocking event loop
    try:
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: agent.run(
                query=req.message,
                user_context=user_ctx,
                session_id=req.session_id,
            ),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {str(exc)}") from exc

    # Determine status: answered | abstained | needs_review
    if resp.is_no_answer:
        outcome_status = "abstained"
    elif resp.is_high_risk or not resp.validation_passed:
        outcome_status = "needs_review"
    else:
        outcome_status = "answered"

    # Gather limitations (currency banners, validation errors, risk warnings)
    limitations: List[str] = []
    if resp.currency_banners:
        limitations.extend(resp.currency_banners)
    if resp.validation_errors:
        limitations.extend(resp.validation_errors)
    if resp.is_high_risk:
        limitations.append("High-risk statutory/legal query. Research brief issued; official legal confirmation required.")

    # Convert citations to ACL-approved output schema
    out_citations: List[V1Citation] = []
    cited_chunk_ids: List[str] = []
    index_version_ids: List[str] = []

    for c in resp.citations:
        c_dict = c.to_dict()
        out_citations.append(V1Citation(**c_dict))
        if c.version_hash and c.version_hash not in index_version_ids:
            index_version_ids.append(c.version_hash)

    # Record answer reconstruction provenance without logging raw sensitive message/answer text
    request_hash = AnswerReconstructionService.compute_request_hash(
        message=req.message,
        user_roles=user_ctx.roles,
        collection_ids=req.collection_ids,
    )

    AnswerReconstructionService.record_provenance(
        db=db,
        request_hash=request_hash,
        trace_id=trace_id,
        session_id=resp.session_id,
        user_id=user_ctx.user_id,
        model_id=resp.model_id,
        index_version_ids=index_version_ids,
        cited_chunk_ids=cited_chunk_ids,
        status=outcome_status,
    )

    return V1ChatResponse(
        answer=resp.answer,
        status=outcome_status,
        citations=out_citations,
        limitations=limitations,
        trace_id=trace_id,
    )
