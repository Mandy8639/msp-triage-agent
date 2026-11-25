"""Minimal MCP server (stdio JSON-RPC 2.0), no external dependencies.

Exposes the three allowlisted tools over the Model Context Protocol:
tools/list and tools/call. Run: python -m msp_triage.mcp_server
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict

from msp_triage.tools import (
    ALLOWED_TOOLS,
    kb_lookup,
    read_case,
    resolution_draft,
    ticket_search,
)

TOOLS = {
    "ticket_search": {
        "description": "Filter the ticket queue to tickets that can be triaged for a case.",
        "inputSchema": {
            "type": "object",
            "properties": {"case": {"type": "object"}},
            "required": ["case"],
        },
    },
    "kb_lookup": {
        "description": "Knowledge-base articles visible to the case's client for this kind.",
        "inputSchema": {
            "type": "object",
            "properties": {"case": {"type": "object"}},
            "required": ["case"],
        },
    },
    "resolution_draft": {
        "description": "Draft a resolution for one matching ticket. Never applies a change "
        "or sends a message; the client message travels inside the draft.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "case": {"type": "object"},
                "ticket_id": {"type": "string"},
            },
            "required": ["case", "ticket_id"],
        },
    },
}


def _tool_result(payload: object) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, indent=2)}]}


def handle(request: dict) -> dict | None:
    """Handle one JSON-RPC request. Returns None for notifications."""
    method = request.get("method", "")
    request_id = request.get("id")
    params = request.get("params", {}) or {}

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "msp-triage-agent", "version": "0.1.0"},
                "capabilities": {"tools": {}},
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if method.startswith("notifications/"):
        return None
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {"name": name, **spec} for name, spec in TOOLS.items() if name in ALLOWED_TOOLS
                ]
            },
        }
    if method == "tools/call":
        name = params.get("name", "")
        arguments = params.get("arguments", {}) or {}
        try:
            if name == "ticket_search":
                case = read_case(arguments["case"])
                matches = ticket_search(case)
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": _tool_result([asdict(match) for match in matches]),
                }
            if name == "kb_lookup":
                case = read_case(arguments["case"])
                articles = kb_lookup(case)
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": _tool_result([asdict(article) for article in articles]),
                }
            if name == "resolution_draft":
                case = read_case(arguments["case"])
                resolution = resolution_draft(case, arguments["ticket_id"])
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": _tool_result(asdict(resolution)),
                }
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": f"unknown tool: {name}"},
            }
        except (KeyError, ValueError) as exc:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": str(exc)},
            }
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"unknown method: {method}"},
    }


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = handle(request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
