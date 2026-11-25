"""Tests for the MCP server (stdio JSON-RPC, no external dependencies)."""

from __future__ import annotations

import json

from msp_triage.mcp_server import handle
from tests.conftest import clean_case


def test_initialize_and_ping() -> None:
    response = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert response["result"]["serverInfo"]["name"] == "msp-triage-agent"
    assert handle({"jsonrpc": "2.0", "id": 2, "method": "ping"})["result"] == {}


def test_notifications_return_none() -> None:
    assert handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_tools_list_exposes_exactly_three_tools() -> None:
    response = handle({"jsonrpc": "2.0", "id": 3, "method": "tools/list"})
    names = [tool["name"] for tool in response["result"]["tools"]]
    assert names == ["ticket_search", "kb_lookup", "resolution_draft"]


def test_tools_call_ticket_search() -> None:
    response = handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "ticket_search", "arguments": {"case": clean_case()}},
        }
    )
    matches = json.loads(response["result"]["content"][0]["text"])
    assert [m["ticket"]["id"] for m in matches] == ["T001", "T031"]


def test_tools_call_kb_lookup() -> None:
    response = handle(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "kb_lookup", "arguments": {"case": clean_case()}},
        }
    )
    articles = json.loads(response["result"]["content"][0]["text"])
    ids = [article["id"] for article in articles]
    assert "KB001" in ids
    assert "KB011" in ids  # Acme's own runbook
    assert "KB012" not in ids  # Helix's runbook is not visible to Acme


def test_tools_call_resolution_draft() -> None:
    response = handle(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {
                "name": "resolution_draft",
                "arguments": {"case": clean_case(), "ticket_id": "T001"},
            },
        }
    )
    resolution = json.loads(response["result"]["content"][0]["text"])
    assert resolution["status"] == "draft"
    assert resolution["ticket_id"] == "T001"
    assert resolution["applied"] is False
    assert resolution["client_message"]["sent"] is False


def test_tools_call_unknown_tool_and_method_return_errors() -> None:
    unknown_tool = handle(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "apply_resolution", "arguments": {}},
        }
    )
    assert unknown_tool["error"]["code"] == -32602
    unknown_method = handle({"jsonrpc": "2.0", "id": 8, "method": "resources/list"})
    assert unknown_method["error"]["code"] == -32601


def test_tools_call_bad_arguments_return_error() -> None:
    response = handle(
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {
                "name": "resolution_draft",
                "arguments": {"case": clean_case(), "ticket_id": "T013"},
            },
        }
    )
    assert response["error"]["code"] == -32602
