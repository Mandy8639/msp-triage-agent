"""Tests for the stub and live reasoners."""

from __future__ import annotations

import pytest

from msp_triage.packet import case_from_dict
from msp_triage.reasoner import (
    DEFAULT_MODEL,
    PRICED_MODELS,
    LiveReasoner,
    SpendTracker,
    StubReasoner,
)
from msp_triage.tools import ticket_search
from tests.conftest import clean_case


def _flags(**overrides):
    base = {
        "injection": False,
        "fabrication": False,
        "missing": False,
        "conflicts": False,
        "violations": False,
        "remediation": False,
    }
    base.update(overrides)
    return base


def test_stub_proposes_when_everything_is_clean() -> None:
    case = case_from_dict(clean_case())
    assert StubReasoner().decide(case, ticket_search(case), **_flags()) == "PROPOSE"


def test_stub_priority_injection_beats_everything() -> None:
    case = case_from_dict(clean_case())
    decision = StubReasoner().decide(
        case, ticket_search(case), **_flags(injection=True, violations=True, missing=True)
    )
    assert decision == "BLOCK"


def test_stub_priority_pause_beats_hold() -> None:
    case = case_from_dict(clean_case())
    decision = StubReasoner().decide(
        case, ticket_search(case), **_flags(violations=True, missing=True, fabrication=True)
    )
    assert decision == "PAUSE"


def test_stub_holds_on_missing_remediation_fabrication_or_no_match() -> None:
    case = case_from_dict(clean_case())
    for flags in (
        _flags(missing=True),
        _flags(remediation=True),
        _flags(fabrication=True),
    ):
        assert StubReasoner().decide(case, ticket_search(case), **flags) == "HOLD"
    assert StubReasoner().decide(case, [], **_flags()) == "HOLD"


def test_priced_model_table_is_haiku_only() -> None:
    assert PRICED_MODELS == {
        "claude-haiku-4-5": {"input_usd_per_mtok": 1.00, "output_usd_per_mtok": 5.00}
    }
    assert DEFAULT_MODEL == "claude-haiku-4-5"


def test_live_refuses_without_api_key(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    reasoner = LiveReasoner(spend_path=str(tmp_path / "spend.json"))
    case = case_from_dict(clean_case())
    with pytest.raises(RuntimeError, match="no ANTHROPIC_API_KEY"):
        reasoner.decide(case, ticket_search(case))


def test_live_refuses_unknown_model(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    reasoner = LiveReasoner(model="claude-opus-4-5", spend_path=str(tmp_path / "spend.json"))
    case = case_from_dict(clean_case())
    with pytest.raises(RuntimeError, match="not in the priced-model table"):
        reasoner.decide(case, ticket_search(case))


def test_live_refuses_when_daily_cap_reached(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    spend_path = tmp_path / "spend.json"
    tracker = SpendTracker(str(spend_path))
    tracker.record(1.00)
    reasoner = LiveReasoner(spend_path=str(spend_path))
    case = case_from_dict(clean_case())
    with pytest.raises(RuntimeError, match="daily cap"):
        reasoner.decide(case, ticket_search(case))


def test_spend_tracker_resets_on_a_new_day(tmp_path) -> None:
    spend_path = tmp_path / "spend.json"
    spend_path.write_text('{"date": "2020-01-01", "spent_usd": 1.00}', encoding="utf-8")
    assert SpendTracker(str(spend_path)).today_spent() == 0.0


def test_live_parse_accepts_only_the_four_decisions() -> None:
    assert LiveReasoner._parse("propose") == "PROPOSE"
    assert LiveReasoner._parse("We should HOLD this one.") == "HOLD"
    with pytest.raises(RuntimeError, match="unparseable"):
        LiveReasoner._parse("maybe later")
