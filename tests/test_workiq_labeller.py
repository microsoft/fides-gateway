from __future__ import annotations

import json
from typing import Any

import pytest
from fastmcp.server.middleware import MiddlewareContext
from fastmcp.tools import ToolResult
from mcp.types import CallToolRequestParams, TextContent

from policy_engine import (
    IFC_LABELS_META_PREFIX,
    _build_effective_labels,
    _resolve_effective_label,
)
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
async def test_calendar_fields_use_owner_organizer_and_attendees_as_readers() -> None:
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

    async def owner_lookup(name, arguments):
        assert name == "fetch"
        assert arguments == {"entityUrls": ["/me?$select=id,mail,userPrincipalName"]}
        return {
            "results": [
                {
                    "statusCode": 200,
                    "data": {"id": "owner-id", "mail": "Owner@example.com"},
                }
            ]
        }

    meta = await WorkIQLabeling.labelfetch(
        {"entityUrls": ["/me/events"]},
        output,
        owner_lookup,
        _fetch_rules("/me/events/**", "calendarEvents"),
    )
    labels = _dump_labels(meta)
    readers = [
        "attendee@example.com",
        "organizer@example.com",
        "owner-id",
        "owner@example.com",
    ]

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
@pytest.mark.parametrize("status,data", [(404, {}), (200, {}), (200, None)])
async def test_unknown_calendar_owner_fails_closed(status, data, caplog):
    async def owner_lookup(name, arguments):
        return {"results": [{"statusCode": status, "data": data}]}

    meta = await WorkIQLabeling.labelfetch(
        {"entityUrls": ["/me/events"]},
        {"results": [{"statusCode": 200, "data": {"id": "event-1"}}]},
        owner_lookup,
        _fetch_rules("/me/events/**", "calendarEvents"),
    )
    assert _dump_labels(meta)["$"] == {
        "integrity": "untrusted",
        "confidentiality": [],
    }
    assert "Cannot verify Calendar owner" in caplog.text


@pytest.mark.anyio
async def test_named_calendar_uses_calendar_owner_not_current_user():
    async def owner_lookup(name, arguments):
        assert arguments == {"entityUrls": ["/me/calendars/shared?$select=owner"]}
        return {
            "results": [
                {
                    "statusCode": 200,
                    "data": {"owner": {"address": "owner@example.com"}},
                }
            ]
        }

    meta = await WorkIQLabeling.labelfetch(
        {"entityUrls": ["/me/calendars/shared/calendarView"]},
        {"results": [{"statusCode": 200, "data": {"id": "event-1"}}]},
        owner_lookup,
        _fetch_rules("/me/calendars/*/calendarView/**", "calendarEvents"),
    )
    assert _dump_labels(meta)["$"]["confidentiality"] == ["owner@example.com"]


@pytest.mark.anyio
async def test_other_mailbox_does_not_inherit_current_user_as_calendar_owner():
    meta = await WorkIQLabeling.labelfetch(
        {"entityUrls": ["/users/another-user/events"]},
        {"results": [{"statusCode": 200, "data": {"id": "event-1"}}]},
        _unused_upstream,
        _fetch_rules("/users/*/events/**", "calendarEvents"),
    )
    assert _dump_labels(meta)["$"]["confidentiality"] == []


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
    assert labels["$['structuredContent']['data']"] == {
        "integrity": "untrusted",
        "confidentiality": [],
    }


@pytest.mark.parametrize(
    "tool",
    [
        "fetch_blob",
        "call_function",
        "create_entity",
        "update_entity",
        "delete_entity",
        "do_action",
    ],
)
@pytest.mark.parametrize("field", ["data", "unexpected'payload"])
def test_response_payload_effective_labels_remain_private(tool, field) -> None:
    payload = {"statusCode": 200, field: {"nested": ["private content"]}}
    labels = _dump_labels(getattr(WorkIQLabeling, f"label{tool}")({}, payload))
    effective = _build_effective_labels({"$['structuredContent']": payload}, labels)

    def resolve(*path):
        return _resolve_effective_label(list(path), labels, effective, "test response")

    private = {"integrity": "untrusted", "confidentiality": []}
    assert resolve("structuredContent") == private
    assert resolve("structuredContent", field, "nested", 0) == private
    assert resolve("structuredContent", "statusCode") == {
        "integrity": "trusted",
        "confidentiality": ["public"],
    }


@pytest.mark.parametrize(
    "payload",
    [
        {"statusCode": 204, "requestId": "request-1"},
        {"statusCode": 200, "data": None},
        {"statusCode": 200, "data": []},
        {},
    ],
)
def test_response_empty_payload_and_metadata_only_labels(payload) -> None:
    labels = _dump_labels(WorkIQLabeling.labelfetch_blob({}, payload))
    effective = _build_effective_labels({"$['structuredContent']": payload}, labels)
    actual = _resolve_effective_label(
        ["structuredContent"],
        labels,
        effective,
        "test response",
    )
    assert actual == (
        {"integrity": "trusted", "confidentiality": ["public"]}
        if payload and "data" not in payload
        else {"integrity": "untrusted", "confidentiality": []}
    )
