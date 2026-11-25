"""Shared fixtures for the triage tests."""

from __future__ import annotations

import pytest

from msp_triage.agent import TriageAgent
from msp_triage.inventory import BY_ID


def ticket_dict(ticket_id: str) -> dict:
    ticket = dict(BY_ID[ticket_id])
    ticket["attachments"] = list(ticket["attachments"])
    return ticket


def clean_case() -> dict:
    """A clean P1 incident case: T001 and T031 both satisfy it."""
    return {
        "id": "MT-T01",
        "category": "clean",
        "client_id": "C01",
        "client_name": "Acme Manufacturing",
        "request_text": "VPN gateway down for 12 users at Acme Manufacturing",
        "kind": "incident",
        "severity": "P1",
        "sla_hours": 4,
        "tickets": [ticket_dict("T001"), ticket_dict("T031")],
        "messages": [
            {
                "text": "Ticket T001: VPN gateway down for 12 users. Severity P1, SLA 4h.",
                "source": "T001",
                "asserts": {"severity": "P1", "sla_hours": 4},
            },
            {
                "text": "KB001 covers this: see the knowledge base.",
                "source": "T001",
                "asserts": {"kb_article": "KB001"},
            },
        ],
        "claims": [
            {
                "text": "Acme Manufacturing has an active support agreement covering this service.",
                "source": "agreement-001",
            }
        ],
        "required_evidence": ["T001:sla_hours", "T001:kb_article"],
        "remediation_needed": [],
    }


@pytest.fixture
def agent() -> TriageAgent:
    return TriageAgent(mode="stub")
