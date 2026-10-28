from pathlib import Path

import pytest

from policy_engine import _run_policy_sync

POLICIES = Path(__file__).parents[1] / "policies"
WORKIQ_POLICIES = POLICIES / "workiq"

CREATE_ENTITY_POLICY = (WORKIQ_POLICIES / "teams" / "messages.rego").read_text(
    encoding="utf-8"
)
ALLOW_POLICY = (POLICIES / "allow.rego").read_text(encoding="utf-8")
DENY_POLICY = (POLICIES / "deny.rego").read_text(encoding="utf-8")
CALENDAR_POLICY = (WORKIQ_POLICIES / "calendar" / "events.rego").read_text(
    encoding="utf-8"
)

SERVER_INFO = {"name": "WorkIQ", "version": "3.3.1"}

MEMBERS = [
    {"userId": "user-alice", "email": "alice@example.com", "displayName": "Alice"},
    {"userId": "user-bob", "email": "bob@example.com", "displayName": "Bob"},
]


def _extensions(
    readers: list[str],
    fetched: object,
    status_code: int = 200,
    integrity: str = "untrusted",
) -> dict[str, object]:
    return {
        "ifc.label": (
            1,
            lambda _path: {"integrity": integrity, "confidentiality": readers},
        ),
        "upstream.serverInfo": (0, lambda: SERVER_INFO),
        "upstream.fetch": (
            1,
            lambda _args: {"results": [{"statusCode": status_code, "data": fetched}]},
        ),
    }


def _create_decision(
    readers: list[str],
    parent_url: str = "/teams/team-1/channels/channel-1/messages",
    members: list[dict[str, str]] | None = None,
    next_link: bool = False,
    status_code: int = 200,
    integrity: str = "untrusted",
) -> dict[str, str]:
    data: dict[str, object] = {
        "value": MEMBERS if members is None else members,
    }
    if next_link:
        data["@odata.nextLink"] = "https://graph.microsoft.com/next"
    return _run_policy_sync(
        {
            "name": "create_entity",
            "arguments": {
                "parentUrl": parent_url,
                "jsonBody": {"body": {"content": "secret"}},
            },
        },
        CREATE_ENTITY_POLICY,
        _extensions(readers, data, status_code, integrity),
    )["decision"]


# create_entity: Teams messages


def test_public_content_can_be_posted() -> None:
    assert _create_decision(["public"])["decision"] == "allow"


def test_content_can_return_to_authorized_channel() -> None:
    decision = _create_decision(["user-alice", "user-bob"])

    assert decision["decision"] == "allow"


def test_content_can_return_to_channel_authorized_by_email() -> None:
    decision = _create_decision(["alice@example.com", "bob@example.com"])

    assert decision["decision"] == "allow"


def test_cross_group_post_requires_approval() -> None:
    decision = _create_decision(["user-alice"])

    assert decision["decision"] == "ask"
    assert "bob@example.com" in decision["message"]


def test_trusted_context_can_declassify_without_approval() -> None:
    decision = _create_decision([], status_code=404, integrity="trusted")

    assert decision["decision"] == "allow"
    assert "trusted context" in decision["message"]


def test_chat_message_uses_chat_roster() -> None:
    decision = _create_decision(
        ["user-alice"], parent_url="/chats/19:abc@thread.v2/messages"
    )

    assert decision["decision"] == "ask"
    assert "bob@example.com" in decision["message"]


def test_channel_reply_is_covered() -> None:
    decision = _create_decision(
        ["user-alice"],
        parent_url="/teams/team-1/channels/channel-1/messages/message-1/replies",
    )

    assert decision["decision"] == "ask"


def test_paginated_roster_fails_closed() -> None:
    decision = _create_decision(["user-alice", "user-bob"], next_link=True)

    assert decision["decision"] == "ask"
    assert "complete membership" in decision["message"]


def test_unavailable_roster_fails_closed() -> None:
    decision = _create_decision(["user-alice", "user-bob"], status_code=404)

    assert decision["decision"] == "ask"


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"value": None},
        {"value": {}},
        {"value": []},
        {"value": ["invalid"]},
        {"value": [MEMBERS[0], "invalid"]},
    ],
)
def test_unverifiable_roster_requires_approval(data) -> None:
    decision = _run_policy_sync(
        {
            "name": "create_entity",
            "arguments": {
                "parentUrl": "/chats/chat-1/messages",
                "jsonBody": {"body": {"content": "secret"}},
            },
        },
        CREATE_ENTITY_POLICY,
        _extensions(["user-alice", "user-bob"], data),
    )["decision"]

    assert decision["decision"] == "ask"


@pytest.mark.parametrize(
    "readers,integrity", [([], "trusted"), (["public"], "untrusted")]
)
def test_unverifiable_roster_preserves_trusted_or_public_allow(
    readers, integrity
) -> None:
    def unexpected_fetch(_arguments):
        pytest.fail("Trusted or Public calls must not depend on a membership lookup")

    extensions = _extensions(readers, {}, integrity=integrity)
    extensions["upstream.fetch"] = (1, unexpected_fetch)
    decision = _run_policy_sync(
        {
            "name": "create_entity",
            "arguments": {
                "parentUrl": "/chats/chat-1/messages",
                "jsonBody": {"body": {"content": "secret"}},
            },
        },
        CREATE_ENTITY_POLICY,
        extensions,
    )["decision"]

    assert decision["decision"] == "allow"


def test_unvetted_creation_path_is_denied() -> None:
    decision = _create_decision(["public"], parent_url="/me/drive/root/children")

    assert decision["decision"] == "deny"


def test_trusted_context_does_not_extend_teams_policy_to_other_paths() -> None:
    assert (
        _create_decision(
            ["public"], parent_url="/me/drive/root/children", integrity="trusted"
        )["decision"]
        == "deny"
    )


# allow / deny


def test_allow_policy_allows() -> None:
    decision = _run_policy_sync(
        {"name": "fetch", "arguments": {"entityUrls": ["/me/messages"]}},
        ALLOW_POLICY,
        {"upstream.serverInfo": (0, lambda: SERVER_INFO)},
    )["decision"]

    assert decision["decision"] == "allow"


def test_deny_policy_denies() -> None:
    decision = _run_policy_sync(
        {"name": "delete_entity", "arguments": {"entityUrl": "/me/messages/m1"}},
        DENY_POLICY,
        {"upstream.serverInfo": (0, lambda: SERVER_INFO)},
    )["decision"]

    assert decision["decision"] == "deny"


@pytest.mark.parametrize("version", ["3.3.1", "3.4.5", "0.1.0", "service-build"])
@pytest.mark.parametrize(
    ("policy", "expected"), [(ALLOW_POLICY, "allow"), (DENY_POLICY, "deny")]
)
def test_generic_policies_do_not_confuse_transport_versions_with_service_versions(
    version, policy, expected
) -> None:
    result = _run_policy_sync(
        {"name": "fetch", "arguments": {}},
        policy,
        {"upstream.serverInfo": (0, lambda: {"name": "workiq", "version": version})},
    )
    assert result["decision"]["decision"] == expected


@pytest.mark.parametrize(
    "policy", [ALLOW_POLICY, DENY_POLICY, CREATE_ENTITY_POLICY, CALENDAR_POLICY]
)
@pytest.mark.parametrize("version", ["3.3.1", "3.4.5", "invalid", 42, None])
def test_explicit_version_pin_rejects_mismatch_and_missing_identity(policy, version):
    info = None if version is None else {"name": "workiq", "version": version}
    result = _run_policy_sync(
        {
            "name": "create_entity",
            "arguments": {
                "parentUrl": (
                    "/chats/c1/messages"
                    if policy == CREATE_ENTITY_POLICY
                    else "/me/events"
                ),
                "jsonBody": {"subject": "Review"},
            },
        },
        policy.replace('expected_version := ""', 'expected_version := "3.3.1"'),
        {
            **_extensions(["public"], {"value": MEMBERS}, integrity="trusted"),
            "upstream.serverInfo": (0, lambda: info),
        },
    )
    if version == "3.3.1":
        assert result["decision"]["decision"] == (
            "deny" if policy == DENY_POLICY else "allow"
        )
        assert "incompatible" not in result["decision"]["message"]
    else:
        assert result["decision"]["decision"] == "deny"
        assert "incompatible" in result["decision"]["message"]


OWNER = {"id": "user-alice", "mail": "alice@example.com"}
BOB = {"emailAddress": {"address": "bob@example.com"}}
EVENT = {
    "id": "e1",
    "organizer": {"emailAddress": {"address": "alice@example.com"}},
    "attendees": [],
}


def _calendar_decision(
    readers,
    *,
    operation="create_entity",
    body=None,
    path=None,
    owner=OWNER,
    event=EVENT,
    status=200,
    integrity="untrusted",
):
    path_key = "parentUrl" if operation == "create_entity" else "entityUrl"
    target = path or ("/me/events" if operation == "create_entity" else "/me/events/e1")

    def fetch(arguments):
        url = arguments["entityUrls"][0].split("?")[0]
        return {
            "results": [
                {
                    "statusCode": status,
                    "data": owner if url == "/me" else event,
                }
            ]
        }

    return _run_policy_sync(
        {
            "name": operation,
            "arguments": {
                path_key: target,
                "jsonBody": {"subject": "Review"} if body is None else body,
            },
        },
        CALENDAR_POLICY,
        {
            **_extensions(readers, {}, integrity=integrity),
            "upstream.fetch": (1, fetch),
        },
    )["decision"]


@pytest.mark.parametrize("operation", ["create_entity", "update_entity"])
def test_calendar_owner_can_receive_private_event_content(operation):
    assert (
        _calendar_decision(["user-alice", "alice@example.com"], operation=operation)[
            "decision"
        ]
        == "allow"
    )


def test_calendar_accepts_serialized_json_body():
    assert (
        _calendar_decision(
            ["user-alice"],
            body='{"subject":"Review","attendees":[]}',
        )["decision"]
        == "allow"
    )


@pytest.mark.parametrize("operation", ["create_entity", "update_entity"])
def test_calendar_new_attendee_requires_authorization(operation):
    decision = _calendar_decision(
        ["user-alice", "alice@example.com"],
        operation=operation,
        body={"attendees": [BOB]},
    )
    assert decision["decision"] == "ask"
    assert "bob@example.com" in decision["message"]
    assert (
        _calendar_decision(
            ["user-alice", "ALICE@example.com", "BOB@example.com"],
            operation=operation,
            body={"attendees": [BOB]},
        )["decision"]
        == "allow"
    )


def test_calendar_update_checks_existing_attendees_even_when_removed():
    assert (
        _calendar_decision(
            ["user-alice", "alice@example.com"],
            operation="update_entity",
            body={"attendees": []},
            event={**EVENT, "attendees": [BOB]},
        )["decision"]
        == "ask"
    )


def test_calendar_update_does_not_trust_supplied_organizer():
    assert (
        _calendar_decision(
            ["user-alice", "alice@example.com"],
            operation="update_entity",
            body={"organizer": EVENT["organizer"]},
            event={**EVENT, "organizer": BOB},
        )["decision"]
        == "ask"
    )


@pytest.mark.parametrize(
    "arguments",
    [
        {"owner": {}},
        {"status": 404},
        {"body": {"attendees": [{}]}},
        {"operation": "update_entity", "event": {"id": "e1"}},
        {"operation": "update_entity", "event": {**EVENT, "attendees": None}},
    ],
)
def test_calendar_unknown_audience_requires_approval(arguments):
    assert (
        _calendar_decision(
            ["user-alice", "alice@example.com"],
            **arguments,
        )["decision"]
        == "ask"
    )


def test_calendar_owner_is_part_of_the_audience():
    assert (
        _calendar_decision(
            ["bob@example.com"],
            body={"attendees": [BOB]},
        )["decision"]
        == "ask"
    )


@pytest.mark.parametrize("missing", [None, "owner", "organizer", "attendee"])
def test_calendar_all_three_roles_must_be_authorized(missing):
    addresses = {
        "owner": "alice@example.com",
        "organizer": "bob@example.com",
        "attendee": "carol@example.com",
    }
    readers = [address for role, address in addresses.items() if role != missing]
    decision = _calendar_decision(
        readers,
        operation="update_entity",
        event={
            **EVENT,
            "organizer": BOB,
            "attendees": [{"emailAddress": {"address": addresses["attendee"]}}],
        },
    )
    assert decision["decision"] == ("allow" if missing is None else "ask")


@pytest.mark.parametrize("operation", ["create_entity", "update_entity"])
def test_calendar_proposed_organizer_is_also_checked(operation):
    assert (
        _calendar_decision(
            ["user-alice", "alice@example.com"],
            operation=operation,
            body={"organizer": BOB},
        )["decision"]
        == "ask"
    )


@pytest.mark.parametrize("body", ["invalid JSON", "[]", {"attendees": None}])
def test_calendar_rejects_invalid_event_payload(body):
    assert _calendar_decision(["public"], body=body)["decision"] == "deny"


@pytest.mark.parametrize(
    "operation,path",
    [
        ("create_entity", "/me/drive/root/children"),
        ("create_entity", "/users/another-user/events"),
        ("update_entity", "/me/messages/e1"),
        ("update_entity", "/me/events/.."),
        ("update_entity", "/me/events/%2E%2E"),
        ("update_entity", "/me/events/x%2Fy"),
        ("delete_entity", "/me/events/e1"),
    ],
)
def test_calendar_policy_rejects_uncovered_paths_even_in_trusted_context(
    operation, path
):
    assert (
        _calendar_decision(
            ["public"],
            operation=operation,
            path=path,
            integrity="trusted",
        )["decision"]
        == "deny"
    )
