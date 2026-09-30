"""End-to-end exercise of the Work IQ migration.

Wires the real policy files and the real labeling middleware against a
stub Work IQ upstream (generic ``fetch`` / ``create_entity`` tools addressed
by Microsoft Graph API paths) and walks the full loop a client goes through:

1. read Teams messages via ``fetch``, which makes the labeler stamp the result with
   the roster of the conversation the messages came from;
2. propose a ``create_entity`` post carrying those labels, after which the policy
   re-reads the target roster from the upstream and decides.

No network and no auth: the upstream is an in-process FastMCP server.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client, FastMCP
from fastmcp.client.transports import FastMCPTransport
from fastmcp.server.middleware import MiddlewareContext
from mcp.types import CallToolRequestParams

from policy_engine import IFC_LABELS_META_PREFIX, eval_policy
from workiq_labeller import WorkIQLabellingMiddleware

POLICIES = Path(__file__).parents[1] / "policies" / "workiq"
CREATE_ENTITY_POLICY = (POLICIES / "teams" / "messages.rego").read_text(
    encoding="utf-8"
)

ENGINEERING_MEMBERS = [
    {
        "id": "m1",
        "displayName": "Alice",
        "userId": "user-alice",
        "email": "alice@example.com",
        "roles": ["owner"],
    },
    {
        "id": "m2",
        "displayName": "Bob",
        "userId": "user-bob",
        "email": "bob@example.com",
        "roles": ["member"],
    },
]

MARKETING_MEMBERS = ENGINEERING_MEMBERS + [
    {
        "id": "m3",
        "displayName": "Carol",
        "userId": "user-carol",
        "email": "carol@example.com",
        "roles": ["member"],
    },
]


def _workiq_stub() -> FastMCP:
    """A minimal stand-in for the Work IQ MCP server."""
    server = FastMCP("workiq-stub", version="1.0.0")

    @server.tool
    def fetch(entityUrls: list[str]) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        for url in entityUrls:
            path = url.split("?")[0]
            if path == "/teams/team-eng/channels/channel-eng/members":
                data: dict[str, Any] = {"value": ENGINEERING_MEMBERS}
            elif path == "/teams/team-mkt/channels/channel-mkt/members":
                data = {"value": MARKETING_MEMBERS}
            elif path.endswith("/messages"):
                data = {"value": [{"id": "msg-1", "body": {"content": "roadmap"}}]}
            else:
                data = {"value": []}
            results.append({"statusCode": 200, "data": data})
        return {"results": results}

    @server.tool
    def create_entity(parentUrl: str, jsonBody: dict[str, Any]) -> dict[str, Any]:
        return {"results": [{"statusCode": 201, "data": {"id": "msg-2"}}]}

    return server


async def _labelled_fetch(url: str) -> dict[str, Any]:
    """Call ``fetch`` through the labeling middleware and return the IFC
    labels the gateway stamped on the result."""
    upstream = _workiq_stub()
    middleware = WorkIQLabellingMiddleware(
        upstream_client_factory=lambda: Client(FastMCPTransport(upstream)),
        labellers={
            "fetch": {
                "pathArg": "entityUrls",
                "rules": [
                    {
                        "path": "/teams/*/channels/*/messages/**",
                        "labeller": "teamsMessages",
                    }
                ],
            }
        },
    )
    context: MiddlewareContext[CallToolRequestParams] = MiddlewareContext(
        message=CallToolRequestParams.model_construct(
            name="fetch", arguments={"entityUrls": [url]}
        ),
        method="tools/call",
    )

    async def call_next(_context: object):
        async with Client(FastMCPTransport(upstream)) as client:
            return await client.call_tool("fetch", {"entityUrls": [url]})

    result = await middleware.on_call_tool(context, call_next)
    assert result.meta is not None
    return result.meta[IFC_LABELS_META_PREFIX]


def _call_labels(fetch_labels: dict[str, Any]) -> dict[str, Any]:
    """Labels for an untrusted proposed call whose body carries the
    provenance of whatever was read earlier."""
    return {
        "$['name']": {"integrity": "untrusted", "confidentiality": ["public"]},
        "$['arguments']['jsonBody']": fetch_labels["$"],
    }


async def _decide(
    call_name: str, arguments: dict[str, Any], labels: dict[str, Any], policy: str
) -> dict[str, str]:
    upstream = _workiq_stub()
    decision = await eval_policy(
        {
            "name": call_name,
            "arguments": arguments,
            "_meta": {IFC_LABELS_META_PREFIX: labels},
        },
        policy,
        upstream_client=Client(FastMCPTransport(upstream)),
        server_info={"name": "workiq-stub", "version": "1.0.0"},
    )
    return decision["decision"]


@pytest.mark.anyio
async def test_fetch_is_labelled_with_the_channel_roster() -> None:
    labels = await _labelled_fetch("/teams/team-eng/channels/channel-eng/messages")

    audience_label = {
        "integrity": "untrusted",
        "confidentiality": [
            "alice@example.com",
            "bob@example.com",
            "user-alice",
            "user-bob",
        ],
    }
    assert labels["$"] == audience_label
    assert labels["$['structuredContent']['results'][0]['data']"] == audience_label
    assert labels["$['structuredContent']['results'][0]['data']['value'][0]['id']"] == {
        "integrity": "trusted",
        "confidentiality": [
            "alice@example.com",
            "bob@example.com",
            "user-alice",
            "user-bob",
        ],
    }


@pytest.mark.anyio
async def test_content_can_be_posted_back_to_its_own_channel() -> None:
    labels = await _labelled_fetch("/teams/team-eng/channels/channel-eng/messages")

    decision = await _decide(
        "create_entity",
        {
            "parentUrl": "/teams/team-eng/channels/channel-eng/messages",
            "jsonBody": {"body": {"content": "re: roadmap"}},
        },
        _call_labels(labels),
        CREATE_ENTITY_POLICY,
    )

    assert decision["decision"] == "allow"


@pytest.mark.anyio
async def test_posting_to_a_wider_channel_requires_approval() -> None:
    labels = await _labelled_fetch("/teams/team-eng/channels/channel-eng/messages")

    decision = await _decide(
        "create_entity",
        {
            "parentUrl": "/teams/team-mkt/channels/channel-mkt/messages",
            "jsonBody": {"body": {"content": "re: roadmap"}},
        },
        _call_labels(labels),
        CREATE_ENTITY_POLICY,
    )

    assert decision["decision"] == "ask"
    assert "carol@example.com" in decision["message"]
