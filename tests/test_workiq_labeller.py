from __future__ import annotations

from typing import Any

import pytest
from fastmcp.server.middleware import MiddlewareContext
from fastmcp.tools import ToolResult
from mcp.types import CallToolRequestParams, TextContent

from policy_engine import IFC_LABELS_META_PREFIX
from workiq_labeller import WorkIQLabellingMiddleware


def _ctx(
    name: str, arguments: dict[str, Any] | None = None
) -> MiddlewareContext[CallToolRequestParams]:
    message = CallToolRequestParams.model_construct(
        name=name, arguments=arguments or {}
    )
    return MiddlewareContext(message=message, method="tools/call")


@pytest.mark.anyio
async def test_workiq_labeller_stamps_ifc_meta_key() -> None:
    middleware = WorkIQLabellingMiddleware()
    context = _ctx("NoSpecificLabeler")

    async def call_next(_context: object) -> ToolResult:
        return ToolResult.model_construct(content=[], meta={}, structured_content={})

    result = await middleware.on_call_tool(context, call_next)

    assert result.meta is not None
    assert IFC_LABELS_META_PREFIX in result.meta
    assert result.meta[IFC_LABELS_META_PREFIX] == {
        "$": {
            "integrity": "trusted",
            "confidentiality": ["public"],
        },
    }


def _undecodable_result() -> ToolResult:
    """A result with neither ``structured_content`` nor decodable text in
    ``content[0]`` — exactly the shape that should trip
    :func:`mcp_result.extract_structured_content` and, when paired with a
    tool that has a specific labeler, should make
    :class:`WorkIQLabellingMiddleware` *refuse* to label rather than
    silently fall back to the baseline (which could under-label
    sensitive data we just couldn't decode)."""
    return ToolResult.model_construct(
        content=[TextContent(type="text", text="not actually JSON {")],
        structured_content=None,
        meta={},
    )


@pytest.mark.anyio
async def test_workiq_labeller_raises_when_specific_labeler_cannot_decode() -> None:
    """If a tool has a tool-specific labeler but the upstream's response
    can't be decoded into a structured payload, the middleware re-raises
    a ``ValueError`` naming the tool — refusing to label rather than
    risking a mislabel via the baseline fallback."""
    middleware = WorkIQLabellingMiddleware()
    # ``ListTeams`` has a labeler in WorkIQLabeling.
    context = _ctx("ListTeams")

    async def call_next(_context: object) -> ToolResult:
        return _undecodable_result()

    with pytest.raises(ValueError, match=r"tool 'ListTeams'"):
        await middleware.on_call_tool(context, call_next)


@pytest.mark.anyio
async def test_workiq_labeller_does_not_raise_when_no_specific_labeler() -> None:
    """Tools with no specific labeler don't read ``tool_output`` at all;
    a broken upstream response must still produce the baseline label so
    every result carries an ``ifc`` block."""
    middleware = WorkIQLabellingMiddleware()
    context = _ctx("NoSpecificLabeler")

    async def call_next(_context: object) -> ToolResult:
        return _undecodable_result()

    # Must NOT raise — no labeler means no risk of mislabeling.
    result = await middleware.on_call_tool(context, call_next)
    assert result.meta is not None
    assert result.meta[IFC_LABELS_META_PREFIX] == {
        "$": {
            "integrity": "trusted",
            "confidentiality": ["public"],
        },
    }
