from __future__ import annotations

import json
from typing import Any

import pytest
from fastmcp.server.middleware import MiddlewareContext
from fastmcp.tools import ToolResult
from mcp.types import CallToolRequestParams, TextContent

from policy_engine import IFC_LABELS_META_PREFIX
from workiq_labeller import (
    WorkIQLabeling,
    WorkIQLabellingMiddleware,
    resolve_labellers,
)


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
            "integrity": "untrusted",
            "confidentiality": [],
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
    a broken upstream response must still produce a fail-closed label."""
    middleware = WorkIQLabellingMiddleware()
    context = _ctx("NoSpecificLabeler")

    async def call_next(_context: object) -> ToolResult:
        return _undecodable_result()

    # Must NOT raise — no labeler means no risk of mislabeling.
    result = await middleware.on_call_tool(context, call_next)
    assert result.meta is not None
    assert result.meta[IFC_LABELS_META_PREFIX] == {
        "$": {
            "integrity": "untrusted",
            "confidentiality": [],
        },
    }


@pytest.mark.anyio
async def test_failed_async_labeler_preserves_extracted_structured_content() -> None:
    middleware = WorkIQLabellingMiddleware(
        labellers={
            "fetch": {
                "pathArg": "entityUrls",
                "rules": [
                    {
                        "path": "/chats/*/messages/**",
                        "labeller": "teamsMessages",
                    }
                ],
            }
        }
    )
    context = _ctx(
        "fetch",
        {"entityUrls": ["/chats/chat-1/messages"]},
    )
    payload = {
        "results": [
            {
                "statusCode": 200,
                "data": {"value": [{"body": {"content": "hello"}}]},
            }
        ]
    }

    async def call_next(_context: object) -> ToolResult:
        return ToolResult(content=[TextContent(type="text", text=json.dumps(payload))])

    result = await middleware.on_call_tool(context, call_next)

    assert result.structured_content == payload
    assert result.meta[IFC_LABELS_META_PREFIX] == {
        "$": {
            "integrity": "untrusted",
            "confidentiality": [],
        }
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("tool_name", "expected"),
    [
        (
            "get_schema",
            {"integrity": "trusted", "confidentiality": ["public"]},
        ),
    ],
)
async def test_static_default_labelers_do_not_require_structured_output(
    tool_name: str, expected: dict[str, Any]
) -> None:
    middleware = WorkIQLabellingMiddleware()
    context = _ctx(tool_name)

    async def call_next(_context: object) -> ToolResult:
        return _undecodable_result()

    result = await middleware.on_call_tool(context, call_next)

    assert result.meta is not None
    assert result.meta[IFC_LABELS_META_PREFIX] == {"$": expected}


def _dump_labels(meta: Any) -> dict[str, dict[str, Any]]:
    return {path: label.model_dump() for path, label in meta.ifc_labels.items()}


async def _unused_upstream(_name: str, _arguments: dict[str, Any]) -> dict[str, Any]:
    raise AssertionError("This labeler must not call the upstream")


def _fetch_rules(path: str, labeller: str) -> Any:
    return resolve_labellers(
        {
            "fetch": {
                "pathArg": "entityUrls",
                "rules": [{"path": path, "labeller": labeller}],
            }
        }
    )["fetch"]


@pytest.mark.anyio
async def test_mail_fields_use_sender_and_recipients_as_readers() -> None:
    output = {
        "results": [
            {
                "statusCode": 200,
                "data": {
                    "value": [
                        {
                            "id": "message-1",
                            "subject": "Untrusted subject",
                            "from": {"emailAddress": {"address": "alice@example.com"}},
                            "toRecipients": [
                                {"emailAddress": {"address": "bob@example.com"}}
                            ],
                        }
                    ]
                },
            }
        ]
    }
    meta = await WorkIQLabeling.labelfetch(
        {"entityUrls": ["/me/messages"]},
        output,
        _unused_upstream,
        _fetch_rules("/me/messages/**", "outlookMail"),
    )
    labels = _dump_labels(meta)
    readers = ["alice@example.com", "bob@example.com"]

    assert labels["$['structuredContent']['results'][0]['data']['value'][0]"] == {
        "integrity": "untrusted",
        "confidentiality": readers,
    }
    assert labels["$['structuredContent']['results'][0]['data']['value'][0]['id']"] == {
        "integrity": "trusted",
        "confidentiality": readers,
    }
    assert labels["$['structuredContent']['results'][0]['statusCode']"] == {
        "integrity": "trusted",
        "confidentiality": ["public"],
    }


@pytest.mark.anyio
async def test_calendar_fields_use_organizer_and_attendees_as_readers() -> None:
    output = {
        "results": [
            {
                "statusCode": 200,
                "data": {
                    "value": [
                        {
                            "id": "event-1",
                            "subject": "Untrusted subject",
                            "organizer": {
                                "emailAddress": {"address": "organizer@example.com"}
                            },
                            "attendees": [
                                {"emailAddress": {"address": "attendee@example.com"}}
                            ],
                            "start": {
                                "dateTime": "2026-09-10T09:00:00",
                                "timeZone": "UTC",
                            },
                        }
                    ]
                },
            }
        ]
    }
    meta = await WorkIQLabeling.labelfetch(
        {"entityUrls": ["/me/events"]},
        output,
        _unused_upstream,
        _fetch_rules("/me/events/**", "calendarEvents"),
    )
    labels = _dump_labels(meta)
    readers = ["attendee@example.com", "organizer@example.com"]

    assert labels["$['structuredContent']['results'][0]['data']['value'][0]"] == {
        "integrity": "untrusted",
        "confidentiality": readers,
    }
    assert labels[
        "$['structuredContent']['results'][0]['data']['value'][0]['organizer']"
    ] == {
        "integrity": "trusted",
        "confidentiality": readers,
    }


@pytest.mark.anyio
async def test_member_fields_are_trusted_for_the_roster_audience() -> None:
    output = {
        "results": [
            {
                "statusCode": 200,
                "data": {
                    "value": [
                        {
                            "id": "member-1",
                            "displayName": "Alice",
                            "userId": "user-alice",
                            "email": "alice@example.com",
                        }
                    ]
                },
            }
        ]
    }
    meta = await WorkIQLabeling.labelfetch(
        {"entityUrls": ["/chats/chat-1/members"]},
        output,
        _unused_upstream,
        _fetch_rules("/chats/*/members", "teamsMembers"),
    )
    labels = _dump_labels(meta)

    assert labels[
        "$['structuredContent']['results'][0]['data']['value'][0]['displayName']"
    ] == {
        "integrity": "trusted",
        "confidentiality": ["alice@example.com", "user-alice"],
    }


def test_write_response_envelope_is_trusted_but_data_is_not() -> None:
    labels = _dump_labels(
        WorkIQLabeling.labelcreate_entity(
            {},
            {
                "statusCode": 201,
                "data": {"body": {"content": "untrusted"}},
                "requestId": "request-1",
            },
        )
    )

    assert labels["$"] == {
        "integrity": "untrusted",
        "confidentiality": [],
    }
    assert labels["$['structuredContent']['statusCode']"] == {
        "integrity": "trusted",
        "confidentiality": ["public"],
    }
    assert labels["$['structuredContent']['requestId']"] == {
        "integrity": "trusted",
        "confidentiality": ["public"],
    }
