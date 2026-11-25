"""The three allowlisted tools. Nothing else may touch a case.

1. ticket_search — filter the queue to tickets that can be triaged for the case.
2. kb_lookup — knowledge-base articles visible to the case's client.
3. resolution_draft — draft a resolution. It never applies a change and
   never sends a message; the client message it carries is a draft.

The client message itself is built by ``client_message`` (a helper, not a
tool) and travels inside the resolution draft, so the draft is the only
place a message to a client can originate.
"""

from __future__ import annotations

from dataclasses import dataclass

from msp_triage import guardrail
from msp_triage.inventory import KB_ARTICLES, KB_BY_ID
from msp_triage.packet import Case, KBArticle, Ticket, case_from_dict, kb_from_dict

ALLOWED_TOOLS = (
    "ticket_search",
    "kb_lookup",
    "resolution_draft",
)

MESSAGE_PURPOSES = (
    "request_info",
    "confirm_resolution",
    "escalation_notice",
)

SEVERITY_RANK = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}


@dataclass(frozen=True)
class TicketMatch:
    """One ticket that can be triaged for the case, with its KB article."""

    ticket: Ticket
    kb_article_id: str
    source: str


@dataclass(frozen=True)
class Draft:
    """A drafted message to a client. ``sent`` is always False: it sends nothing."""

    to_client: str
    to_client_id: str
    purpose: str
    subject: str
    body: str
    sent: bool = False


@dataclass(frozen=True)
class Resolution:
    """A drafted resolution. Status is always 'draft': it applies nothing.

    ``applied`` and ``sent`` are always False on the draft itself — only a
    human confirmation (gate 2) may flip them on the agent result.
    """

    ticket_id: str
    client_id: str
    summary: str
    steps: list[str]
    kb_article_id: str
    kb_title: str
    client_message: Draft
    status: str = "draft"
    applied: bool = False
    sent: bool = False


def ticket_search(case: Case) -> list[TicketMatch]:
    """Tool 1: tickets that can be triaged for the case, most urgent first.

    A ticket matches only when every fact is known and passes: it belongs
    to the case's client (per-client isolation), kind and severity match,
    SLA and KB article are known, the SLA is consistent with the severity
    and within the case's target, and the SLA is not already breached.
    Unknown facts exclude the ticket (G3) rather than being guessed.
    """
    matches = []
    for ticket in case.tickets:
        if ticket.client_id != case.client_id:
            continue
        if ticket.kind != case.kind or ticket.severity != case.severity:
            continue
        if ticket.duplicate_of is not None:
            continue
        if ticket.sla_hours is None or ticket.kb_article_id is None:
            continue
        if ticket.sla_hours > guardrail.SEVERITY_MAX_SLA[ticket.severity]:
            continue
        if ticket.sla_hours > case.sla_hours:
            continue
        if ticket.hours_open >= ticket.sla_hours:
            continue
        matches.append(
            TicketMatch(ticket=ticket, kb_article_id=ticket.kb_article_id, source=ticket.id)
        )
    matches.sort(
        key=lambda match: (
            SEVERITY_RANK[match.ticket.severity],
            match.ticket.sla_hours or 0,
            match.ticket.id,
        )
    )
    return matches


def kb_lookup(case: Case) -> list[KBArticle]:
    """Tool 2: KB articles visible to the case's client for this kind.

    Shared articles are visible to every client; a client-scoped article
    is visible only to its own client. Articles for other clients are
    never returned (per-client isolation, G3).
    """
    articles = []
    for data in KB_ARTICLES:
        if data["resolves_kind"] != case.kind:
            continue
        if data["client_id"] not in ("shared", case.client_id):
            continue
        articles.append(kb_from_dict(data))
    articles.sort(key=lambda article: article.id)
    return articles


def client_message(case: Case, ticket: Ticket, article: KBArticle, purpose: str) -> Draft:
    """Build a message draft to the client. It is never sent.

    The body cites ticket and KB facts only — never a fact the queue or
    KB does not know — and any PII quoted from the ticket is redacted
    before the draft leaves the queue (G3).
    """
    if purpose not in MESSAGE_PURPOSES:
        raise ValueError(f"unknown message purpose: {purpose!r}")
    summary = guardrail.redact_pii(ticket.summary)
    if purpose == "confirm_resolution":
        subject = f"Resolution proposed — {ticket.title} ({ticket.id})"
        body = (
            f"Hello {case.client_name}, we have a proposed resolution for "
            f"{ticket.id} ({ticket.title}), following {article.id} "
            f"({article.title}). Reported symptom: {summary} "
            f"Please confirm before we apply it — nothing changes until you do. "
            f"SLA target: {case.sla_hours}h, severity {ticket.severity}."
        )
    elif purpose == "request_info":
        subject = f"More information needed — {ticket.title} ({ticket.id})"
        body = (
            f"Hello {case.client_name}, we need one more detail to triage "
            f"{ticket.id} ({ticket.title}). Reported symptom: {summary} "
            f"Could you confirm what changed just before this started?"
        )
    else:  # escalation_notice
        subject = f"Escalation — {ticket.title} ({ticket.id})"
        body = (
            f"Hello {case.client_name}, {ticket.id} ({ticket.title}) has been "
            f"escalated to a human engineer for review. Reported symptom: "
            f"{summary} We will update you once they have looked at it."
        )
    return Draft(
        to_client=case.client_name,
        to_client_id=case.client_id,
        purpose=purpose,
        subject=subject,
        body=body,
    )


def resolution_draft(case: Case, ticket_id: str) -> Resolution:
    """Tool 3: draft a resolution for one matching ticket.

    The resolution is a draft: it applies nothing, changes no client
    system, and sends nothing. Only a ticket returned by ticket_search
    may be drafted, and only a KB article visible to the case's client
    may be cited. The client message travels inside the draft.
    """
    matches = {match.ticket.id: match for match in ticket_search(case)}
    if ticket_id not in matches:
        raise ValueError(f"ticket {ticket_id!r} is not a confirmed match for this case")
    ticket = matches[ticket_id].ticket
    article_data = KB_BY_ID.get(ticket.kb_article_id or "")
    if article_data is None:
        raise ValueError(f"ticket {ticket_id!r} has no KB article on file")
    if article_data["client_id"] not in ("shared", case.client_id):
        raise ValueError(
            f"KB article {article_data['id']!r} is not visible to client {case.client_id!r}"
        )
    article = kb_from_dict(article_data)
    steps = [
        f"Verify the reported symptom against ticket {ticket.id}: "
        f"{guardrail.redact_pii(ticket.title)}.",
        f"Apply {article.id} ({article.title}): {article.summary}",
        f"Confirm the fix with the client before closing "
        f"(SLA target {case.sla_hours}h, severity {ticket.severity}).",
    ]
    if ticket.attachments:
        steps.append(f"Reviewed {len(ticket.attachments)} attachment(s) on the ticket.")
    if ticket.requires:
        steps.append(f"Pre-resolution step (human): {ticket.requires}")
    steps.append("Human confirmation required before any change or message is sent.")
    return Resolution(
        ticket_id=ticket.id,
        client_id=case.client_id,
        summary=guardrail.redact_pii(ticket.summary),
        steps=steps,
        kb_article_id=article.id,
        kb_title=article.title,
        client_message=client_message(case, ticket, article, "confirm_resolution"),
    )


def read_case(data: dict) -> Case:
    """Load and validate a case. Raises ValueError if malformed."""
    return case_from_dict(data)
