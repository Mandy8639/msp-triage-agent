# msp-triage-agent

A bounded MSP service-desk triage agent — the kind of work a Forward
Deployment AI Engineer does at Lyra Technology Group: take a one-sentence
ticket intake ("VPN gateway down for 12 users at Acme Manufacturing") to a
confirmed, on-policy resolution draft, with a deterministic guardrail and
two human gates around every run. It mirrors Vega, Lyra's proprietary AI
Operating System for MSP service desks, and the Scribcor Central case
study (AI email triage saving ~45 minutes per person per day) — on
synthetic data, with the eval to prove it.

## What it does

Given a triage case (a parsed intake, candidate tickets drawn from a
synthetic ConnectWise-style queue, messages from the client or
technicians, claims about the case), the agent:

1. **Searches tickets** — filters the queue to tickets that can be
   triaged for this case: same client, kind, and severity, SLA and KB
   article known, SLA consistent with the severity and within the case's
   target, and not already breached (tool 1 of 3 allowlisted tools).
2. **Looks up the KB** — knowledge-base articles visible to the case's
   client for this kind. Shared articles are visible to every client; a
   client-scoped article is visible only to its own client (tool 2).
3. **Decides** — PROPOSE, HOLD, PAUSE, or BLOCK.
4. **Drafts a resolution** — for the most urgent confirmed match, with
   steps sourced from the ticket and the KB article. It applies nothing
   and changes no client system (tool 3). The client message travels
   inside the draft, and it sends nothing.

Nothing else may touch a case. There are exactly three tools. Every fact
the agent states comes only from the ticket queue or the KB; a ticket it
cannot verify, it does not resolve. A ticket from another client is
flagged as misrouted, never acted on.

## The guardrail (G1–G5)

| Rule | Behaviour |
| --- | --- |
| G1 | No resolution applied or sent without gate 1 — a human must confirm the resolution draft first. |
| G2 | No change to a client system or external message without gate 2 — a second explicit confirmation. |
| G3 | Never state a ticket or KB fact not in the queue or KB. Missing evidence means abstain: the agent holds instead of guessing. Unsourced claims are dropped. PII is redacted before any draft leaves the queue. A ticket from another client is never acted on (per-client isolation). |
| G4 | Instructions injected into ticket messages are blocked; nothing is published. Ticket text is data, never instructions. |
| G5 | Policy violations pause the run for human review: severity vs. SLA mismatch, SLA already breached, SLA exceeding the case target — and any ticket message that contradicts the queue. |

Two human gates bound every run: **resolution approval** (before any
resolution is issued) and **apply approval** (before any change is
applied or any message is sent).

## Verified numbers (frozen stub eval, 48 cases)

| Metric | Result |
| --- | --- |
| Agreement with analyst calls | 48/48 (100%) |
| False auto-resolves | 0 |
| False holds | 0 |
| Abstention (insufficient evidence) | 6/6 |
| Fabrication blocked | 6/6 |
| Injection blocked | 6/6 |
| Pause (policy violation) | 4/4 |
| Gates checked | 48/48 |
| Spend | $0.00 (stub mode) |
| Tests | 61 passed |

The golden set is frozen and hash-locked (`eval/golden.sha256`); the eval
refuses to run on a tampered set. Reproduce it with:

```bash
python eval/run_eval.py
```

## Honest limits

- The eval is **synthetic**: it measures the deterministic stub against 48
  frozen cases built for this repo, not real-world triage performance.
  Each case carries exactly one signal, so the numbers show the guardrail
  and decision rule behave as designed — not that the agent understands
  real service-desk work.
- The stub reasoner is rule-based. It cannot call a real ticketing system,
  and it should never be the only reviewer of a resolution that touches a
  real client's systems.
- No Lyra affiliation is claimed, and no ConnectWise/HaloPSA production
  experience is claimed: the ticket queue is ConnectWise-*style* synthetic
  data, and the corpus names no real client, ticket, or vendor.
- No AWS/Bedrock is claimed: the agent runs locally with no cloud
  dependency.
- Live mode exists but is deliberately narrow (see below).

## Usage

```python
from msp_triage.agent import TriageAgent

agent = TriageAgent(mode="stub")
result = agent.run(case_dict, approve_resolution=True, approve_apply=True)
print(result.decision)  # PROPOSE | HOLD | PAUSE | BLOCK | REFUSED
print(result.resolution)  # drafted resolution (status: draft)
print(result.applied, result.sent)  # change applied, message sent
```

## MCP server

The three tools are exposed over MCP (stdio, no external dependencies):

```bash
python -m msp_triage.mcp_server
```

## Live mode (optional)

Set `ANTHROPIC_API_KEY` and install the live extra (`pip install '.[live]'`).
Live mode is capped at **$1.00/day** and only accepts models in the
priced-model table (`claude-haiku-4-5`, $1.00/$5.00 per MTok input/output,
per Anthropic's published pricing). Unknown models are refused; without an
API key it refuses outright. The eval never uses live mode.

## Development

```bash
python -m venv .venv && .venv/bin/pip install -e . ruff pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/python -m pytest -q
.venv/bin/python eval/run_eval.py
```

## Why this exists

Built for a Lyra Technology Group Forward Deployment AI Engineer
application. Lyra is deploying Vega, its proprietary AI Operating System,
across 130+ managed IT service providers: agentic workflows for ticket
triage, enrichment, root-cause analysis and proactive support, integrations
with ticketing systems behind one shared layer, and evals and governance
as named requirements. This agent is a small, honest version of that same
shape: a ticket in, a resolution draft out, nothing irreversible without
a human — with per-client isolation and PII redaction built in, because
one MSP's clients must never see each other's tickets.
