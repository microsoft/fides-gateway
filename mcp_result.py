"""Helpers for interpreting an MCP ``tools/call`` response.

The MCP spec lets a server return its payload in two equivalent ways:

* As ``structured_content`` — a JSON object that matches the tool's
  declared ``outputSchema``. This is the recommended shape and the one
  FastMCP itself produces from a tool that returns a Python ``dict``.
* As ``content`` — a list of typed blocks (``TextContent``,
  ``ImageContent``, ...), with the structured payload encoded as a
  JSON-string ``TextContent`` block. Some real-world servers (notably
  the Microsoft Graph–backed WorkIQ MCP server) return *only* this
  shape: their results look like ::

      {
        "content": [
          {"type": "text", "text": "<escaped JSON of the payload>"},
          {"type": "text", "text": "CorrelationId: <guid>, TimeStamp: ..."}
        ],
        "isError": false
      }

  with ``structured_content`` unset.

:func:`extract_structured_content` papers over the two shapes for code
that needs the structured payload as a dict — primarily the upstream-
calling helpers used by :mod:`policy_engine` (the ``upstream.<Tool>``
Rego extensions in :func:`eval_policy`) and by :mod:`workiq_labeller`
(the ``call_upstream`` injected into async labelers).
"""

from __future__ import annotations

import json
from typing import Any, cast
from fastmcp.tools import ToolResult
from fastmcp.client.client import CallToolResult
from mcp.types import TextContent


def extract_structured_content(result: ToolResult | CallToolResult) -> dict[str, Any]:
    """Return the structured payload of an MCP ``tools/call`` *result*.

    Prefers ``result.structured_content`` when set. Otherwise falls back
    to ``result.content[0].text`` parsed as JSON — the shape used by
    upstreams that do not populate ``structured_content`` directly (e.g.
    WorkIQ, where ``content[0]`` carries the escaped-JSON payload and a
    trailing ``content[1]`` block carries ``CorrelationId: …``
    diagnostics).

    Raises ``ValueError`` if neither path yields a JSON object: no
    structured content and no content blocks, a non-text first block, a
    first block whose ``text`` is not valid JSON, or a first block whose
    parsed value is not a JSON object.
    """
    if result.structured_content is not None:
        return result.structured_content

    if not result.content:
        raise ValueError(
            "MCP tool result has no structured_content and no content blocks"
        )

    block = result.content[0]
    if not isinstance(block, TextContent):
        raise ValueError(
            "MCP tool result has no structured_content and content[0] is "
            f"{type(block).__name__} (not TextContent); cannot extract payload"
        )

    try:
        parsed: Any = json.loads(block.text)
    except json.JSONDecodeError as e:
        raise ValueError(
            "MCP tool result has no structured_content and content[0].text "
            f"is not valid JSON: {e}"
        ) from e

    if not isinstance(parsed, dict):
        raise ValueError(
            "MCP tool result has no structured_content and content[0].text "
            f"parsed to {type(parsed).__name__}, not a JSON object"
        )

    return cast(dict[str, Any], parsed)
