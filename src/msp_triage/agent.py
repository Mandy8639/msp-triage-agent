"""The triage agent: two human gates around three allowlisted tools."""

from __future__ import annotations

from dataclasses import dataclass, field

from msp_triage import guardrail
from msp_triage.reasoner import LiveReasoner, StubReasoner
from msp_triage.tools import (
    ALLOWED_TOOLS,
    Draft,
    Resolution,
    kb_lookup,
    read_case,
    resolution_draft,
    ticket_search,
)


@dataclass(frozen=True)
class AgentResult:
    """Everything one agent run produces (or refuses to produce)."""

    case_id: str
    decision: str  # PROPOSE | HOLD | PAUSE | BLOCK | REFUSED
    resolution: Resolution | None = None
    draft: Draft | None = None
    flags: dict = field(default_factory=dict)
    published: bool = False
    applied: bool = False
    sent: bool = False
    provenance: list[str] = field(default_factory=list)
    spend_usd: float = 0.0
    gates_checked: list[str] = field(default_factory=list)
    refusal: str = ""


class TriageAgent:
    """Bounded MSP service-desk triage agent."""

    def __init__(self, mode: str = "stub", live_model: str | None = None) -> None:
        if mode not in ("stub", "live"):
            raise ValueError(f"unknown mode: {mode!r}")
        self.mode = mode
        self._live = LiveReasoner(model=live_model) if mode == "live" else None

    def plan(self) -> list[str]:
        """The tool plan, fixed and allowlisted. Gate 1 approves this plan."""
        return list(ALLOWED_TOOLS)

    def run(
        self,
        case_data: dict,
        *,
        approve_resolution: bool,
        approve_apply: bool,
    ) -> AgentResult:
        case = read_case(case_data)
        if not approve_resolution:
            return AgentResult(
                case_id=case.id,
                decision="REFUSED",
                refusal="resolution gate not approved: no tool ran",
                gates_checked=["resolution"],
            )
        matches = ticket_search(case)
        articles = kb_lookup(case)
        injected = guardrail.scan_injection(case.messages)
        fabricated = guardrail.scan_fabrication(case.claims)
        missing = guardrail.missing_evidence(case)
        conflicts = guardrail.scan_ticket_conflicts(case)
        violations = guardrail.policy_violations(case)
        misrouted = guardrail.cross_client_records(case)
        duplicates = [ticket.id for ticket in case.tickets if ticket.duplicate_of is not None]
        flags = {
            "injection": [message.text for message in injected],
            "fabrication": [claim.text for claim in fabricated],
            "missing_evidence": missing,
            "ticket_conflicts": conflicts,
            "policy_violations": violations,
            "misrouted": misrouted,
            "duplicates": duplicates,
            "kb_articles": [article.id for article in articles],
        }
        if self.mode == "live":
            assert self._live is not None
            decision, cost = self._live.decide(case, matches)
            spend = cost
        else:
            decision = StubReasoner().decide(
                case,
                matches,
                injection=bool(injected),
                fabrication=bool(fabricated),
                missing=bool(missing),
                conflicts=bool(conflicts),
                violations=bool(violations),
                remediation=bool(case.remediation_needed),
            )
            spend = 0.0
        resolution = None
        draft = None
        published = False
        applied = False
        sent = False
        if decision == "PROPOSE" and matches:
            # Gate 1 (G1): the resolution draft is issued only because a
            # human confirmed it. Gate 2 (G2): the change is applied and
            # the message sent only with the second explicit confirmation.
            best = matches[0].ticket
            resolution = resolution_draft(case, best.id)
            draft = resolution.client_message
            published = True
            applied = bool(approve_apply)
            sent = bool(approve_apply)
        return AgentResult(
            case_id=case.id,
            decision=decision,
            resolution=resolution,
            draft=draft,
            flags=flags,
            published=published,
            applied=applied,
            sent=sent,
            provenance=guardrail.cited_sources(case),
            spend_usd=spend,
            gates_checked=["resolution", "apply"],
        )
