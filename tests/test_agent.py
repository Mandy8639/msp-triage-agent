"""End-to-end tests for the triage agent."""

from __future__ import annotations

import pytest

from msp_triage.agent import TriageAgent
from tests.conftest import clean_case


def test_clean_case_proposes_applies_and_sends_with_both_gates(agent) -> None:
    result = agent.run(clean_case(), approve_resolution=True, approve_apply=True)
    assert result.decision == "PROPOSE"
    assert result.resolution is not None
    assert result.resolution.ticket_id == "T001"  # most urgent confirmed match
    assert result.resolution.status == "draft"
    assert result.resolution.applied is False
    assert result.resolution.kb_article_id == "KB001"
    assert result.draft is not None
    assert result.draft.sent is False
    assert result.draft.to_client_id == "C01"
    assert result.published is True
    assert result.applied is True
    assert result.sent is True
    assert result.spend_usd == 0.0
    assert result.gates_checked == ["resolution", "apply"]
    assert result.provenance == ["T001", "agreement-001"]


def test_clean_case_resolution_carries_the_client_message_draft(agent) -> None:
    result = agent.run(clean_case(), approve_resolution=True, approve_apply=True)
    assert result.resolution is not None
    assert result.draft is result.resolution.client_message
    assert result.draft.purpose == "confirm_resolution"
    assert "T001" in result.draft.subject
    assert "KB001" in result.draft.body


def test_plan_is_the_three_allowlisted_tools(agent) -> None:
    assert agent.plan() == ["ticket_search", "kb_lookup", "resolution_draft"]


def test_agent_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match="unknown mode"):
        TriageAgent(mode="oracle")


def test_remediation_holds(agent) -> None:
    data = clean_case()
    data["remediation_needed"] = [
        "Printer queue stuck requires client approval for a production reboot "
        "during business hours — a human must complete this."
    ]
    result = agent.run(data, approve_resolution=True, approve_apply=True)
    assert result.decision == "HOLD"
    assert result.published is False
    assert result.applied is False
    assert result.sent is False


def test_live_agent_refuses_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    agent = TriageAgent(mode="live")
    with pytest.raises(RuntimeError, match="no ANTHROPIC_API_KEY"):
        agent.run(clean_case(), approve_resolution=True, approve_apply=True)
