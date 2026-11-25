"""Live-mode safety tests: refusal paths only, no network calls."""

from __future__ import annotations

import pytest

from msp_triage.agent import TriageAgent
from msp_triage.packet import case_from_dict
from msp_triage.reasoner import LiveReasoner, SpendTracker
from tests.conftest import clean_case


def test_live_mode_refuses_without_key_even_when_gates_approved(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    agent = TriageAgent(mode="live")
    with pytest.raises(RuntimeError, match="no ANTHROPIC_API_KEY"):
        agent.run(clean_case(), approve_resolution=True, approve_apply=True)


def test_live_reasoner_default_model_is_haiku(tmp_path) -> None:
    reasoner = LiveReasoner(spend_path=str(tmp_path / "spend.json"))
    assert reasoner.model == "claude-haiku-4-5"


def test_live_mode_refuses_unknown_model(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    reasoner = LiveReasoner(model="claude-opus-4-5", spend_path=str(tmp_path / "spend.json"))
    case = case_from_dict(clean_case())
    with pytest.raises(RuntimeError, match="not in the priced-model table"):
        reasoner.decide(case, [])


def test_live_mode_refuses_when_daily_cap_reached(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    spend_path = tmp_path / "spend.json"
    SpendTracker(str(spend_path)).record(1.00)
    reasoner = LiveReasoner(spend_path=str(spend_path))
    case = case_from_dict(clean_case())
    with pytest.raises(RuntimeError, match="daily cap"):
        reasoner.decide(case, [])
