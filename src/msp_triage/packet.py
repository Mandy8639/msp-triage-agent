"""Ticket case: the single input to the agent.

A case is a synthetic service-desk intake: a one-sentence request parsed
into client, kind, severity and SLA target, a shortlist of candidate
tickets drawn from the queue, messages from the client or technicians, and
claims about the case. Every message and claim carries a provenance source;
a claim without a source is unsourced by construction and the guardrail
treats it as fabrication. Every ticket carries the client it belongs to:
a ticket from another client is a misrouted record, and the agent may
never act on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Ticket:
    """One ticket in the queue, with facts copied from the corpus.

    ``sla_hours`` and ``kb_article_id`` are None when that fact is unknown
    (missing evidence, G3). ``requires`` names a human step that must be
    completed before any auto-resolution (remediation). ``duplicate_of``
    names the ticket this one duplicates, if any. ``attachments`` are
    filenames only — no content is ever read.
    """

    id: str
    msp: str
    client_id: str
    client_name: str
    title: str
    kind: str
    severity: str
    sla_hours: int | None
    hours_open: int
    kb_article_id: str | None
    summary: str
    requires: str | None = None
    duplicate_of: str | None = None
    attachments: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class KBArticle:
    """One knowledge-base article. ``client_id`` is "shared" or one client.

    An article scoped to one client is visible only to that client
    (per-client isolation, G3). The agent may never cite an article
    another client cannot see.
    """

    id: str
    title: str
    client_id: str
    resolves_kind: str
    keywords: list[str]
    summary: str


@dataclass(frozen=True)
class TicketMessage:
    """One message from the client or a technician. ``source`` is the ticket id.

    ``asserts`` holds machine-readable facts the message claims (e.g. a
    severity or an SLA). The guardrail compares them against the ticket
    record: an assert that contradicts the queue is a ticket conflict (G5).
    """

    text: str
    source: str
    asserts: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Claim:
    """One claim about the case. ``source`` may be None (unsourced)."""

    text: str
    source: str | None


@dataclass(frozen=True)
class Case:
    """A triage case. All fields are required; see tools.read_case."""

    id: str
    category: str
    client_id: str
    client_name: str
    request_text: str
    kind: str
    severity: str
    sla_hours: int
    tickets: list[Ticket] = field(default_factory=list)
    messages: list[TicketMessage] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    required_evidence: list[str] = field(default_factory=list)
    remediation_needed: list[str] = field(default_factory=list)


def ticket_from_dict(data: dict) -> Ticket:
    return Ticket(
        id=data["id"],
        msp=data["msp"],
        client_id=data["client_id"],
        client_name=data["client_name"],
        title=data["title"],
        kind=data["kind"],
        severity=data["severity"],
        sla_hours=data.get("sla_hours"),
        hours_open=data["hours_open"],
        kb_article_id=data.get("kb_article_id"),
        summary=data["summary"],
        requires=data.get("requires"),
        duplicate_of=data.get("duplicate_of"),
        attachments=list(data.get("attachments", [])),
    )


def kb_from_dict(data: dict) -> KBArticle:
    return KBArticle(
        id=data["id"],
        title=data["title"],
        client_id=data["client_id"],
        resolves_kind=data["resolves_kind"],
        keywords=list(data["keywords"]),
        summary=data["summary"],
    )


def case_from_dict(data: dict) -> Case:
    """Build a Case from a plain dict, validating required fields."""
    required = [
        "id",
        "category",
        "client_id",
        "client_name",
        "request_text",
        "kind",
        "severity",
        "sla_hours",
    ]
    for key in required:
        if key not in data or data[key] in (None, ""):
            raise ValueError(f"case is missing required field: {key}")
    tickets = [ticket_from_dict(t) for t in data.get("tickets", [])]
    messages = [
        TicketMessage(text=m["text"], source=m["source"], asserts=dict(m.get("asserts", {})))
        for m in data.get("messages", [])
    ]
    claims = [Claim(text=c["text"], source=c.get("source")) for c in data.get("claims", [])]
    return Case(
        id=data["id"],
        category=data["category"],
        client_id=data["client_id"],
        client_name=data["client_name"],
        request_text=data["request_text"],
        kind=data["kind"],
        severity=data["severity"],
        sla_hours=data["sla_hours"],
        tickets=tickets,
        messages=messages,
        claims=claims,
        required_evidence=list(data.get("required_evidence", [])),
        remediation_needed=list(data.get("remediation_needed", [])),
    )


def ticket_to_dict(ticket: Ticket) -> dict:
    return {
        "id": ticket.id,
        "msp": ticket.msp,
        "client_id": ticket.client_id,
        "client_name": ticket.client_name,
        "title": ticket.title,
        "kind": ticket.kind,
        "severity": ticket.severity,
        "sla_hours": ticket.sla_hours,
        "hours_open": ticket.hours_open,
        "kb_article_id": ticket.kb_article_id,
        "summary": ticket.summary,
        "requires": ticket.requires,
        "duplicate_of": ticket.duplicate_of,
        "attachments": list(ticket.attachments),
    }


def case_to_dict(case: Case) -> dict:
    """Serialise a Case back to a plain dict."""
    return {
        "id": case.id,
        "category": case.category,
        "client_id": case.client_id,
        "client_name": case.client_name,
        "request_text": case.request_text,
        "kind": case.kind,
        "severity": case.severity,
        "sla_hours": case.sla_hours,
        "tickets": [ticket_to_dict(t) for t in case.tickets],
        "messages": [
            {"text": m.text, "source": m.source, "asserts": dict(m.asserts)} for m in case.messages
        ],
        "claims": [{"text": c.text, "source": c.source} for c in case.claims],
        "required_evidence": list(case.required_evidence),
        "remediation_needed": list(case.remediation_needed),
    }
