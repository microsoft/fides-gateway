from pathlib import Path

from policy_engine import _run_policy_sync

POLICIES = Path(__file__).parents[1] / "policies"
WORKIQ_POLICIES = POLICIES / "workiq"

CREATE_ENTITY_POLICY = (WORKIQ_POLICIES / "teams" / "messages.rego").read_text(
    encoding="utf-8"
)
ALLOW_POLICY = (POLICIES / "allow.rego").read_text(encoding="utf-8")
DENY_POLICY = (POLICIES / "deny.rego").read_text(encoding="utf-8")

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


def test_unvetted_creation_path_is_denied() -> None:
    decision = _create_decision(["public"], parent_url="/me/drive/root/children")

    assert decision["decision"] == "deny"


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
