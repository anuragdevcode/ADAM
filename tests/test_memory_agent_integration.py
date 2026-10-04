"""Integration tests connecting AgentStateMachine with Phase 05 conversation memory."""

import pytest

from adam.agent.state_machine import AgentStateMachine
from adam.db.models import ChatSession, ChatTurn, SessionSummary
from adam.memory.session import SessionAccessDeniedError, SessionManager
from adam.memory.summary import SessionSummarizer
from adam.rag.models import UserContext


def test_agent_memory_multi_turn_flow(db_session):
    """Verify that multi-turn queries in the same session retain summary and record encrypted turns."""
    user = UserContext(user_id="desk_officer_1", clearance_level="PUBLIC")
    agent = AgentStateMachine(db_session)

    # Turn 1: Initial query
    resp1 = agent.run(
        query="What is the official procedure for filing an RTI application?",
        user_context=user,
    )
    assert resp1.session_id is not None
    session_id = resp1.session_id

    # Verify session and turns recorded in DB
    manager = SessionManager(db_session)
    turns = manager.get_turns(session_id, requesting_user_id="desk_officer_1")
    assert len(turns) == 2  # 1 user turn, 1 assistant turn
    assert turns[0].role == "user"
    assert "RTI application" in turns[0].content
    assert turns[1].role == "assistant"

    # Verify summary generated
    summarizer = SessionSummarizer(db_session)
    summary = summarizer.get_summary(session_id, requesting_user_id="desk_officer_1")
    assert summary is not None
    assert len(summary.source_turn_ids) == 2

    # Turn 2: Follow-up query in same session
    resp2 = agent.run(
        query="Are there specific fee exemptions for BPL applicants in Uttarakhand?",
        user_context=user,
        session_id=session_id,
    )
    assert resp2.session_id == session_id

    # Turns should now be 4
    db_session.expire_all()
    turns_after = manager.get_turns(session_id, requesting_user_id="desk_officer_1")
    assert len(turns_after) == 4
    assert turns_after[2].role == "user"
    assert "BPL applicants" in turns_after[2].content

    # Summary should now track all 4 turns
    db_session.expire_all()
    summary_after = summarizer.get_summary(session_id, requesting_user_id="desk_officer_1")
    assert summary_after is not None
    assert len(summary_after.source_turn_ids) == 4


def test_agent_cross_user_session_hijack_blocked(db_session):
    """Acceptance Criterion 1: Passing another user's session_id to agent.run is strictly blocked."""
    agent = AgentStateMachine(db_session)

    # User 1 starts session
    user1 = UserContext(user_id="user_alpha", clearance_level="PUBLIC")
    resp1 = agent.run(
        query="What are the casual leave rules?",
        user_context=user1,
    )
    session_id = resp1.session_id

    # User 2 attempts to supply user 1's session_id
    user2 = UserContext(user_id="user_attacker", clearance_level="PUBLIC")
    with pytest.raises(SessionAccessDeniedError):
        agent.run(
            query="Tell me what the previous question was about",
            user_context=user2,
            session_id=session_id,
        )
