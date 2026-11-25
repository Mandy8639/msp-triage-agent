"""Deterministic guardrail G1-G5.

Every rule is a pure function over the case, so the eval can reproduce it
exactly. No rule ever invents evidence: when evidence is missing the agent
abstains; when instructions appear inside ticket messages they are blocked;
when a ticket message contradicts the queue the run pauses. PII is
redacted before any draft leaves the queue, and a ticket from another
client is never acted on (per-client isolation).
"""

from __future__ import annotations

import re

from msp_triage.packet import Case, Claim, TicketMessage

# Maximum SLA hours a severity may carry. A ticket whose SLA exceeds its
# severity's ceiling is a policy violation (G5), not a fact to work around.
SEVERITY_MAX_SLA = {"P1": 4, "P2": 8, "P3": 24, "P4": 72}

# G4: substrings that mark an instruction injected into a ticket message.
# A message containing one of these is treated as an attempt to steer the
# agent, not as ticket evidence.
INJECTION_PATTERNS = (
    "ignore the",
    "ignore all",
    "override",
    "approve anyway",
    "disregard",
    "do not flag",
    "skip the check",
    "resolve it anyway",
    "close it anyway",
    "mark it resolved",
    "bypass",
    "pretend",
    "confirm without asking",
)

# G3: PII patterns redacted before any draft leaves the queue.
PII_PATTERNS = (
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "[EMAIL REDACTED]"),
    (
        re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b"),
        "[PHONE REDACTED]",
    ),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[SSN REDACTED]"),
)


def redact_pii(text: str) -> str:
    """G3: redact PII from text before it is quoted in any draft."""
    redacted = text
    for pattern, replacement in PII_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def scan_injection(messages: list[TicketMessage]) -> list[TicketMessage]:
    """G4: return the ticket messages that carry an injected instruction."""
    hits = []
    for message in messages:
        lowered = message.text.lower()
        if any(pattern in lowered for pattern in INJECTION_PATTERNS):
            hits.append(message)
    return hits


def scan_fabrication(claims: list[Claim]) -> list[Claim]:
    """G3: return the claims with no provenance source. They are dropped."""
    return [claim for claim in claims if not claim.source]


def cited_sources(case: Case) -> list[str]:
    """Provenance the agent is allowed to cite: sourced messages and claims."""
    sources = [message.source for message in case.messages]
    sources += [claim.source for claim in case.claims if claim.source]
    return sorted(set(sources))


def missing_evidence(case: Case) -> list[str]:
    """G3: required evidence items with no supporting record.

    Entries are ``"TID:sla_hours"`` or ``"TID:kb_article"``. An item is
    missing when the ticket is not among the case tickets, or the field is
    unknown (None) on that ticket.
    """
    missing = []
    by_id = {ticket.id: ticket for ticket in case.tickets}
    for entry in case.required_evidence:
        parts = entry.split(":")
        ticket_id, field_name = parts[0], parts[1]
        ticket = by_id.get(ticket_id)
        if ticket is None:
            missing.append(entry)
            continue
        if field_name == "sla_hours" and ticket.sla_hours is None:
            missing.append(entry)
        elif field_name == "kb_article" and ticket.kb_article_id is None:
            missing.append(entry)
    return missing


def scan_ticket_conflicts(case: Case) -> list[dict]:
    """G5: ticket-message asserts that contradict the queue.

    Only fields the ticket actually knows are compared; an assert about
    an unknown field is not a conflict. Returns one dict per contradiction.
    """
    conflicts = []
    by_id = {ticket.id: ticket for ticket in case.tickets}
    for message in case.messages:
        ticket = by_id.get(message.source)
        if ticket is None:
            continue
        for key, asserted in message.asserts.items():
            if key == "severity" and asserted != ticket.severity:
                conflicts.append(
                    {
                        "ticket": ticket.id,
                        "field": key,
                        "asserted": asserted,
                        "queue": ticket.severity,
                    }
                )
            elif key == "sla_hours" and ticket.sla_hours is not None:
                if asserted != ticket.sla_hours:
                    conflicts.append(
                        {
                            "ticket": ticket.id,
                            "field": key,
                            "asserted": asserted,
                            "queue": ticket.sla_hours,
                        }
                    )
            elif key == "kb_article" and ticket.kb_article_id is not None:
                if asserted != ticket.kb_article_id:
                    conflicts.append(
                        {
                            "ticket": ticket.id,
                            "field": key,
                            "asserted": asserted,
                            "queue": ticket.kb_article_id,
                        }
                    )
            elif key == "client_id" and asserted != ticket.client_id:
                conflicts.append(
                    {
                        "ticket": ticket.id,
                        "field": key,
                        "asserted": asserted,
                        "queue": ticket.client_id,
                    }
                )
    return conflicts


def cross_client_records(case: Case) -> list[str]:
    """G3: ticket ids in the case that belong to another client.

    A misrouted ticket is flagged, never acted on: per-client isolation
    means the agent may only work tickets of the case's own client.
    """
    return [ticket.id for ticket in case.tickets if ticket.client_id != case.client_id]


def policy_violations(case: Case) -> list[str]:
    """G5: policy violations that block any auto-resolution.

    A candidate is viable when every computable constraint passes
    (severity/SLA consistency, SLA not already breached, SLA within the
    case's target). If at least one candidate is viable there is no
    violation. Otherwise the violations from every candidate are returned,
    deduplicated. Unknown fields never count as violations — they are
    missing evidence (G3), not policy.
    """
    in_scope = [
        ticket
        for ticket in case.tickets
        if ticket.client_id == case.client_id
        and ticket.kind == case.kind
        and ticket.severity == case.severity
    ]
    if not in_scope:
        return []
    violations: set[str] = set()
    viable = False
    for ticket in in_scope:
        ticket_violations: list[str] = []
        if ticket.sla_hours is not None:
            if ticket.sla_hours > SEVERITY_MAX_SLA[ticket.severity]:
                ticket_violations.append(
                    f"severity_sla_mismatch: {ticket.id} is {ticket.severity} "
                    f"with a {ticket.sla_hours}h SLA "
                    f"(max {SEVERITY_MAX_SLA[ticket.severity]}h)"
                )
            if ticket.hours_open >= ticket.sla_hours:
                ticket_violations.append(
                    f"sla_breach: {ticket.id} open {ticket.hours_open}h "
                    f"against a {ticket.sla_hours}h SLA"
                )
            if ticket.sla_hours > case.sla_hours:
                ticket_violations.append(
                    f"sla_exceeds_target: {ticket.id} SLA {ticket.sla_hours}h "
                    f"exceeds the case target of {case.sla_hours}h"
                )
        if ticket_violations:
            violations.update(ticket_violations)
        else:
            viable = True
    if viable:
        return []
    return sorted(violations)
