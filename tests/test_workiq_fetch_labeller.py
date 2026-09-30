from __future__ import annotations

from typing import Any

import pytest

from middleware import PathRule, PathRules
from workiq_labeller import WorkIQLabeling

TEAMS_FETCH_RULES = PathRules(
    path_arg="entityUrls",
    rules=(
        PathRule(pattern=("chats", "*", "members"), value="teamsMembers"),
        PathRule(
            pattern=("me", "chats", "*", "members"),
            value="teamsMembers",
        ),
        PathRule(
            pattern=("users", "*", "chats", "*", "members"),
            value="teamsMembers",
        ),
        PathRule(
            pattern=("teams", "*", "channels", "*", "members"),
            value="teamsMembers",
        ),
        PathRule(
            pattern=("chats", "*", "messages", "**"),
            value="teamsMessages",
        ),
        PathRule(
            pattern=("me", "chats", "*", "messages", "**"),
            value="teamsMessages",
        ),
        PathRule(
            pattern=("users", "*", "chats", "*", "messages", "**"),
            value="teamsMessages",
        ),
        PathRule(
            pattern=("teams", "*", "channels", "*", "messages", "**"),
            value="teamsMessages",
        ),
    ),
)

ROSTER = {
    "results": [
        {
            "statusCode": 200,
            "data": {
                "value": [
                    {"userId": "user-alice", "email": "Alice@example.com"},
                    {"userId": "user-bob", "email": "bob@example.com"},
                ]
            },
        }
    ]
}


def _call_upstream_returning(payload: dict[str, Any]):
    calls: list[tuple[str, dict[str, Any]]] = []

    async def call_upstream(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        calls.append((name, arguments))
        return payload

    return call_upstream, calls


def _labels(meta: Any) -> dict[str, Any]:
    return meta.ifc_labels["$"].model_dump()


@pytest.mark.anyio
async def test_fetch_of_channel_messages_is_labelled_with_the_roster() -> None:
    call_upstream, calls = _call_upstream_returning(ROSTER)

    meta = await WorkIQLabeling.labelfetch(
        {"entityUrls": ["/teams/team-1/channels/channel-1/messages?$top=5"]},
        {"results": [{"statusCode": 200, "data": {"value": [{"id": "m1"}]}}]},
        call_upstream,
        TEAMS_FETCH_RULES,
    )

    assert _labels(meta) == {
        "integrity": "untrusted",
        "confidentiality": [
            "alice@example.com",
            "bob@example.com",
            "user-alice",
            "user-bob",
        ],
    }
    assert calls[0][0] == "fetch"
    assert calls[0][1]["entityUrls"][0].startswith(
        "/teams/team-1/channels/channel-1/members?"
    )


@pytest.mark.anyio
async def test_fetch_of_chat_messages_uses_chat_roster() -> None:
    call_upstream, calls = _call_upstream_returning(ROSTER)

    await WorkIQLabeling.labelfetch(
        {"entityUrls": ["/me/chats/19:abc@thread.v2/messages"]},
        {"results": [{"statusCode": 200, "data": {"value": []}}]},
        call_upstream,
        TEAMS_FETCH_RULES,
    )

    assert calls[0][1]["entityUrls"][0].startswith("/chats/19:abc@thread.v2/members?")


@pytest.mark.anyio
async def test_fetch_of_a_member_roster_is_labelled_with_its_members() -> None:
    call_upstream, calls = _call_upstream_returning(ROSTER)

    meta = await WorkIQLabeling.labelfetch(
        {"entityUrls": ["/chats/19:abc@thread.v2/members"]},
        ROSTER,
        call_upstream,
        TEAMS_FETCH_RULES,
    )

    assert _labels(meta)["integrity"] == "trusted"
    assert _labels(meta)["confidentiality"] == [
        "alice@example.com",
        "bob@example.com",
        "user-alice",
        "user-bob",
    ]
    assert calls == []


@pytest.mark.anyio
async def test_multiple_paths_are_joined() -> None:
    call_upstream, _ = _call_upstream_returning(ROSTER)

    meta = await WorkIQLabeling.labelfetch(
        {
            "entityUrls": [
                "/chats/19:abc@thread.v2/members",
                "/chats/19:abc@thread.v2/messages",
            ]
        },
        {
            "results": [
                ROSTER["results"][0],
                {"statusCode": 200, "data": {"value": [{"id": "m1"}]}},
            ]
        },
        call_upstream,
        TEAMS_FETCH_RULES,
    )

    # Both paths resolve to the same roster, so the join (an
    # intersection of reader sets) leaves it unchanged.
    assert _labels(meta)["confidentiality"] == [
        "alice@example.com",
        "bob@example.com",
        "user-alice",
        "user-bob",
    ]


@pytest.mark.anyio
async def test_join_with_an_unknown_path_is_fail_closed() -> None:
    call_upstream, _ = _call_upstream_returning(ROSTER)

    meta = await WorkIQLabeling.labelfetch(
        {"entityUrls": ["/chats/19:abc@thread.v2/members", "/me/people"]},
        {
            "results": [
                ROSTER["results"][0],
                {"statusCode": 200, "data": {"value": [{"id": "p1"}]}},
            ]
        },
        call_upstream,
        TEAMS_FETCH_RULES,
    )

    # ``/me/people`` matches no rule, so it contributes an empty reader
    # set and the join empties the whole payload's audience.
    assert _labels(meta) == {"integrity": "untrusted", "confidentiality": []}


@pytest.mark.anyio
async def test_unknown_path_is_fail_closed() -> None:
    call_upstream, _ = _call_upstream_returning(ROSTER)

    meta = await WorkIQLabeling.labelfetch(
        {"entityUrls": ["/me/drive/root/children"]},
        {"results": [{"statusCode": 200, "data": {"value": []}}]},
        call_upstream,
        TEAMS_FETCH_RULES,
    )

    # An unrecognized path is not evidence that its contents are public.
    assert _labels(meta) == {"integrity": "untrusted", "confidentiality": []}


@pytest.mark.anyio
async def test_configured_rules_only_cover_named_paths() -> None:
    call_upstream, _ = _call_upstream_returning(ROSTER)
    rules = PathRules(
        path_arg="entityUrls",
        rules=(PathRule(pattern=("widgets", "*"), value="teamsMembers"),),
    )

    meta = await WorkIQLabeling.labelfetch(
        {"entityUrls": ["/widgets/w1"]},
        {"results": [ROSTER["results"][0]]},
        call_upstream,
        rules,
    )

    assert _labels(meta)["confidentiality"] == [
        "alice@example.com",
        "bob@example.com",
        "user-alice",
        "user-bob",
    ]

    # A path the configured rules do not name is fail-closed.
    meta = await WorkIQLabeling.labelfetch(
        {"entityUrls": ["/chats/19:abc@thread.v2/members"]},
        {"results": [ROSTER["results"][0]]},
        call_upstream,
        rules,
    )

    assert _labels(meta) == {"integrity": "untrusted", "confidentiality": []}


@pytest.mark.anyio
async def test_missing_fetch_rules_are_fail_closed() -> None:
    call_upstream, _ = _call_upstream_returning(ROSTER)

    meta = await WorkIQLabeling.labelfetch(
        {"entityUrls": ["/chats/19:abc@thread.v2/members"]},
        ROSTER,
        call_upstream,
    )

    assert _labels(meta) == {"integrity": "untrusted", "confidentiality": []}


@pytest.mark.parametrize(
    ("labeler", "expected"),
    [
        (
            WorkIQLabeling.labelask,
            {"integrity": "untrusted", "confidentiality": []},
        ),
        (
            WorkIQLabeling.labelsearch_paths,
            {"integrity": "trusted", "confidentiality": ["public"]},
        ),
        (
            WorkIQLabeling.labelget_schema,
            {"integrity": "trusted", "confidentiality": ["public"]},
        ),
        (
            WorkIQLabeling.labellist_agents,
            {"integrity": "trusted", "confidentiality": []},
        ),
    ],
)
def test_static_tool_default_labels(labeler: Any, expected: dict[str, Any]) -> None:
    meta = labeler({})

    assert _labels(meta) == expected
