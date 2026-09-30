"""Tests for resource-path policy selection.

Work IQ uses dynamic tool discovery with generic, resource-oriented
tools. Binding one policy per tool name is therefore too coarse: every
``create_entity`` call, whatever it creates, would share a policy.
``PathRules`` lets the configuration route a call to a policy by the
resource path it names, which is what these tests cover: the matcher,
the fall-through that keeps unrouted paths denied by default, and the
resolution of the config block.
"""

import json
from pathlib import Path

import jsonschema
import pytest

from middleware import (
    PathRules,
    match_path,
    resolve_policies,
    select_by_path,
)

POLICIES = Path(__file__).parents[1] / "policies" / "workiq"


def _config(rules: list[dict[str, str]], path_arg: str = "parentUrl") -> dict:
    return {"create_entity": {"pathArg": path_arg, "rules": rules}}


TEAMS_RULES = [
    {"path": "/chats/*/messages", "literal": "teams"},
    {"path": "/teams/*/channels/*/messages", "literal": "teams"},
    {"path": "/teams/*/channels/*/messages/*/replies", "literal": "teams"},
]


# Matching


@pytest.mark.parametrize(
    "url",
    [
        "/chats/chat-1/messages",
        "chats/chat-1/messages",
        "/chats/chat-1/messages?$top=10",
        "/Chats/chat-1/Messages",
    ],
)
def test_single_segment_wildcard_matches(url: str) -> None:
    spec = resolve_policies(_config(TEAMS_RULES))["create_entity"]

    assert select_by_path(spec, {"parentUrl": url}) == "teams"


@pytest.mark.parametrize(
    "url",
    [
        "/chats/chat-1",
        "/chats/chat-1/messages/m1",
        "/chats/chat-1/messages/m1/replies",
        "/events",
    ],
)
def test_unrouted_paths_select_nothing(url: str) -> None:
    # Selecting nothing is what keeps the server's ``"*"`` deny default
    # in force for creation paths nobody has written a policy for.
    spec = resolve_policies(_config(TEAMS_RULES))["create_entity"]

    assert select_by_path(spec, {"parentUrl": url}) is None


def test_double_wildcard_matches_any_number_of_segments() -> None:
    spec = resolve_policies(
        _config([{"path": "/me/messages/**", "literal": "mail"}], "actionUrl")
    )["create_entity"]

    assert select_by_path(spec, {"actionUrl": "/me/messages"}) == "mail"
    assert select_by_path(spec, {"actionUrl": "/me/messages/m1/reply"}) == "mail"
    assert select_by_path(spec, {"actionUrl": "/users/u1/messages/m1"}) is None


def test_first_matching_rule_wins() -> None:
    spec = resolve_policies(
        _config(
            [
                {"path": "/chats/*/messages", "literal": "specific"},
                {"path": "**", "literal": "catch-all"},
            ]
        )
    )["create_entity"]

    assert select_by_path(spec, {"parentUrl": "/chats/c1/messages"}) == "specific"
    assert select_by_path(spec, {"parentUrl": "/events"}) == "catch-all"


def test_missing_or_non_string_path_argument_selects_nothing() -> None:
    spec = resolve_policies(_config(TEAMS_RULES))["create_entity"]

    assert select_by_path(spec, {}) is None
    assert select_by_path(spec, None) is None
    assert select_by_path(spec, {"parentUrl": 42}) is None


def test_plain_policy_spec_ignores_arguments() -> None:
    spec = resolve_policies({"fetch": {"literal": "always"}})["fetch"]

    assert select_by_path(spec, {"anything": "at all"}) == "always"


# List-valued path arguments (``fetch`` takes ``entityUrls``)


def test_list_argument_matches_when_every_path_selects_the_same_rule() -> None:
    spec = resolve_policies(_config(TEAMS_RULES, "entityUrls"))["create_entity"]

    urls = ["/chats/c1/messages", "/teams/t1/channels/ch1/messages"]
    assert select_by_path(spec, {"entityUrls": urls}) == "teams"


def test_list_argument_mixing_policies_selects_nothing() -> None:
    spec = resolve_policies(
        _config(
            [
                {"path": "/chats/*/messages", "literal": "teams"},
                {"path": "/me/messages", "literal": "mail"},
            ],
            "entityUrls",
        )
    )["create_entity"]

    # A call that mixes domains must not be cleared by whichever policy
    # happens to come first; it falls back to the server default.
    mixed = ["/chats/c1/messages", "/me/messages"]
    assert select_by_path(spec, {"entityUrls": mixed}) is None
    assert select_by_path(spec, {"entityUrls": []}) is None


# Config resolution


def test_rules_read_policy_files() -> None:
    spec = resolve_policies(
        _config(
            [
                {
                    "path": "/chats/*/messages",
                    "file": str(POLICIES / "teams" / "messages.rego"),
                }
            ]
        )
    )["create_entity"]

    policy = select_by_path(spec, {"parentUrl": "/chats/c1/messages"})
    assert policy is not None
    assert "package policy" in policy


def test_leaf_and_path_specs_coexist() -> None:
    resolved = resolve_policies(
        {
            "*": {"literal": "deny"},
            "fetch": {"literal": "allow"},
            "create_entity": {"pathArg": "parentUrl", "rules": TEAMS_RULES},
        }
    )

    assert resolved["*"] == "deny"
    assert resolved["fetch"] == "allow"
    assert isinstance(resolved["create_entity"], PathRules)


@pytest.mark.parametrize(
    "spec",
    [
        {"pathArg": "", "rules": TEAMS_RULES},
        {"pathArg": "parentUrl", "rules": []},
        {"pathArg": "parentUrl", "rules": "nope"},
        {"pathArg": "parentUrl", "rules": [{"literal": "x"}]},
        {
            "pathArg": "parentUrl",
            "rules": [{"path": "/a", "file": "f", "literal": "x"}],
        },
    ],
)
def test_malformed_path_specs_are_rejected(spec: dict) -> None:
    with pytest.raises((TypeError, ValueError)):
        resolve_policies({"create_entity": spec})


# The shipped Work IQ configuration


def _shipped_create_entity_policy() -> PathRules:
    config = json.loads(
        (Path(__file__).parents[1] / "config.workiq.example.json").read_text(
            encoding="utf-8"
        )
    )
    middleware = config["mcpServers"]["workiq"]["middleware"]
    policies = next(
        entry["policies"] for entry in middleware if entry["type"] == "PolicyMiddleware"
    )
    resolved = resolve_policies(policies)
    return resolved["create_entity"]


@pytest.mark.parametrize(
    "parent_url, expected",
    [
        ("/chats/19:abc@thread.v2/messages", "teams/messages"),
        ("/me/chats/19:abc@thread.v2/messages", "teams/messages"),
        ("/users/u1/chats/19:abc@thread.v2/messages", "teams/messages"),
        ("/teams/t1/channels/c1/messages", "teams/messages"),
        ("/teams/t1/channels/c1/messages/m1/replies", "teams/messages"),
        # Nothing has been written for these yet, so they must fall
        # through to the server's deny default rather than borrowing the
        # Teams messaging policy.
        ("/me/events", None),
        ("/me/drive/root/children", None),
        ("/teams/t1/channels", None),
    ],
)
def test_shipped_config_routes_create_entity(
    parent_url: str, expected: str | None
) -> None:
    create_entity = _shipped_create_entity_policy()

    policy = select_by_path(create_entity, {"parentUrl": parent_url})
    if expected is None:
        assert policy is None
    else:
        assert policy is not None
        assert (POLICIES / f"{expected}.rego").read_text(encoding="utf-8") == policy


# The same machinery drives labeling


def test_labeller_rules_resolve_to_labeller_names() -> None:
    from workiq_labeller import resolve_labellers

    resolved = resolve_labellers(
        {
            "fetch": {
                "pathArg": "entityUrls",
                "rules": [
                    {"path": "/chats/*/messages/**", "labeller": "teamsMessages"},
                    {"path": "/chats/*/members", "labeller": "teamsMembers"},
                ],
            }
        }
    )["fetch"]

    assert resolved.path_arg == "entityUrls"
    assert match_path(resolved, "/chats/c1/messages") == "teamsMessages"
    assert match_path(resolved, "/chats/c1/members") == "teamsMembers"
    assert match_path(resolved, "/me/drive/root/children") is None


def test_unknown_labeller_name_is_rejected_at_startup() -> None:
    # A typo must fail loudly rather than leaving the path fail-closed
    # at runtime, where it would look like a deliberate omission.
    from workiq_labeller import resolve_labellers

    with pytest.raises(ValueError, match="unknown labeller"):
        resolve_labellers(
            {
                "fetch": {
                    "pathArg": "entityUrls",
                    "rules": [{"path": "/chats/*/messages", "labeller": "teamsChat"}],
                }
            }
        )


def test_labeller_rules_reject_policy_style_leaves() -> None:
    from workiq_labeller import resolve_labellers

    with pytest.raises((TypeError, ValueError)):
        resolve_labellers(
            {
                "fetch": {
                    "pathArg": "entityUrls",
                    "rules": [{"path": "/chats/*/messages", "file": "some.rego"}],
                }
            }
        )


def test_shipped_config_labeller_rules_cover_the_policy_paths() -> None:
    # Every conversation a message may be posted to must also be a
    # conversation the gateway knows how to label, or content read from
    # it would be fail-closed and never postable anywhere.
    from workiq_labeller import resolve_labellers

    config = json.loads(
        (Path(__file__).parents[1] / "config.workiq.example.json").read_text(
            encoding="utf-8"
        )
    )
    middleware = config["mcpServers"]["workiq"]["middleware"]
    labellers = next(
        entry["labellers"]
        for entry in middleware
        if entry["type"] == "WorkIQLabellingMiddleware"
    )
    fetch = resolve_labellers(labellers)["fetch"]

    for url in (
        "/chats/c1/messages",
        "/me/chats/c1/messages",
        "/users/u1/chats/c1/messages",
        "/teams/t1/channels/ch1/messages",
        "/teams/t1/channels/ch1/messages/m1/replies",
    ):
        assert match_path(fetch, url) == "teamsMessages", url

    for url in (
        "/me/messages",
        "/me/messages/m1",
        "/me/mailFolders/inbox/messages",
        "/users/u1/messages/m1",
    ):
        assert match_path(fetch, url) == "outlookMail", url

    for url in (
        "/me/events",
        "/me/events/e1",
        "/me/calendar/events",
        "/me/calendarView?startDateTime=2026-09-01",
        "/me/calendars/c1/calendarView",
    ):
        assert match_path(fetch, url) == "calendarEvents", url


def _shipped_output_schemas() -> dict[str, dict]:
    config = json.loads(
        (Path(__file__).parents[1] / "config.workiq.example.json").read_text(
            encoding="utf-8"
        )
    )
    middleware = config["mcpServers"]["workiq"]["middleware"]
    return next(
        entry["outputSchemas"]
        for entry in middleware
        if entry["type"] == "OutputSchemaMiddleware"
    )


def test_shipped_output_schemas_cover_only_fixed_object_responses() -> None:
    assert set(_shipped_output_schemas()) == {
        "ask",
        "search_paths",
        "fetch_blob",
        "delete_entity",
    }


@pytest.mark.parametrize(
    ("tool_name", "payload"),
    [
        (
            "ask",
            {"answer": "shape check", "conversationId": "conversation-1"},
        ),
        (
            "search_paths",
            {
                "paths": [
                    {
                        "path": "/me/messages",
                        "operations": ["fetch", "create"],
                        "operationDetails": [
                            {
                                "operation": "fetch",
                                "uriTemplate": "/me/messages{?$select,$top}",
                            },
                            {"operation": "create"},
                        ],
                    }
                ]
            },
        ),
        (
            "fetch_blob",
            {
                "statusCode": 200,
                "sizeBytes": 3,
                "base64Content": "YWJj",
                "contentType": "text/plain",
            },
        ),
        (
            "fetch_blob",
            {
                "statusCode": 404,
                "sizeBytes": 0,
                "base64Content": "",
                "error": "item not found",
                "requestId": "request-1",
            },
        ),
        (
            "delete_entity",
            {"statusCode": 204, "data": None},
        ),
        (
            "delete_entity",
            {
                "statusCode": 404,
                "data": None,
                "error": {"error": {"code": "NotFound"}},
                "requestId": "request-1",
            },
        ),
    ],
)
def test_shipped_output_schemas_accept_fixed_response_shapes(
    tool_name: str, payload: object
) -> None:
    jsonschema.validate(payload, _shipped_output_schemas()[tool_name])
