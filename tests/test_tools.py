"""Tests for the three allowlisted tools."""

from __future__ import annotations

import pytest

from msp_triage.inventory import KB_BY_ID
from msp_triage.packet import case_from_dict, kb_from_dict
from msp_triage.tools import (
    client_message,
    kb_lookup,
    read_case,
    resolution_draft,
    ticket_search,
)
from tests.conftest import clean_case, ticket_dict


def test_ticket_search_returns_only_matching_tickets() -> None:
    case = case_from_dict(clean_case())
    matches = ticket_search(case)
    assert [m.ticket.id for m in matches] == ["T001", "T031"]
    assert matches[0].kb_article_id == "KB001"


def test_ticket_search_excludes_other_clients() -> None:
    data = clean_case()
    data["tickets"] = [ticket_dict("T001")]  # belongs to C01
    data["client_id"] = "C02"
    case = case_from_dict(data)
    assert ticket_search(case) == []


def test_ticket_search_excludes_duplicates() -> None:
    data = clean_case()
    data["tickets"] = [ticket_dict("T029"), ticket_dict("T030")]
    data["client_id"] = "C14"
    data["client_name"] = "Ironwood Realty"
    data["kind"] = "incident"
    data["severity"] = "P3"
    data["sla_hours"] = 24
    case = case_from_dict(data)
    assert ticket_search(case) == []


def test_ticket_search_excludes_unknown_sla_or_kb() -> None:
    data = clean_case()
    data["tickets"] = [ticket_dict("T010"), ticket_dict("T022")]
    data["client_id"] = "C10"
    data["client_name"] = "Pinnacle Healthcare"
    data["severity"] = "P2"
    data["sla_hours"] = 8
    case = case_from_dict(data)
    assert ticket_search(case) == []


def test_ticket_search_excludes_breached_and_mismatched() -> None:
    breached = ticket_dict("T001")
    breached["hours_open"] = 30  # open 30h against a 4h SLA
    mismatched = ticket_dict("T031")
    mismatched["sla_hours"] = 48  # P1 may carry at most 4h
    data = clean_case()
    data["tickets"] = [breached, mismatched]
    case = case_from_dict(data)
    assert ticket_search(case) == []


def test_ticket_search_sorts_most_urgent_first() -> None:
    data = clean_case()
    data["tickets"] = [ticket_dict("T031"), ticket_dict("T001")]
    case = case_from_dict(data)
    assert [m.ticket.id for m in ticket_search(case)] == ["T001", "T031"]


def test_kb_lookup_returns_visible_articles_only() -> None:
    case_c01 = case_from_dict(clean_case())
    ids_c01 = [article.id for article in kb_lookup(case_c01)]
    assert "KB011" in ids_c01  # Acme's own runbook
    assert "KB012" not in ids_c01  # Helix's runbook is not visible to Acme
    data = clean_case()
    data["client_id"] = "C02"
    data["client_name"] = "BlueRiver Retail"
    case_c02 = case_from_dict(data)
    ids_c02 = [article.id for article in kb_lookup(case_c02)]
    assert "KB011" not in ids_c02
    assert "KB001" in ids_c02  # shared articles are visible to every client


def test_kb_lookup_filters_by_kind() -> None:
    data = clean_case()
    data["kind"] = "request"
    case = case_from_dict(data)
    ids = [article.id for article in kb_lookup(case)]
    assert ids == ["KB003", "KB009"]


def test_resolution_draft_is_draft_only() -> None:
    case = case_from_dict(clean_case())
    resolution = resolution_draft(case, "T001")
    assert resolution.status == "draft"
    assert resolution.applied is False
    assert resolution.sent is False
    assert resolution.client_message.sent is False
    assert resolution.ticket_id == "T001"
    assert resolution.client_id == "C01"
    assert "Human confirmation required" in resolution.steps[-1]


def test_resolution_draft_cites_kb_and_redacts_pii() -> None:
    data = clean_case()
    data["tickets"] = [ticket_dict("T002")]
    data["client_id"] = "C02"
    data["client_name"] = "BlueRiver Retail"
    data["severity"] = "P2"
    data["sla_hours"] = 8
    case = case_from_dict(data)
    resolution = resolution_draft(case, "T002")
    assert resolution.kb_article_id == "KB002"
    assert "KB002" in resolution.steps[1]
    assert "j.smith@blueriver-retail.example" not in resolution.summary
    assert "[EMAIL REDACTED]" in resolution.summary
    assert "212-555-0147" not in resolution.client_message.body
    assert "[PHONE REDACTED]" in resolution.client_message.body


def test_resolution_draft_rejects_unmatched_ticket() -> None:
    case = case_from_dict(clean_case())
    with pytest.raises(ValueError, match="not a confirmed match"):
        resolution_draft(case, "T013")  # belongs to another client


def test_resolution_draft_rejects_kb_not_visible_to_client() -> None:
    data = clean_case()
    ticket = ticket_dict("T001")
    ticket["kb_article_id"] = "KB012"  # Helix Pharma's runbook, not Acme's
    data["tickets"] = [ticket]
    case = case_from_dict(data)
    with pytest.raises(ValueError, match="not visible to client"):
        resolution_draft(case, "T001")


def test_client_message_purposes() -> None:
    case = case_from_dict(clean_case())
    ticket = case.tickets[0]
    article = kb_from_dict(KB_BY_ID["KB001"])
    confirm = client_message(case, ticket, article, "confirm_resolution")
    assert confirm.purpose == "confirm_resolution"
    assert confirm.sent is False
    assert "Please confirm before we apply it" in confirm.body
    info = client_message(case, ticket, article, "request_info")
    assert "need one more detail" in info.body
    escalation = client_message(case, ticket, article, "escalation_notice")
    assert "escalated to a human engineer" in escalation.body
    with pytest.raises(ValueError, match="unknown message purpose"):
        client_message(case, ticket, article, "negotiate")


def test_read_case_rejects_missing_fields() -> None:
    data = clean_case()
    del data["severity"]
    with pytest.raises(ValueError, match="missing required field"):
        read_case(data)
