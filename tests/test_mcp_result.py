"""Tests for :func:`mcp_result.extract_structured_content`.

The helper unifies the two MCP ``tools/call`` response shapes: the
recommended ``structured_content`` dict, and the WorkIQ-style
``content[0].text`` escaped-JSON fallback. These tests exercise both
paths via lightweight stand-ins (no FastMCP plumbing required) and
cover the failure modes raised when neither shape yields a JSON object.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastmcp.tools import ToolResult
from mcp.types import ImageContent, TextContent

from mcp_result import extract_structured_content


def _text_block(text: str) -> TextContent:
    return TextContent(type="text", text=text)


def _result(
    *,
    structured_content: Any = None,
    content: list[Any] | None = None,
) -> ToolResult:
    """Build a :class:`ToolResult` via ``model_construct`` so we can
    populate exactly the fields the helper reads — including the
    "neither set" case that the validating ``__init__`` rejects."""
    return ToolResult.model_construct(
        content=content if content is not None else [],
        structured_content=structured_content,
    )


def test_returns_structured_content_when_set():
    """When the upstream populated ``structured_content`` the helper
    returns it directly and ignores ``content``."""
    payload = {"teams": [{"id": "1"}]}
    result = _result(
        structured_content=payload,
        content=[_text_block("ignored")],
    )
    assert extract_structured_content(result) is payload


def test_falls_back_to_content_zero_text_when_unstructured():
    """No ``structured_content`` → parse ``content[0].text`` as JSON."""
    payload = {"teams": [{"id": "1", "name": "Engineering"}]}
    result = _result(content=[_text_block(json.dumps(payload))])
    assert extract_structured_content(result) == payload


def test_ignores_trailing_diagnostic_blocks():
    """WorkIQ-style: ``content[0]`` is the JSON, ``content[1]`` carries
    ``CorrelationId: …, TimeStamp: …`` and is silently ignored."""
    payload = {"members": [{"userId": "u1"}]}
    result = _result(
        content=[
            _text_block(json.dumps(payload)),
            _text_block(
                "CorrelationId: 1f8552f5-2933-412a-b747-21d858eb88a0, "
                "TimeStamp: 2026-05-22_10:44:02"
            ),
        ]
    )
    assert extract_structured_content(result) == payload


def test_ignores_arbitrary_trailing_blocks():
    """The helper does not interpret ``content[1:]`` at all — any extra
    block content is treated as opaque diagnostic."""
    payload = {"k": "v"}
    result = _result(
        content=[
            _text_block(json.dumps(payload)),
            _text_block("totally unrelated text"),
            _text_block('{"misleading": "but ignored"}'),
        ]
    )
    assert extract_structured_content(result) == payload


def test_raises_when_no_structured_and_no_content():
    result = _result()
    with pytest.raises(ValueError, match="no structured_content and no content"):
        extract_structured_content(result)


def test_raises_when_content_zero_has_no_text_field():
    """If ``content[0]`` is not a text block (e.g. an image block) we
    cannot extract a structured payload from it."""
    not_a_text_block = ImageContent(type="image", data="b64...", mimeType="image/png")
    result = _result(content=[not_a_text_block])
    with pytest.raises(
        ValueError,
        match=r"content\[0\] is ImageContent \(not TextContent\)",
    ):
        extract_structured_content(result)


def test_raises_when_content_zero_text_is_invalid_json():
    result = _result(content=[_text_block("not actually JSON {")])
    with pytest.raises(ValueError, match="not valid JSON"):
        extract_structured_content(result)


def test_raises_when_content_zero_parses_to_non_object():
    """The MCP ``outputSchema`` contract is a JSON object, not a bare
    array or scalar; reject anything that isn't a dict."""
    result = _result(content=[_text_block(json.dumps([1, 2, 3]))])
    with pytest.raises(ValueError, match="parsed to list, not a JSON object"):
        extract_structured_content(result)

    result = _result(content=[_text_block(json.dumps("string"))])
    with pytest.raises(ValueError, match="parsed to str, not a JSON object"):
        extract_structured_content(result)


def test_structured_content_takes_precedence_over_invalid_content():
    """If ``structured_content`` is populated, the helper short-circuits
    and never inspects ``content`` — even garbage in ``content[0]`` is
    fine."""
    payload = {"ok": True}
    result = _result(
        structured_content=payload,
        content=[_text_block("definitely not JSON {{")],
    )
    assert extract_structured_content(result) == payload


def test_empty_dict_structured_content_is_returned_as_is():
    """``{}`` is a valid structured payload (falsy but not ``None``);
    don't fall through to the content path."""
    result = _result(structured_content={}, content=[_text_block("ignored")])
    assert extract_structured_content(result) == {}
