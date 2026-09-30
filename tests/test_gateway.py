from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys

import httpx
import pytest
from fastmcp import Client, FastMCP
from fastmcp.client.transports import FastMCPTransport
from fastmcp.server.middleware import Middleware
from fastmcp.tools import ToolResult
from mcp.types import TextContent
from starlette.applications import Starlette
from starlette.routing import Mount

import msal_auth
from fastmcp_proxy import MCPGateway, load_config
from mcp_result import extract_structured_content
from middleware import (
    MetaPrefixTranslationMiddleware,
    PolicyMiddleware,
    StripFastmcpMetaMiddleware,
)
from output_schema import OutputSchemaMiddleware
from github_labeller import GitHubLabellingMiddleware
from workiq_labeller import WorkIQLabellingMiddleware
from msal_auth import MSALBearerAuth, load_msal_cache, save_msal_cache

from typing import Any

# ---------------------------------------------------------------------------
# Tiny FastMCP backend used as an in-memory upstream for sanity tests
# ---------------------------------------------------------------------------


_SAMPLE_USERS = [
    {
        "id": "11111111-1111-1111-1111-111111111111",
        "displayName": "Alice Anderson",
        "email": "alice@example.com",
    },
    {
        "id": "22222222-2222-2222-2222-222222222222",
        "displayName": "Bob Brown",
        "email": "bob@example.com",
    },
    {
        "id": "33333333-3333-3333-3333-333333333333",
        "displayName": "Carol Chen",
        "email": "carol@example.com",
    },
    {
        "id": "44444444-4444-4444-4444-444444444444",
        "displayName": "Dave Davis",
        "email": "dave@example.com",
    },
    {
        "id": "55555555-5555-5555-5555-555555555555",
        "displayName": "Eve Evans",
        "email": "eve@example.com",
    },
    {
        "id": "66666666-6666-6666-6666-666666666666",
        "displayName": "Frank Foster",
        "email": "frank@example.com",
    },
]

_SAMPLE_TEAMS = [
    {
        "id": "aaaa0001-0000-0000-0000-000000000000",
        "displayName": "Engineering",
        "description": "Engineering team",
        "webUrl": None,
    },
    {
        "id": "aaaa0002-0000-0000-0000-000000000000",
        "displayName": "Product",
        "description": "Product team",
        "webUrl": None,
    },
    {
        "id": "aaaa0003-0000-0000-0000-000000000000",
        "displayName": "Operations",
        "description": "Operations team",
        "webUrl": None,
    },
]

_CHANNEL_GENERAL_ID = "19:general-abc@thread.tacv2"
_CHANNEL_ANNOUNCEMENTS_ID = "19:announcements-xyz@thread.tacv2"

_SAMPLE_CHAT_ID = "19:8ecb0abf7a3d4e57aed6fa15b783cedd@thread.v2"
_SAMPLE_SENT_MESSAGE_ID = "1778589434289"
_SAMPLE_SENT_DATETIME = "2026-05-12T12:37:14Z"

_SAMPLE_CHANNELS = [
    {
        "id": _CHANNEL_GENERAL_ID,
        "displayName": "General",
        "description": "General discussion",
        "membershipType": "Standard",
        "createdDateTime": "2026-04-24T12:51:08Z",
        "webUrl": "https://teams.cloud.microsoft/l/channel/general",
    },
    {
        "id": _CHANNEL_ANNOUNCEMENTS_ID,
        "displayName": "Announcements",
        "description": "Team-wide announcements",
        "membershipType": "Standard",
        "createdDateTime": "2026-04-24T12:51:08Z",
        "webUrl": "https://teams.cloud.microsoft/l/channel/announcements",
    },
]


def _member(user: dict, roles: list[str]) -> dict:
    return {
        "id": f"MCMj-{user['id']}",
        "displayName": user["displayName"],
        "email": user["email"],
        "userId": user["id"],
        "roles": list(roles),
    }


_CHANNEL_MEMBERS = {
    _CHANNEL_GENERAL_ID: [
        _member(_SAMPLE_USERS[0], ["owner"]),
        _member(_SAMPLE_USERS[1], []),
        _member(_SAMPLE_USERS[2], []),
        _member(_SAMPLE_USERS[3], []),
    ],
    _CHANNEL_ANNOUNCEMENTS_ID: [
        _member(_SAMPLE_USERS[0], ["owner"]),
        _member(_SAMPLE_USERS[4], []),
        _member(_SAMPLE_USERS[5], []),
    ],
}


_SAMPLE_CORRELATION_ID = "1f8552f5-2933-412a-b747-21d858eb88a0"
_SAMPLE_TIMESTAMP = "2026-05-22_10:44:02"


def _wiq_result(payload: dict) -> ToolResult:
    """Wrap *payload* in a WorkIQ-style ``ToolResult``.

    The real WorkIQ MCP server never populates ``structured_content``;
    instead it returns ``content[0].text`` as an escaped-JSON dump of
    the payload plus a trailing ``content[1].text`` carrying
    ``CorrelationId: <guid>, TimeStamp: <ts>`` diagnostics. The test
    backend mimics that shape so every upstream-reading code path
    exercises the
    :func:`mcp_result.extract_structured_content` fallback.
    """
    return ToolResult(
        content=[
            TextContent(type="text", text=json.dumps(payload)),
            TextContent(
                type="text",
                text=f"CorrelationId: {_SAMPLE_CORRELATION_ID}, "
                f"TimeStamp: {_SAMPLE_TIMESTAMP}",
            ),
        ],
        # structured_content intentionally omitted — matches the real
        # WorkIQ wire shape.
    )


def _make_backend() -> FastMCP:
    backend = FastMCP("test-backend")

    @backend.tool
    def ListTeams() -> ToolResult:
        """List the teams the caller belongs to."""
        return _wiq_result({"teams": [dict(t) for t in _SAMPLE_TEAMS]})

    @backend.tool
    def ListChannels(
        teamId: str,
        select: str | None = None,
        filter: str | None = None,
    ) -> ToolResult:
        """List the channels in a team."""
        del teamId, select, filter  # sample backend ignores filtering
        return _wiq_result({"channels": [dict(c) for c in _SAMPLE_CHANNELS]})

    @backend.tool
    def ListChannelMembers(
        teamId: str,
        channelId: str,
        top: int = 100,
    ) -> ToolResult:
        """List the members of a channel."""
        del teamId  # sample backend ignores teamId
        members = _CHANNEL_MEMBERS.get(channelId, [])
        return _wiq_result({"members": [dict(m) for m in members[:top]]})

    @backend.tool
    def SendMessageToChat(
        chatId: str,
        content: str,
        contentType: str | None = None,
        importance: str | None = None,
        mentions: str | None = None,
        adaptiveCardJson: str | None = None,
    ) -> ToolResult:
        """Send a message to a chat."""
        del content, contentType, importance, mentions, adaptiveCardJson
        return _wiq_result(
            {
                "id": _SAMPLE_SENT_MESSAGE_ID,
                "chatId": chatId,
                "createdDateTime": _SAMPLE_SENT_DATETIME,
                "message": "Message sent successfully.",
            }
        )

    return backend


@pytest.fixture()
async def client_session():
    backend = _make_backend()
    async with Client(FastMCPTransport(backend)) as client:
        yield client


@pytest.mark.anyio
async def test_backend_list_tools(client_session: Client):
    tools = await client_session.list_tools()
    assert {t.name for t in tools} == {
        "ListTeams",
        "ListChannels",
        "ListChannelMembers",
        "SendMessageToChat",
    }


@pytest.mark.anyio
async def test_backend_list_teams(client_session: Client):
    """The sample backend mirrors the WorkIQ wire shape: no
    ``structured_content``, payload in ``content[0].text`` as escaped
    JSON, ``CorrelationId``/``TimeStamp`` diagnostics in ``content[1]``."""
    result = await client_session.call_tool("ListTeams", {})
    assert result.structured_content is None
    assert len(result.content) == 2
    block0, block1 = result.content
    assert isinstance(block0, TextContent)
    assert isinstance(block1, TextContent)
    assert json.loads(block0.text) == {"teams": _SAMPLE_TEAMS}
    assert block1.text.startswith("CorrelationId: ")
    # extract_structured_content papers over the two shapes.
    assert extract_structured_content(result) == {"teams": _SAMPLE_TEAMS}


@pytest.mark.anyio
async def test_backend_list_channel_members(client_session: Client):
    result = await client_session.call_tool(
        "ListChannelMembers",
        {"teamId": _SAMPLE_TEAMS[0]["id"], "channelId": _CHANNEL_GENERAL_ID},
    )
    assert result.structured_content is None
    assert extract_structured_content(result) == {
        "members": _CHANNEL_MEMBERS[_CHANNEL_GENERAL_ID]
    }


# ---------------------------------------------------------------------------
# fastmcp_proxy.load_config — parses + validates the multi-server config
# ---------------------------------------------------------------------------


def _write_config(tmp_path: Path, payload: dict) -> Path:
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(payload))
    return config_file


def test_load_config_minimal_http_server(tmp_path: Path):
    cfg = load_config(
        _write_config(
            tmp_path,
            {
                "mcpServers": {
                    "github": {
                        "type": "http",
                        "url": "https://example/mcp",
                    }
                }
            },
        )
    )
    assert set(cfg.keys()) == {"github"}
    assert cfg["github"]["type"] == "http"
    assert cfg["github"]["url"] == "https://example/mcp"
    # No msal block in config → no msal entry in the parsed meta.
    assert "msal" not in cfg["github"]


def test_load_config_multiple_servers(tmp_path: Path):
    cfg = load_config(
        _write_config(
            tmp_path,
            {
                "mcpServers": {
                    "github": {
                        "type": "http",
                        "url": "https://github/mcp",
                    },
                    "workiq": {
                        "type": "http",
                        "url": "https://workiq/mcp",
                    },
                }
            },
        )
    )
    assert set(cfg.keys()) == {"github", "workiq"}
    assert cfg["workiq"]["url"] == "https://workiq/mcp"


def test_load_config_msal_section_is_normalized(tmp_path: Path):
    cfg = load_config(
        _write_config(
            tmp_path,
            {
                "mcpServers": {
                    "workiq": {
                        "type": "http",
                        "url": "https://workiq/mcp",
                        "msal": {
                            "clientId": "cid",
                            "tenantId": "tid",
                            "scopes": ["https://api/.default"],
                            "callbackPort": 7777,
                        },
                    }
                }
            },
        )
    )
    assert cfg["workiq"]["msal"] == {
        "client_id": "cid",
        "tenant_id": "tid",
        "scopes": ["https://api/.default"],
        "callback_port": 7777,
    }


def test_load_config_msal_callback_port_defaults_to_8080(tmp_path: Path):
    cfg = load_config(
        _write_config(
            tmp_path,
            {
                "mcpServers": {
                    "workiq": {
                        "type": "http",
                        "url": "https://workiq/mcp",
                        "msal": {"clientId": "cid", "tenantId": "tid"},
                    }
                }
            },
        )
    )
    assert cfg["workiq"]["msal"]["callback_port"] == 8080
    # scopes was not provided → comes through as None
    assert cfg["workiq"]["msal"]["scopes"] is None


def test_load_config_oauth_section_is_normalized(tmp_path: Path):
    cfg = load_config(
        _write_config(
            tmp_path,
            {
                "mcpServers": {
                    "github": {
                        "type": "http",
                        "url": "https://api.githubcopilot.com/mcp/",
                        "oauth": {
                            "clientId": "cid",
                            "clientSecret": "csecret",
                            "scopes": ["repo", "read:user"],
                            "callbackPort": 8765,
                        },
                    }
                }
            },
        )
    )
    assert cfg["github"]["oauth"] == {
        "client_id": "cid",
        "client_secret": "csecret",
        "scopes": ["repo", "read:user"],
        "callback_port": 8765,
    }


def test_load_config_oauth_minimal_fields(tmp_path: Path):
    # Empty oauth block is valid: every field is optional and translates to
    # full Dynamic Client Registration with FastMCP defaults.
    cfg = load_config(
        _write_config(
            tmp_path,
            {
                "mcpServers": {
                    "github": {
                        "type": "http",
                        "url": "https://api.githubcopilot.com/mcp/",
                        "oauth": {},
                    }
                }
            },
        )
    )
    assert cfg["github"]["oauth"] == {
        "client_id": None,
        "client_secret": None,
        "scopes": None,
        "callback_port": None,
    }


def test_load_config_oauth_dcr_only_scopes(tmp_path: Path):
    # A common DCR setup: no pre-registered client, just request scopes.
    cfg = load_config(
        _write_config(
            tmp_path,
            {
                "mcpServers": {
                    "dcr-server": {
                        "type": "http",
                        "url": "https://dcr/mcp/",
                        "oauth": {"scopes": ["read"]},
                    }
                }
            },
        )
    )
    assert cfg["dcr-server"]["oauth"]["client_id"] is None
    assert cfg["dcr-server"]["oauth"]["scopes"] == ["read"]


def test_load_config_rejects_msal_and_oauth_together(tmp_path: Path):
    with pytest.raises(ValueError, match="mutually exclusive"):
        load_config(
            _write_config(
                tmp_path,
                {
                    "mcpServers": {
                        "weird": {
                            "type": "http",
                            "url": "https://example/mcp/",
                            "msal": {"clientId": "c", "tenantId": "t"},
                            "oauth": {"clientId": "c"},
                        }
                    }
                },
            )
        )


def test_load_config_headers_pass_through(tmp_path: Path):
    cfg = load_config(
        _write_config(
            tmp_path,
            {
                "mcpServers": {
                    "github": {
                        "type": "http",
                        "url": "https://api.githubcopilot.com/mcp/",
                        "headers": {
                            "Authorization": "Bearer ghp_xxx",
                            "X-Custom": "value",
                        },
                    }
                }
            },
        )
    )
    assert cfg["github"]["headers"] == {
        "Authorization": "Bearer ghp_xxx",
        "X-Custom": "value",
    }


def test_load_config_headers_absent_means_no_headers_key(tmp_path: Path):
    cfg = load_config(
        _write_config(
            tmp_path,
            {
                "mcpServers": {
                    "github": {
                        "type": "http",
                        "url": "https://api.githubcopilot.com/mcp/",
                    }
                }
            },
        )
    )
    assert "headers" not in cfg["github"]


def test_load_config_rejects_non_object_headers(tmp_path: Path):
    with pytest.raises(ValueError, match="'headers' field must be an object"):
        load_config(
            _write_config(
                tmp_path,
                {
                    "mcpServers": {
                        "github": {
                            "type": "http",
                            "url": "https://api.githubcopilot.com/mcp/",
                            "headers": ["Authorization: Bearer xxx"],
                        }
                    }
                },
            )
        )


def test_load_config_rejects_non_string_header_value(tmp_path: Path):
    with pytest.raises(ValueError, match="header 'Authorization' must be a string"):
        load_config(
            _write_config(
                tmp_path,
                {
                    "mcpServers": {
                        "github": {
                            "type": "http",
                            "url": "https://api.githubcopilot.com/mcp/",
                            "headers": {"Authorization": 123},
                        }
                    }
                },
            )
        )


def test_load_config_requires_mcp_servers_key(tmp_path: Path):
    with pytest.raises(ValueError, match="mcpServers"):
        load_config(_write_config(tmp_path, {}))


def test_load_config_accepts_stdio_server(tmp_path: Path):
    cfg = load_config(
        _write_config(
            tmp_path,
            {
                "mcpServers": {
                    "workiq": {
                        "type": "stdio",
                        "command": "/opt/workiq-mock",
                        "args": ["serve", "--port", "8123"],
                        "env": {"WORKIQ_MOCK_DISCOVERY_SOURCE": "local"},
                        "cwd": "/opt",
                    }
                }
            },
        )
    )
    assert cfg["workiq"] == {
        "type": "stdio",
        "command": "/opt/workiq-mock",
        "args": ["serve", "--port", "8123"],
        "env": {"WORKIQ_MOCK_DISCOVERY_SOURCE": "local"},
        "cwd": "/opt",
    }


@pytest.mark.parametrize(
    ("update", "message"),
    [
        ({"command": ""}, "command"),
        ({"args": [1]}, "args"),
        ({"env": {"A": 1}}, "env"),
        ({"cwd": 1}, "cwd"),
        ({"url": "http://127.0.0.1"}, "does not support"),
    ],
)
def test_load_config_rejects_invalid_stdio_server(
    tmp_path: Path, update: dict[str, Any], message: str
):
    server = {"type": "stdio", "command": "workiq-mock"}
    server.update(update)
    with pytest.raises(ValueError, match=message):
        load_config(
            _write_config(
                tmp_path,
                {"mcpServers": {"workiq": server}},
            )
        )


def test_load_config_rejects_unsupported_type(tmp_path: Path):
    with pytest.raises(ValueError, match="Unsupported server type"):
        load_config(
            _write_config(
                tmp_path,
                {"mcpServers": {"socket_server": {"type": "socket"}}},
            )
        )


def test_load_config_requires_url(tmp_path: Path):
    with pytest.raises(ValueError, match="missing required 'url'"):
        load_config(
            _write_config(
                tmp_path,
                {"mcpServers": {"github": {"type": "http"}}},
            )
        )


def test_load_config_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "does-not-exist.json")


def test_load_config_invalid_json(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    with pytest.raises(json.JSONDecodeError):
        load_config(bad)


# ---------------------------------------------------------------------------
# msal_auth: token cache helpers
# ---------------------------------------------------------------------------


def test_load_msal_cache_missing_file_returns_empty_cache(tmp_path: Path):
    cache = load_msal_cache(tmp_path / "does-not-exist.json")
    # An untouched SerializableTokenCache serializes to an empty JSON object.
    assert cache.serialize() in ("", "{}")


def test_load_msal_cache_ignores_invalid_json(tmp_path: Path):
    bad = tmp_path / "cache.json"
    bad.write_text("{not json")
    cache = load_msal_cache(bad)
    assert cache.serialize() in ("", "{}")


def test_save_msal_cache_writes_when_state_changed(tmp_path: Path):
    target = tmp_path / "nested" / "cache.json"

    class DummyCache:
        has_state_changed = True

        def serialize(self) -> str:
            return '{"hello": "world"}'

    save_msal_cache(DummyCache(), target)
    assert target.exists()
    assert json.loads(target.read_text()) == {"hello": "world"}


def test_save_msal_cache_noop_when_unchanged(tmp_path: Path):
    target = tmp_path / "cache.json"

    class DummyCache:
        has_state_changed = False

        def serialize(self) -> str:  # pragma: no cover - should not be called
            raise AssertionError("serialize() must not be called when unchanged")

    save_msal_cache(DummyCache(), target)
    assert not target.exists()


# ---------------------------------------------------------------------------
# msal_auth.MSALBearerAuth: injects a Bearer header using the acquired token
# ---------------------------------------------------------------------------


def test_msal_bearer_auth_injects_bearer_header(tmp_path: Path, monkeypatch):
    captured: dict = {}

    def fake_acquire(**kwargs):
        captured.update(kwargs)
        return "fake-token-xyz"

    monkeypatch.setattr(msal_auth, "acquire_msal_token", fake_acquire)

    auth = MSALBearerAuth(
        token_cache_file=tmp_path / "cache.json",
        scopes=["https://api/.default"],
        client_id="cid",
        tenant_id="tid",
        callback_port=8080,
    )

    # acquire_msal_token was called with the snake_case fields the gateway uses.
    assert captured["client_id"] == "cid"
    assert captured["tenant_id"] == "tid"
    assert captured["scopes"] == ["https://api/.default"]
    assert captured["callback_port"] == 8080
    assert captured["token_cache_file"] == tmp_path / "cache.json"

    # auth_flow yields a request with the Bearer header set.
    request = httpx.Request("GET", "https://example/mcp")
    flow = auth.auth_flow(request)
    sent = next(flow)
    assert sent.headers["Authorization"] == "Bearer fake-token-xyz"


# ---------------------------------------------------------------------------
# fastmcp_proxy.MCPGateway: construction with the upstream auth flow stubbed
# ---------------------------------------------------------------------------


def _stub_acquire_token(monkeypatch) -> None:
    # MCPGateway → MSALBearerAuth → acquire_msal_token (in msal_auth).
    monkeypatch.setattr(msal_auth, "acquire_msal_token", lambda **kw: "stub-token")


def _server_with_msal(url: str) -> dict:
    return {
        "type": "http",
        "url": url,
        "msal": {
            "clientId": "cid",
            "tenantId": "tid",
            "scopes": ["https://api/.default"],
            "callbackPort": 8080,
        },
    }


def _server_with_oauth(url: str) -> dict:
    return {
        "type": "http",
        "url": url,
        "oauth": {
            "clientId": "github-oauth-cid",
            "clientSecret": "github-oauth-secret",
            "scopes": ["repo"],
            "callbackPort": 8765,
        },
    }


def _server_no_auth(url: str) -> dict:
    return {"type": "http", "url": url}


def _gateway_config(servers: dict) -> dict:
    return {"mcpServers": servers}


def test_mcp_gateway_builds_one_proxy_per_server(tmp_path: Path, monkeypatch):
    _stub_acquire_token(monkeypatch)
    cfg_path = _write_config(
        tmp_path,
        _gateway_config(
            {
                "github": _server_with_msal("https://github/mcp"),
                "workiq": _server_no_auth("https://workiq/mcp"),
            }
        ),
    )
    gw = MCPGateway(config_path=cfg_path, token_cache_path=tmp_path / "cache.json")

    assert set(gw._proxies.keys()) == {"github", "workiq"}
    assert all(isinstance(p, FastMCP) for p in gw._proxies.values())
    # Each proxy is named after its server_id so clients can tell them apart.
    assert gw._proxies["github"].name == "github"
    assert gw._proxies["workiq"].name == "workiq"


def test_mcp_gateway_build_proxy_skips_msal_when_absent(tmp_path: Path, monkeypatch):
    called = False

    def boom(**kw):  # pragma: no cover - should never be called
        nonlocal called
        called = True
        raise AssertionError(
            "acquire_msal_token must not be called for unauthed server"
        )

    monkeypatch.setattr(msal_auth, "acquire_msal_token", boom)

    cfg_path = _write_config(
        tmp_path,
        _gateway_config({"public": _server_no_auth("https://public/mcp")}),
    )
    gw = MCPGateway(config_path=cfg_path, token_cache_path=tmp_path / "cache.json")
    assert "public" in gw._proxies
    assert called is False


def test_mcp_gateway_build_proxy_uses_oauth_with_static_credentials(
    tmp_path: Path, monkeypatch
):
    """OAuth servers must skip Dynamic Client Registration by passing the
    pre-registered client_id/client_secret straight into fastmcp's OAuth.

    Plain ``auth="oauth"`` (which triggers DCR) breaks against providers like
    GitHub that 404 on the registration endpoint.
    """
    from fastmcp.client.auth import OAuth

    captured: dict = {}
    real_oauth_init = OAuth.__init__

    def spy_init(self, *args, **kwargs):
        captured.update(kwargs)
        return real_oauth_init(self, *args, **kwargs)

    monkeypatch.setattr(OAuth, "__init__", spy_init)

    cfg_path = _write_config(
        tmp_path,
        _gateway_config(
            {"github": _server_with_oauth("https://api.githubcopilot.com/mcp/")}
        ),
    )
    gw = MCPGateway(config_path=cfg_path, token_cache_path=tmp_path / "cache.json")

    assert captured["client_id"] == "github-oauth-cid"
    assert captured["client_secret"] == "github-oauth-secret"
    assert captured["scopes"] == ["repo"]
    assert captured["callback_port"] == 8765
    assert captured["mcp_url"] == "https://api.githubcopilot.com/mcp/"
    assert "github" in gw._proxies


def test_mcp_gateway_build_proxy_uses_oauth_with_dynamic_client_registration(
    tmp_path: Path, monkeypatch
):
    """Servers whose oauth block omits ``clientId`` must still construct an
    ``OAuth`` instance — fastmcp's OAuth treats ``client_id=None`` as a signal
    to perform Dynamic Client Registration against the upstream server.
    """
    from fastmcp.client.auth import OAuth

    captured: dict = {}
    real_oauth_init = OAuth.__init__

    def spy_init(self, *args, **kwargs):
        captured.update(kwargs)
        return real_oauth_init(self, *args, **kwargs)

    monkeypatch.setattr(OAuth, "__init__", spy_init)

    cfg_path = _write_config(
        tmp_path,
        _gateway_config(
            {
                "dcr-server": {
                    "type": "http",
                    "url": "https://dcr/mcp/",
                    "oauth": {"scopes": ["read"]},
                }
            }
        ),
    )
    gw = MCPGateway(config_path=cfg_path, token_cache_path=tmp_path / "cache.json")

    assert captured["client_id"] is None
    assert captured["client_secret"] is None
    assert captured["scopes"] == ["read"]
    assert captured["callback_port"] is None
    assert captured["mcp_url"] == "https://dcr/mcp/"
    assert "dcr-server" in gw._proxies


def test_mcp_gateway_build_proxy_forwards_headers_to_transport(
    tmp_path: Path, monkeypatch
):
    """Static headers from the config must be forwarded into the upstream
    ``StreamableHttpTransport`` so they appear on every proxied request — this
    is what enables PAT auth for providers like GitHub.
    """
    from fastmcp.client.transports import StreamableHttpTransport

    captured: dict = {}
    real_init = StreamableHttpTransport.__init__

    def spy_init(self, *args, **kwargs):
        captured.update(kwargs)
        return real_init(self, *args, **kwargs)

    monkeypatch.setattr(StreamableHttpTransport, "__init__", spy_init)

    headers = {"Authorization": "Bearer ghp_xxx", "X-Custom": "yes"}
    cfg_path = _write_config(
        tmp_path,
        _gateway_config(
            {
                "github": {
                    "type": "http",
                    "url": "https://api.githubcopilot.com/mcp/",
                    "headers": headers,
                }
            }
        ),
    )
    gw = MCPGateway(config_path=cfg_path, token_cache_path=tmp_path / "cache.json")

    assert captured["headers"] == headers
    assert captured["url"] == "https://api.githubcopilot.com/mcp/"
    assert "github" in gw._proxies


def test_mcp_gateway_build_proxy_no_headers_when_unconfigured(
    tmp_path: Path, monkeypatch
):
    from fastmcp.client.transports import StreamableHttpTransport

    captured: dict = {}
    real_init = StreamableHttpTransport.__init__

    def spy_init(self, *args, **kwargs):
        captured.update(kwargs)
        return real_init(self, *args, **kwargs)

    monkeypatch.setattr(StreamableHttpTransport, "__init__", spy_init)

    cfg_path = _write_config(
        tmp_path,
        _gateway_config({"public": _server_no_auth("https://public/mcp")}),
    )
    MCPGateway(config_path=cfg_path, token_cache_path=tmp_path / "cache.json")

    # When the config has no headers block, the transport gets headers=None.
    assert captured.get("headers") is None


def test_mcp_gateway_asgi_app_mounts_each_proxy(tmp_path: Path, monkeypatch):
    _stub_acquire_token(monkeypatch)
    cfg_path = _write_config(
        tmp_path,
        _gateway_config(
            {
                "github": _server_with_msal("https://github/mcp"),
                "workiq": _server_no_auth("https://workiq/mcp"),
            }
        ),
    )
    gw = MCPGateway(config_path=cfg_path, token_cache_path=tmp_path / "cache.json")
    app = gw.asgi_app()

    assert isinstance(app, Starlette)
    mounts = [r for r in app.routes if isinstance(r, Mount)]
    paths = {m.path for m in mounts}
    assert paths == {"/mcp/github", "/mcp/workiq"}


def test_mcp_gateway_add_middleware_targets_named_proxy(tmp_path: Path, monkeypatch):
    _stub_acquire_token(monkeypatch)
    cfg_path = _write_config(
        tmp_path,
        _gateway_config(
            {
                "github": _server_with_msal("https://github/mcp"),
                "workiq": _server_no_auth("https://workiq/mcp"),
            }
        ),
    )
    gw = MCPGateway(config_path=cfg_path, token_cache_path=tmp_path / "cache.json")

    class MarkerMiddleware(Middleware):
        pass

    mw = MarkerMiddleware()
    gw.add_middleware("github", mw)

    # The middleware is attached to the github proxy only.
    assert mw in gw._proxies["github"].middleware
    assert mw not in gw._proxies["workiq"].middleware


def test_mcp_gateway_add_middleware_unknown_server_raises(tmp_path: Path, monkeypatch):
    _stub_acquire_token(monkeypatch)
    cfg_path = _write_config(
        tmp_path,
        _gateway_config({"github": _server_with_msal("https://github/mcp")}),
    )
    gw = MCPGateway(config_path=cfg_path, token_cache_path=tmp_path / "cache.json")

    class NoopMiddleware(Middleware):
        pass

    with pytest.raises(KeyError):
        gw.add_middleware("does-not-exist", NoopMiddleware())


# ---------------------------------------------------------------------------
# StripFastmcpMetaMiddleware — removes the FastMCP-injected ``fastmcp`` key
# from each tool's _meta on the wire. Sanity-checks the FastMCP injection
# first so the test breaks loudly if FastMCP ever changes the namespace.
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_fastmcp_injects_fastmcp_meta_by_default():
    """Pin FastMCP's current behavior: list_tools returns _meta['fastmcp'].

    If this ever fails, FastMCP changed the behavior and our middleware may
    no longer be necessary (or may need to target a different key).
    """
    backend = _make_backend()
    async with Client(FastMCPTransport(backend)) as client:
        tools = await client.list_tools()
    for t in tools:
        assert t.meta is not None
        assert "fastmcp" in t.meta


@pytest.mark.anyio
async def test_strip_fastmcp_meta_middleware_removes_fastmcp_key():
    backend = _make_backend()
    backend.add_middleware(StripFastmcpMetaMiddleware())
    async with Client(FastMCPTransport(backend)) as client:
        tools = await client.list_tools()
    for t in tools:
        # After the middleware runs, no tool should advertise ``fastmcp`` meta.
        assert not t.meta or "fastmcp" not in t.meta
        assert not t.meta or "_fastmcp" not in t.meta


@pytest.mark.anyio
async def test_strip_fastmcp_meta_middleware_preserves_other_meta():
    """Non-fastmcp meta entries must survive the strip."""
    backend = FastMCP("test-backend")

    @backend.tool(meta={"custom": "value"})
    def hello() -> str:
        return "hi"

    backend.add_middleware(StripFastmcpMetaMiddleware())
    async with Client(FastMCPTransport(backend)) as client:
        tools = await client.list_tools()
    assert tools[0].meta == {"custom": "value"}


def test_mcp_gateway_config_loads_strip_fastmcp_meta_middleware(
    tmp_path: Path, monkeypatch
):
    """The config-driven middleware loader must wire StripFastmcpMetaMiddleware
    onto the proxy when listed under the server's ``middleware`` block."""
    _stub_acquire_token(monkeypatch)
    cfg_path = _write_config(
        tmp_path,
        _gateway_config(
            {
                "github": {
                    "type": "http",
                    "url": "https://api.githubcopilot.com/mcp/",
                    "middleware": [{"type": "StripFastmcpMetaMiddleware"}],
                }
            }
        ),
    )
    gw = MCPGateway(config_path=cfg_path, token_cache_path=tmp_path / "cache.json")

    attached = gw._proxies["github"].middleware
    assert any(isinstance(m, StripFastmcpMetaMiddleware) for m in attached)


# ---------------------------------------------------------------------------
# MetaPrefixTranslationMiddleware — bidirectional _meta key prefix rewriting
# ---------------------------------------------------------------------------


def test_meta_prefix_translation_rejects_duplicate_proxy_values():
    """The proxy-side prefixes must be unique so the reverse direction
    (proxy → client) is unambiguous."""
    with pytest.raises(ValueError, match="unique"):
        MetaPrefixTranslationMiddleware(
            {"ifc/": "com.github.ifc/", "labels/": "com.github.ifc/"}
        )


@pytest.mark.anyio
async def test_meta_prefix_translation_rewrites_tool_listing_outbound():
    """Tool listings carrying a proxy_prefix in ``_meta`` are translated
    to the corresponding client_prefix before reaching the client."""
    backend = FastMCP("test-backend")

    @backend.tool(meta={"com.github.ifc/policy": "package policy\nallow := true"})
    def hello() -> str:
        return "hi"

    backend.add_middleware(MetaPrefixTranslationMiddleware({"ifc/": "com.github.ifc/"}))
    async with Client(FastMCPTransport(backend)) as client:
        tools = await client.list_tools()
    assert tools[0].meta is not None
    assert "ifc/policy" in tools[0].meta
    assert "com.github.ifc/policy" not in tools[0].meta
    assert tools[0].meta["ifc/policy"] == "package policy\nallow := true"


@pytest.mark.anyio
async def test_policy_middleware_does_not_advertise_policies():
    backend = FastMCP("test-backend")

    @backend.tool
    def hello() -> str:
        return "hi"

    backend.add_middleware(
        PolicyMiddleware(policies={"*": {"literal": "package policy"}})
    )
    async with Client(FastMCPTransport(backend)) as client:
        tools = await client.list_tools()

    assert "com.github.ifc/policy" not in (tools[0].meta or {})


@pytest.mark.anyio
async def test_meta_prefix_translation_rewrites_call_meta_inbound():
    """Tool calls whose ``_meta`` keys carry a client_prefix are rewritten
    to the corresponding proxy_prefix before the call is forwarded to
    the rest of the chain."""
    import mcp.types as mt
    from fastmcp.server.middleware import MiddlewareContext

    mw = MetaPrefixTranslationMiddleware({"ifc/": "com.github.ifc/"})
    params = mt.CallToolRequestParams.model_validate(
        {
            "name": "T",
            "arguments": {},
            "_meta": {"ifc/labels": {"$": "L"}, "progressToken": "abc"},
        }
    )
    forwarded: dict[str, Any] = {}

    async def _next(ctx: MiddlewareContext[Any]) -> Any:
        forwarded["meta"] = dict(ctx.message.meta) if ctx.message.meta else {}

        class _Result:
            meta = None

        return _Result()

    ctx = MiddlewareContext(message=params, source="client", type="request")
    await mw.on_call_tool(ctx, _next)
    assert "com.github.ifc/labels" in forwarded["meta"]
    assert forwarded["meta"]["com.github.ifc/labels"] == {"$": "L"}
    assert "ifc/labels" not in forwarded["meta"]
    # Unmapped progressToken key is preserved verbatim.
    assert forwarded["meta"].get("progressToken") == "abc"


@pytest.mark.anyio
async def test_meta_prefix_translation_rewrites_call_result_outbound():
    """The ``_meta`` carried on a ToolResult flows back through the
    middleware with proxy_prefix → client_prefix rewriting applied."""
    import mcp.types as mt
    from fastmcp.server.middleware import MiddlewareContext

    mw = MetaPrefixTranslationMiddleware({"ifc/": "com.github.ifc/"})
    params = mt.CallToolRequestParams.model_validate({"name": "T", "arguments": {}})

    class _Result:
        meta: dict[str, Any] | None = {
            "com.github.ifc/labels": {"$": "L"},
            "other/k": 1,
        }

    async def _next(ctx: MiddlewareContext[Any]) -> Any:
        return _Result()

    ctx = MiddlewareContext(message=params, source="client", type="request")
    result = await mw.on_call_tool(ctx, _next)
    assert result.meta == {"ifc/labels": {"$": "L"}, "other/k": 1}


def test_meta_prefix_translation_unmapped_keys_untouched():
    """Keys whose prefix does not match any configured client_prefix /
    proxy_prefix pass through unchanged in both directions."""
    from middleware import _translate_meta_keys

    mw = MetaPrefixTranslationMiddleware({"ifc/": "com.github.ifc/"})
    # Outbound (proxy → client): only the proxy prefix is rewritten.
    out = _translate_meta_keys(
        {"com.github.ifc/policy": "p", "fastmcp": {"tags": []}, "other/k": 1},
        mw._proxy_to_client,
    )
    assert out == {"ifc/policy": "p", "fastmcp": {"tags": []}, "other/k": 1}
    # Inbound (client → proxy): symmetric.
    inb = _translate_meta_keys(
        {"ifc/labels": {"$": "L"}, "fastmcp": {"tags": []}, "other/k": 1},
        mw._client_to_proxy,
    )
    assert inb == {
        "com.github.ifc/labels": {"$": "L"},
        "fastmcp": {"tags": []},
        "other/k": 1,
    }


def test_meta_prefix_translation_longest_prefix_wins():
    """When two configured prefixes both match a key, the longer one is
    applied — single-shot rewrite, never re-translated."""
    from middleware import _translate_meta_keys

    mw = MetaPrefixTranslationMiddleware(
        {"ifc/": "com.github.ifc/", "ifc/v2/": "com.github.ifc/v2/"}
    )
    out = _translate_meta_keys(
        {"ifc/v2/labels": "x", "ifc/labels": "y"}, mw._client_to_proxy
    )
    assert out == {"com.github.ifc/v2/labels": "x", "com.github.ifc/labels": "y"}


def test_mcp_gateway_config_loads_meta_prefix_translation_middleware(
    tmp_path: Path, monkeypatch
):
    """The config-driven middleware loader must wire
    MetaPrefixTranslationMiddleware onto the proxy when listed under the
    server's ``middleware`` block."""
    _stub_acquire_token(monkeypatch)
    cfg_path = _write_config(
        tmp_path,
        _gateway_config(
            {
                "github": {
                    "type": "http",
                    "url": "https://api.githubcopilot.com/mcp/",
                    "middleware": [
                        {
                            "type": "MetaPrefixTranslationMiddleware",
                            "prefixMap": {"ifc/": "com.github.ifc/"},
                        }
                    ],
                }
            }
        ),
    )
    gw = MCPGateway(config_path=cfg_path, token_cache_path=tmp_path / "cache.json")

    attached = gw._proxies["github"].middleware
    matching = [m for m in attached if isinstance(m, MetaPrefixTranslationMiddleware)]
    assert len(matching) == 1
    # The dict was loaded into the middleware.
    assert matching[0]._client_to_proxy == [("ifc/", "com.github.ifc/")]


def test_mcp_gateway_config_loads_workiq_labelling_middleware(
    tmp_path: Path, monkeypatch
):
    """The config-driven middleware loader must wire WorkIQLabellingMiddleware
    onto the proxy when listed under the server's ``middleware`` block."""
    _stub_acquire_token(monkeypatch)
    cfg_path = _write_config(
        tmp_path,
        _gateway_config(
            {
                "workiq": {
                    "type": "http",
                    "url": "https://workiq/mcp",
                    "msal": {
                        "clientId": "cid",
                        "tenantId": "tid",
                        "scopes": ["https://api/.default"],
                        "callbackPort": 8080,
                    },
                    "middleware": [{"type": "WorkIQLabellingMiddleware"}],
                }
            }
        ),
    )
    gw = MCPGateway(config_path=cfg_path, token_cache_path=tmp_path / "cache.json")

    attached = gw._proxies["workiq"].middleware
    assert any(isinstance(m, WorkIQLabellingMiddleware) for m in attached)


@pytest.mark.anyio
async def test_stdio_proxy_lists_calls_and_stops_child(tmp_path: Path):
    pid_path = tmp_path / "stdio.pid"
    cfg_path = _write_config(
        tmp_path,
        _gateway_config(
            {
                "fixture": {
                    "type": "stdio",
                    "command": sys.executable,
                    "args": [
                        str(Path(__file__).parent / "fixtures" / "stdio_server.py")
                    ],
                    "env": {
                        "FIDES_STDIO_PID_PATH": str(pid_path),
                        "FIDES_STDIO_MARKER": "configured",
                    },
                    "cwd": str(tmp_path),
                }
            }
        ),
    )
    gateway = MCPGateway(
        config_path=cfg_path,
        token_cache_path=tmp_path / "cache.json",
    )
    app = gateway.asgi_app()

    async with app.router.lifespan_context(app):
        async with Client(FastMCPTransport(gateway._proxies["fixture"])) as client:
            tools = await client.list_tools()
            assert {tool.name for tool in tools} == {
                "eval_policy",
                "inspect_runtime",
            }
            result = await client.call_tool("inspect_runtime", {"value": "hello"})
            payload = extract_structured_content(result)
            assert payload == {
                "cwd": str(tmp_path),
                "marker": "configured",
                "value": "hello",
            }
            pid = int(pid_path.read_text())
            os.kill(pid, 0)

    for _ in range(100):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        await asyncio.sleep(0.05)
    else:
        pytest.fail(f"stdio child process {pid} was not stopped")


def test_mcp_gateway_config_loads_github_labelling_middleware(tmp_path: Path):
    cfg_path = _write_config(
        tmp_path,
        _gateway_config(
            {
                "github": {
                    "type": "http",
                    "url": "https://github/mcp",
                    "middleware": [{"type": "GitHubLabellingMiddleware"}],
                }
            }
        ),
    )
    gw = MCPGateway(config_path=cfg_path, token_cache_path=tmp_path / "cache.json")

    attached = gw._proxies["github"].middleware
    assert any(isinstance(m, GitHubLabellingMiddleware) for m in attached)


# ---------------------------------------------------------------------------
# OutputSchemaMiddleware — injects per-tool outputSchema on tools/list,
# parses + validates unstructured tools/call results into structuredContent.
# ---------------------------------------------------------------------------


import jsonschema as _jsonschema
from fastmcp.server.middleware import MiddlewareContext as _MWCtx
from fastmcp.tools.base import ToolResult as _ToolResult
from mcp.types import CallToolRequestParams as _CallParams, TextContent as _TextContent


def _ctx(name: str) -> _MWCtx:
    return _MWCtx(message=_CallParams(name=name, arguments={}))


def _make_call_next(result: _ToolResult):
    async def call_next(_ctx):
        return result

    return call_next


# JSON schema describing the shape of the ListTeams payload returned by
# ``_make_backend``'s ``ListTeams`` tool (i.e. ``{"teams": _SAMPLE_TEAMS}``).
_TEAMS_SCHEMA = {
    "type": "object",
    "properties": {
        "teams": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "displayName": {"type": "string"},
                    "description": {"type": "string"},
                    "webUrl": {"type": ["string", "null"]},
                },
                "required": ["id", "displayName", "description", "webUrl"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["teams"],
    "additionalProperties": False,
}


@pytest.mark.anyio
async def test_output_schema_middleware_injects_schema_on_list_tools():
    backend = FastMCP("test-backend")

    @backend.tool(output_schema=None)
    def ListTeams() -> dict:
        return {"teams": [dict(t) for t in _SAMPLE_TEAMS]}

    backend.add_middleware(OutputSchemaMiddleware(schemas={"ListTeams": _TEAMS_SCHEMA}))
    async with Client(FastMCPTransport(backend)) as client:
        tools = await client.list_tools()
    assert tools[0].name == "ListTeams"
    assert tools[0].outputSchema == _TEAMS_SCHEMA


@pytest.mark.anyio
async def test_output_schema_middleware_preserves_upstream_schema():
    """Upstream-declared outputSchema must win over the configured one."""
    backend = FastMCP("test-backend")
    upstream_schema = {"type": "object", "properties": {"x": {"type": "integer"}}}

    @backend.tool(output_schema=upstream_schema)
    def Echo() -> dict:
        return {"x": 1}

    other_schema = {"type": "object", "properties": {"y": {"type": "string"}}}
    backend.add_middleware(OutputSchemaMiddleware(schemas={"Echo": other_schema}))
    async with Client(FastMCPTransport(backend)) as client:
        tools = await client.list_tools()
    assert tools[0].outputSchema == upstream_schema


@pytest.mark.anyio
async def test_output_schema_middleware_passthrough_when_no_config_for_tool():
    mw = OutputSchemaMiddleware(schemas={"OtherTool": _TEAMS_SCHEMA})
    original = _ToolResult(content=[_TextContent(type="text", text="hello")])
    out = await mw.on_call_tool(_ctx("ListTeams"), _make_call_next(original))
    assert out is original


@pytest.mark.anyio
async def test_output_schema_middleware_passthrough_when_upstream_structured():
    """If upstream already returned structuredContent, trust it (no double-validate)."""
    mw = OutputSchemaMiddleware(schemas={"ListTeams": _TEAMS_SCHEMA})
    # Note: this structured content does NOT match the configured schema, but
    # the middleware should not validate it because upstream produced it.
    original = _ToolResult(
        content=[_TextContent(type="text", text='{"bogus": true}')],
        structured_content={"bogus": True},
    )
    out = await mw.on_call_tool(_ctx("ListTeams"), _make_call_next(original))
    assert out is original


@pytest.mark.anyio
async def test_output_schema_middleware_parses_and_validates_unstructured_json():
    mw = OutputSchemaMiddleware(schemas={"ListTeams": _TEAMS_SCHEMA})
    payload = {"teams": [dict(t) for t in _SAMPLE_TEAMS]}
    raw = _ToolResult(content=[_TextContent(type="text", text=json.dumps(payload))])
    out = await mw.on_call_tool(_ctx("ListTeams"), _make_call_next(raw))
    assert out.structured_content == payload
    # content is replaced with a single canonical JSON text block.
    assert len(out.content) == 1
    assert isinstance(out.content[0], _TextContent)
    assert json.loads(out.content[0].text) == payload


@pytest.mark.anyio
async def test_output_schema_middleware_rejects_schema_violation():
    mw = OutputSchemaMiddleware(schemas={"ListTeams": _TEAMS_SCHEMA})
    # Drop the required "id" field from each team to trigger a validation error.
    bad = {"teams": [{k: v for k, v in t.items() if k != "id"} for t in _SAMPLE_TEAMS]}
    raw = _ToolResult(content=[_TextContent(type="text", text=json.dumps(bad))])
    with pytest.raises(_jsonschema.ValidationError):
        await mw.on_call_tool(_ctx("ListTeams"), _make_call_next(raw))


@pytest.mark.anyio
async def test_output_schema_middleware_rejects_non_json_text():
    mw = OutputSchemaMiddleware(schemas={"ListTeams": _TEAMS_SCHEMA})
    raw = _ToolResult(content=[_TextContent(type="text", text="not json")])
    with pytest.raises(ValueError, match="not valid JSON"):
        await mw.on_call_tool(_ctx("ListTeams"), _make_call_next(raw))


@pytest.mark.anyio
async def test_output_schema_middleware_ignores_extra_text_blocks():
    """Only ``content[0]`` is parsed as the structured payload; any further
    blocks are treated as diagnostics and silently ignored (matches
    :func:`mcp_result.extract_structured_content` and real WorkIQ-style
    upstreams whose ``content[1:]`` carries ``CorrelationId``/timestamp
    text)."""
    mw = OutputSchemaMiddleware(schemas={"ListTeams": _TEAMS_SCHEMA})
    payload = {"teams": [dict(t) for t in _SAMPLE_TEAMS]}
    raw = _ToolResult(
        content=[
            _TextContent(type="text", text=json.dumps(payload)),
            _TextContent(type="text", text="extra"),
        ]
    )
    out = await mw.on_call_tool(_ctx("ListTeams"), _make_call_next(raw))
    assert out.structured_content == payload
    # Canonical replacement drops the diagnostic block(s) entirely.
    assert len(out.content) == 1
    assert isinstance(out.content[0], _TextContent)
    assert json.loads(out.content[0].text) == payload


@pytest.mark.anyio
async def test_output_schema_middleware_ignores_trailing_correlation_id_block():
    """Microsoft Graph-style upstreams append a ``CorrelationId: <guid>``
    diagnostic block after the JSON payload; it must not derail parsing."""
    mw = OutputSchemaMiddleware(schemas={"ListTeams": _TEAMS_SCHEMA})
    payload = {"teams": [dict(t) for t in _SAMPLE_TEAMS]}
    raw = _ToolResult(
        content=[
            _TextContent(type="text", text=json.dumps(payload)),
            _TextContent(
                type="text",
                text="CorrelationId: 12345678-1234-1234-1234-123456789abc",
            ),
        ]
    )
    out = await mw.on_call_tool(_ctx("ListTeams"), _make_call_next(raw))
    assert out.structured_content == payload
    # Canonical replacement drops the diagnostic block entirely.
    assert len(out.content) == 1
    assert isinstance(out.content[0], _TextContent)
    assert json.loads(out.content[0].text) == payload


def test_output_schema_middleware_rejects_invalid_schema_at_construction():
    with pytest.raises(ValueError, match="Invalid outputSchema"):
        OutputSchemaMiddleware(schemas={"BadTool": {"type": "not-a-real-type"}})


def test_mcp_gateway_config_loads_output_schema_middleware(tmp_path: Path, monkeypatch):
    """The config-driven middleware loader must wire OutputSchemaMiddleware
    onto the proxy when listed under the server's ``middleware`` block."""
    _stub_acquire_token(monkeypatch)
    cfg_path = _write_config(
        tmp_path,
        _gateway_config(
            {
                "workiq": {
                    "type": "http",
                    "url": "https://workiq/mcp",
                    "middleware": [
                        {
                            "type": "OutputSchemaMiddleware",
                            "outputSchemas": {"ListTeams": _TEAMS_SCHEMA},
                        }
                    ],
                }
            }
        ),
    )
    gw = MCPGateway(config_path=cfg_path, token_cache_path=tmp_path / "cache.json")
    attached = gw._proxies["workiq"].middleware
    matching = [m for m in attached if isinstance(m, OutputSchemaMiddleware)]
    assert len(matching) == 1
    assert matching[0].schemas == {"ListTeams": _TEAMS_SCHEMA}


# ---------------------------------------------------------------------------
# eval_policy — _meta-based labelled policy evaluation
# ---------------------------------------------------------------------------


from policy_engine import (
    IFC_LABELS_META_PREFIX,
    LabeledMeta as _LabeledMeta,
    LabeledToolCallParams as _LabeledToolCallParams,
    _jsonpath_normalize,
    _parse_jsonpath_key,
    eval_policy,
    _make_label_extension,
)


def test_parse_jsonpath_key_accepts_singular_forms():
    """Storage-side keys are RFC 9535 JSONPath. Both dot-shorthand and
    bracket-quoted name selectors are accepted; both normalize to the
    Normalized Path form (single-quoted brackets)."""
    assert _parse_jsonpath_key("$") == []
    assert _parse_jsonpath_key("$['name']") == ["name"]
    assert _parse_jsonpath_key("$.name") == ["name"]
    assert _parse_jsonpath_key("$['arguments']['foo']") == ["arguments", "foo"]
    assert _parse_jsonpath_key("$.arguments.foo") == ["arguments", "foo"]
    # Mixed shorthand + bracket access.
    assert _parse_jsonpath_key("$.arguments['foo']['bar']") == [
        "arguments",
        "foo",
        "bar",
    ]
    # Integer index selectors.
    assert _parse_jsonpath_key("$['arguments']['items'][0]") == [
        "arguments",
        "items",
        0,
    ]
    assert _parse_jsonpath_key("$['arguments']['items'][0]['v']") == [
        "arguments",
        "items",
        0,
        "v",
    ]


def test_parse_jsonpath_key_rejects_non_singular_queries():
    """Wildcards, descendants, slices, filters, and multi-selector
    segments do not identify a single node and are rejected outright."""
    for s in [
        "$.*",
        "$..foo",
        "$['arguments'][*]",
        "$['arguments'][0:2]",
        "$['arguments'][0,1]",
        "$['arguments'][?@.x>1]",
    ]:
        with pytest.raises(ValueError, match="singular JSONPath"):
            _parse_jsonpath_key(s)


def test_parse_jsonpath_key_rejects_syntax_errors():
    """Non-JSONPath strings (e.g. missing ``$`` root) are rejected with
    the library's syntax error wrapped as a ``ValueError``."""
    with pytest.raises(ValueError, match="Invalid JSONPath key"):
        _parse_jsonpath_key("arguments.foo")  # no $ root
    with pytest.raises(ValueError, match="Invalid JSONPath key"):
        _parse_jsonpath_key("")
    with pytest.raises(ValueError, match="Invalid JSONPath key"):
        _parse_jsonpath_key("$['unterminated")


def test_jsonpath_normalize_formats_segments():
    """Segment lists round-trip through the Normalized Path form: single-
    quoted name selectors, unquoted integer index selectors, ``$`` for
    the empty (root) path."""
    assert _jsonpath_normalize([]) == "$"
    assert _jsonpath_normalize(["name"]) == "$['name']"
    assert _jsonpath_normalize(["arguments"]) == "$['arguments']"
    assert _jsonpath_normalize(["arguments", "foo"]) == "$['arguments']['foo']"
    assert (
        _jsonpath_normalize(["arguments", "foo", "bar"])
        == "$['arguments']['foo']['bar']"
    )
    assert (
        _jsonpath_normalize(["arguments", "items", 0]) == "$['arguments']['items'][0]"
    )
    assert (
        _jsonpath_normalize(["arguments", "items", 0, "v"])
        == "$['arguments']['items'][0]['v']"
    )


def test_label_extension_returns_explicit_label_when_present():
    labels = {
        "$['name']": {"integrity": "trusted", "confidentiality": []},
        "$['arguments']['x']": {
            "integrity": "untrusted",
            "confidentiality": ["alice"],
        },
    }
    call = {"name": "T", "arguments": {"x": "v"}}
    label = _make_label_extension(call, labels)
    assert label("$.arguments.x") == labels["$['arguments']['x']"]
    assert label("$['arguments']['x']") == labels["$['arguments']['x']"]
    # Dot-shorthand form.
    assert label("$.arguments['x']") == labels["$['arguments']['x']"]


def test_label_extension_accepts_non_canonical_label_keys():
    """Labels attached under any singular RFC 9535 JSONPath expression
    (e.g. dot-shorthand ``$.arguments.x`` or mixed shorthand+bracket
    forms) resolve as if attached under the canonical Normalized Path
    key."""
    expected = {"integrity": "untrusted", "confidentiality": ["alice"]}
    call = {"name": "T", "arguments": {"x": "v"}}
    for raw_key in ("$.arguments.x", "$['arguments'].x", "$.arguments['x']"):
        labels = {
            "$['name']": {"integrity": "trusted", "confidentiality": []},
            raw_key: expected,
        }
        label = _make_label_extension(call, labels)
        assert label("$.arguments.x") == expected
        assert label("$['arguments']['x']") == expected


def test_label_extension_rejects_conflicting_non_canonical_keys():
    """Two label entries that canonicalize to the same path with
    different values are flagged as a configuration error."""
    labels = {
        "$['name']": {"integrity": "trusted", "confidentiality": []},
        "$.arguments.x": {
            "integrity": "untrusted",
            "confidentiality": ["alice"],
        },
        "$['arguments']['x']": {
            "integrity": "untrusted",
            "confidentiality": ["bob"],
        },
    }
    call = {"name": "T", "arguments": {"x": "v"}}
    with pytest.raises(ValueError, match="duplicate label entries"):
        _make_label_extension(call, labels)


def test_label_extension_walks_up_to_nearest_ancestor():
    """When the queried node and its descendants carry no explicit labels,
    the lookup falls back to the nearest explicitly labelled ancestor."""
    labels = {
        "$['name']": {"integrity": "trusted", "confidentiality": []},
        "$['arguments']['x']": {
            "integrity": "untrusted",
            "confidentiality": ["alice"],
        },
    }
    call = {
        "name": "T",
        "arguments": {"x": {"nested": {"deep": "v"}}},
    }
    label = _make_label_extension(call, labels)
    assert (
        label("$['arguments']['x']['nested']['deep']") == labels["$['arguments']['x']"]
    )


def test_label_extension_falls_back_to_call_level_label():
    """Unlabelled paths fall back to the call-level label at '$' (i.e.
    ``input.call`` itself) when no node- or ancestor-level label exists."""
    labels = {
        "$": {"integrity": "trusted", "confidentiality": ["alice"]},
    }
    call = {"name": "T", "arguments": {"unlabeled": {"nested": "v"}}}
    label = _make_label_extension(call, labels)
    # name and arguments both fall back to '$'.
    assert label("$.name") == labels["$"]
    assert label("$.arguments") == labels["$"]
    # As do any deeper unlabelled descendants.
    assert label("$.arguments.unlabeled") == labels["$"]
    assert label("$['arguments']['unlabeled']['nested']") == labels["$"]
    # Direct query of the fallback path also works.
    assert label("$") == labels["$"]


def test_label_extension_fallback_does_not_upper_bound_name_or_arguments():
    """The call-level fallback at '$' is *not* required to upper-bound the
    labels of ``name`` or ``arguments``; it is just a fallback. Construction
    succeeds even when ``name``'s explicit label is incomparable to '$'."""
    labels = {
        # Fallback is trusted integrity, no recipients.
        "$": {"integrity": "trusted", "confidentiality": []},
        # name has a *lower* integrity label — not above '$'. That's fine:
        # '$' is a fallback, not an ancestor-with-well-formedness-check.
        "$['name']": {"integrity": "untrusted", "confidentiality": ["alice"]},
    }
    call = {"name": "T", "arguments": {"x": "v"}}
    # Must not raise.
    label = _make_label_extension(call, labels)
    assert label("$.name") == labels["$['name']"]
    # arguments has no explicit label and no labelled descendants — falls
    # back to '$' (rule 4), NOT to name (rule 4 was changed in this rev).
    assert label("$.arguments") == labels["$"]
    assert label("$.arguments.x") == labels["$"]


def test_label_extension_rejects_missing_coverage_for_arguments():
    """If neither ``arguments`` nor any of its descendants is labelled,
    and no '$' fallback is provided, construction must fail."""
    labels = {
        # Only ``name`` is covered.
        "$['name']": {"integrity": "trusted", "confidentiality": ["alice"]},
    }
    call = {"name": "T", "arguments": {"unlabeled": {"nested": "v"}}}
    with pytest.raises(ValueError, match=r"\$\['arguments'\].* has no effective label"):
        _make_label_extension(call, labels)


def test_label_extension_rejects_missing_coverage_for_name():
    """Symmetrically, ``name`` must be covered too."""
    labels = {
        # Only ``arguments`` (via descendant) is covered.
        "$['arguments']['x']": {
            "integrity": "trusted",
            "confidentiality": ["alice"],
        },
    }
    call = {"name": "T", "arguments": {"x": "v"}}
    with pytest.raises(ValueError, match=r"\$\['name'\].* has no effective label"):
        _make_label_extension(call, labels)


def test_label_extension_coverage_via_fallback_only():
    """Both ``name`` and ``arguments`` can be covered solely by the
    call-level fallback at '$' — no node-level labels required."""
    labels = {"$": {"integrity": "untrusted", "confidentiality": ["alice"]}}
    call = {"name": "T", "arguments": {"x": "v", "y": [1, 2, 3]}}
    # Must not raise.
    label = _make_label_extension(call, labels)
    assert label("$.name") == labels["$"]
    assert label("$.arguments") == labels["$"]
    assert label("$.arguments.x") == labels["$"]
    assert label("$.arguments.y[0]") == labels["$"]


def test_label_extension_rejects_non_string_argument():
    # Provide a '$' fallback so construction succeeds; the test is about
    # runtime rejection of non-string queries to the label extension.
    call = {"name": "T", "arguments": {}}
    label = _make_label_extension(
        call, {"$": {"integrity": "trusted", "confidentiality": []}}
    )
    with pytest.raises(ValueError, match="JSONPath string"):
        label({"not": "a string"})


def test_label_extension_container_is_lub_of_descendants():
    """A dict/array with no explicit label inherits the join of its
    descendants' effective labels."""
    labels = {
        "$['name']": {"integrity": "trusted", "confidentiality": []},
        "$['arguments']['body']['to']": {
            "integrity": "trusted",
            "confidentiality": ["alice"],
        },
        "$['arguments']['body']['cc']": {
            "integrity": "untrusted",
            "confidentiality": ["alice", "bob"],
        },
    }
    call = {
        "name": "Send",
        "arguments": {"body": {"to": "alice", "cc": ["alice", "bob"]}},
    }
    label = _make_label_extension(call, labels)
    # arguments['body'] has no explicit label; effective = lub of the two
    # children: integrity = min(trusted, untrusted) = untrusted, confidentiality =
    # intersection({alice}, {alice, bob}) = {alice}.
    body_label = label("$.arguments.body")
    assert body_label["integrity"] == "untrusted"
    assert set(body_label["confidentiality"]) == {"alice"}
    # ``arguments`` (the dict itself) propagates body's lub further up,
    # which is the only labelled subtree under it.
    args_label = label("$.arguments")
    assert args_label["integrity"] == "untrusted"
    assert set(args_label["confidentiality"]) == {"alice"}


def test_label_extension_array_label_is_lub_of_elements():
    """An array's label is the join over its element labels — and now
    individual elements are addressable via integer-bracket paths."""
    labels = {
        "$['name']": {"integrity": "trusted", "confidentiality": []},
        "$['arguments']['items']": {
            "integrity": "untrusted",
            "confidentiality": ["alice"],
        },
    }
    # Items is an array of dicts; the array itself carries an explicit
    # label that must dominate anything inside.
    call = {
        "name": "Send",
        "arguments": {"items": [{"who": "alice"}, {"who": "bob"}]},
    }
    label = _make_label_extension(call, labels)
    items_label = label("$.arguments.items")
    # Explicit label wins for the array itself.
    assert items_label == labels["$['arguments']['items']"]


def test_label_extension_addresses_individual_array_elements():
    """Array elements can carry their own explicit labels keyed by
    integer-bracket canonical paths."""
    labels = {
        "$['name']": {"integrity": "trusted", "confidentiality": []},
        "$['arguments']['items'][0]": {
            "integrity": "trusted",
            "confidentiality": ["alice"],
        },
        "$['arguments']['items'][1]": {
            "integrity": "untrusted",
            "confidentiality": ["alice", "bob"],
        },
    }
    call = {
        "name": "Send",
        "arguments": {"items": [{"who": "alice"}, {"who": "bob"}, {"who": "carol"}]},
    }
    label = _make_label_extension(call, labels)
    # Direct element access via integer index.
    assert label("$.arguments.items[0]") == labels["$['arguments']['items'][0]"]
    assert label("$['arguments']['items'][1]") == labels["$['arguments']['items'][1]"]
    # Field inside an explicitly labelled element inherits via descent
    # ancestor — its parent element carries the explicit label.
    assert label("$.arguments.items[0].who") == labels["$['arguments']['items'][0]"]
    # The array itself: lub of its two labelled elements (the third has
    # no label, so it contributes nothing). integrity = min(trusted, untrusted) =
    # untrusted; confidentiality = {alice} ∩ {alice, bob} = {alice}.
    arr_label = label("$.arguments.items")
    assert arr_label["integrity"] == "untrusted"
    assert set(arr_label["confidentiality"]) == {"alice"}
    # Unlabelled element falls back to its nearest ancestor — the array's
    # *implicit* (lub-derived) label is in the effective map, so that
    # wins over the name fallback.
    assert label("$.arguments.items[2]") == arr_label
    assert label("$.arguments.items[2].who") == arr_label


def test_label_extension_rejects_inconsistent_array_element_label():
    """Well-formedness applies to array containers too: an explicit label
    on the array must be ≥ the lub of its element labels."""
    labels = {
        "$['name']": {"integrity": "trusted", "confidentiality": []},
        # Array claims integrity=trusted...
        "$['arguments']['items']": {
            "integrity": "trusted",
            "confidentiality": ["alice"],
        },
        # ...but element 0 carries integrity=untrusted, which would force the
        # array's effective label to integrity=untrusted. Inconsistent.
        "$['arguments']['items'][0]": {
            "integrity": "untrusted",
            "confidentiality": ["alice"],
        },
    }
    call = {"name": "Send", "arguments": {"items": [{"who": "alice"}]}}
    with pytest.raises(ValueError, match="Inconsistent label"):
        _make_label_extension(call, labels)


def test_label_extension_explicit_overrides_descendants():
    """A container with both an explicit label and labelled descendants
    returns the explicit label (the well-formedness check guarantees
    the explicit is ≥ the descendants' lub)."""
    labels = {
        "$['name']": {"integrity": "trusted", "confidentiality": []},
        "$['arguments']['body']": {
            "integrity": "untrusted",
            "confidentiality": ["alice"],
        },
        "$['arguments']['body']['to']": {
            "integrity": "trusted",
            "confidentiality": ["alice", "bob"],
        },
    }
    call = {"name": "Send", "arguments": {"body": {"to": "alice"}}}
    label = _make_label_extension(call, labels)
    # Explicit at body wins; child's label is allowed because
    # join(body=untrusted/{alice}, child=trusted/{alice,bob}) == untrusted/{alice} == body.
    assert label("$.arguments.body") == labels["$['arguments']['body']"]


def test_label_extension_rejects_inconsistent_labelling():
    """Construction must fail if an explicit label is *below* the lub of
    its descendants' labels (i.e. the container claims a label tighter
    than what its contents demand)."""
    labels = {
        "$['name']": {"integrity": "trusted", "confidentiality": []},
        # body claims integrity=trusted but contains a child with integrity=untrusted.
        # Join would be untrusted, which != trusted — the container's label is below
        # its child's label in the lattice.
        "$['arguments']['body']": {
            "integrity": "trusted",
            "confidentiality": ["alice"],
        },
        "$['arguments']['body']['to']": {
            "integrity": "untrusted",
            "confidentiality": ["alice"],
        },
    }
    call = {"name": "Send", "arguments": {"body": {"to": "alice"}}}
    with pytest.raises(ValueError, match="Inconsistent label"):
        _make_label_extension(call, labels)


def test_labeled_meta_accepts_arbitrary_label_sets():
    """The Pydantic ``LabeledMeta`` model itself no longer enforces any
    specific entries — the stricter total-coverage requirement is enforced
    at label-extension construction time (which has access to the call
    tree). Pydantic-level validation only checks shapes."""
    # No "$['name']" key, no "$" key — accepted by Pydantic.
    m = _LabeledMeta(**{IFC_LABELS_META_PREFIX: {"$['arguments']['x']": IFCLabels()}})
    assert "$['arguments']['x']" in m.ifc_labels
    # Root key (the call-level fallback) is just another entry.
    m = _LabeledMeta(**{IFC_LABELS_META_PREFIX: {"$": IFCLabels()}})
    assert "$" in m.ifc_labels


from workiq_labeller import IFCLabels  # noqa: E402  (re-import for assertions above)


@pytest.mark.anyio
async def test_eval_policy_resolves_labels_via_extension():
    """End-to-end: a policy that calls ifc.label(...) gets back the configured
    labels per the ancestor-walk semantics."""
    call = {
        "name": "SendMessage",
        "arguments": {
            "to": "alice",
            "body": {"text": "hi", "tag": "internal"},
            "subject": "test",
        },
        "_meta": {
            IFC_LABELS_META_PREFIX: {
                "$['name']": {
                    "integrity": "trusted",
                    "confidentiality": ["fallback"],
                },
                "$['arguments']['to']": {
                    "integrity": "trusted",
                    "confidentiality": ["alice"],
                },
                "$['arguments']['body']": {
                    "integrity": "untrusted",
                    "confidentiality": ["body-principal"],
                },
            }
        },
    }
    policy = """
package policy

name_label := ifc.label("$.name")
to_label := ifc.label("$.arguments.to")
body_text_label := ifc.label("$.arguments.body.text")
subject_label := ifc.label("$.arguments.subject")
"""
    result = await eval_policy(call, policy)
    assert result["name_label"]["confidentiality"] == ["fallback"]
    # Explicit label.
    assert result["to_label"]["confidentiality"] == ["alice"]
    # Nearest ancestor (arguments["body"]) — text has no explicit label.
    assert result["body_text_label"]["confidentiality"] == ["body-principal"]
    # subject has no explicit label and no labelled descendants, but its
    # parent ``arguments`` carries an *implicit* label — the lub over its
    # labelled children: integrity=min(trusted, untrusted)=untrusted and confidentiality
    # = {alice} ∩ {body-principal} = ∅. That implicit ancestor label wins
    # over the name fallback.
    subject_label = result["subject_label"]
    assert subject_label["integrity"] == "untrusted"
    assert subject_label["confidentiality"] == []


@pytest.mark.anyio
async def test_eval_policy_tool_registered_and_callable():
    """Smoke test: the gateway-registered eval_policy tool resolves
    labels end-to-end through the FastMCP plumbing."""
    proxy = FastMCP("proxy")
    MCPGateway._register_eval_policy(proxy)

    policy = """
package policy

default allow := false

to_conf := ifc.label("$.arguments.to").confidentiality
allow if to_conf == ["alice"]

decision := {"allow": allow}
"""
    call_args = {
        "call": {
            "name": "SendMessage",
            "arguments": {"to": "alice"},
            "_meta": {
                IFC_LABELS_META_PREFIX: {
                    "$['name']": {"integrity": "trusted", "confidentiality": []},
                    "$['arguments']['to']": {
                        "integrity": "trusted",
                        "confidentiality": ["alice"],
                    },
                }
            },
        },
        "policy": policy,
    }

    async with Client(FastMCPTransport(proxy)) as client:
        tools = await client.list_tools()
        assert "eval_policy" in {t.name for t in tools}
        result = await client.call_tool("eval_policy", call_args)

    assert result.structured_content is not None
    assert result.structured_content["allow"] is True


@pytest.mark.anyio
async def test_eval_policy_uses_configured_policy_when_argument_omitted():
    """When the caller omits the ``policy`` argument, the gateway falls back
    to the policy configured for the tool via ``policy_provider`` (the
    same source ``PolicyMiddleware`` reads from)."""
    configured = {
        "SendMessage": """
package policy

default allow := false

to_conf := ifc.label("$.arguments.to").confidentiality
allow if to_conf == ["alice"]

decision := {"allow": allow}
""",
    }

    proxy = FastMCP("proxy")
    MCPGateway._register_eval_policy(
        proxy,
        policy_provider=lambda name, arguments: configured.get(name)
        or configured.get("*"),
    )

    call_args = {
        "call": {
            "name": "SendMessage",
            "arguments": {"to": "alice"},
            "_meta": {
                IFC_LABELS_META_PREFIX: {
                    "$['name']": {"integrity": "trusted", "confidentiality": []},
                    "$['arguments']['to']": {
                        "integrity": "trusted",
                        "confidentiality": ["alice"],
                    },
                }
            },
        },
    }

    async with Client(FastMCPTransport(proxy)) as client:
        result = await client.call_tool("eval_policy", call_args)

    assert result.structured_content is not None
    assert result.structured_content["allow"] is True


@pytest.mark.anyio
async def test_eval_policy_falls_back_to_wildcard_configured_policy():
    """The ``"*"`` key in the configured policies acts as a per-server
    fallback for any tool name without an explicit entry."""
    configured = {
        "*": """
package policy

default allow := false
allow if input.name == "AnyTool"

decision := {"allow": allow}
""",
    }

    proxy = FastMCP("proxy")
    MCPGateway._register_eval_policy(
        proxy,
        policy_provider=lambda name, arguments: configured.get(name)
        or configured.get("*"),
    )

    call_args = {
        "call": {
            "name": "AnyTool",
            "arguments": {},
            "_meta": {
                IFC_LABELS_META_PREFIX: {
                    "$": {"integrity": "trusted", "confidentiality": []},
                }
            },
        },
    }

    async with Client(FastMCPTransport(proxy)) as client:
        result = await client.call_tool("eval_policy", call_args)

    assert result.structured_content is not None
    assert result.structured_content["allow"] is True


@pytest.mark.anyio
async def test_eval_policy_explicit_policy_overrides_configured():
    """An explicit ``policy`` argument bypasses any configured fallback."""
    configured_policy = """
package policy
default allow := true
decision := {"allow": allow}
"""
    explicit_policy = """
package policy
default allow := false
decision := {"allow": allow}
"""

    proxy = FastMCP("proxy")
    MCPGateway._register_eval_policy(
        proxy,
        policy_provider=lambda name, arguments: configured_policy,
    )

    call_args = {
        "call": {
            "name": "Tool",
            "arguments": {},
            "_meta": {
                IFC_LABELS_META_PREFIX: {
                    "$": {"integrity": "trusted", "confidentiality": []},
                }
            },
        },
        "policy": explicit_policy,
    }

    async with Client(FastMCPTransport(proxy)) as client:
        result = await client.call_tool("eval_policy", call_args)

    assert result.structured_content is not None
    assert result.structured_content["allow"] is False


@pytest.mark.anyio
async def test_eval_policy_errors_when_no_policy_available():
    """If the caller omits ``policy`` and no policy is configured for the
    tool, the gateway returns an MCP tool error (``isError=true``) rather
    than a normal result."""
    proxy = FastMCP("proxy")
    MCPGateway._register_eval_policy(proxy)  # no policy_provider wired

    call_args = {
        "call": {
            "name": "Tool",
            "arguments": {},
            "_meta": {
                IFC_LABELS_META_PREFIX: {
                    "$": {"integrity": "trusted", "confidentiality": []},
                }
            },
        },
    }

    async with Client(FastMCPTransport(proxy)) as client:
        result = await client.call_tool("eval_policy", call_args, raise_on_error=False)

    assert result.is_error is True
    block = result.content[0]
    assert isinstance(block, TextContent)
    assert "No policy provided" in block.text
    assert "'Tool'" in block.text


@pytest.mark.anyio
async def test_eval_policy_errors_when_provider_returns_none():
    """Provider that returns ``None`` for the tool (e.g. no entry and no
    ``"*"`` fallback) is treated the same as having no provider — the
    call surfaces an MCP tool error."""
    proxy = FastMCP("proxy")
    MCPGateway._register_eval_policy(
        proxy, policy_provider=lambda name, arguments: None
    )

    call_args = {
        "call": {
            "name": "Tool",
            "arguments": {},
            "_meta": {
                IFC_LABELS_META_PREFIX: {
                    "$": {"integrity": "trusted", "confidentiality": []},
                }
            },
        },
    }

    async with Client(FastMCPTransport(proxy)) as client:
        result = await client.call_tool("eval_policy", call_args, raise_on_error=False)

    assert result.is_error is True
    block = result.content[0]
    assert isinstance(block, TextContent)
    assert "No policy provided" in block.text


# ---------------------------------------------------------------------------
# CaptureServerInfoMiddleware + upstream.serverInfo() Rego extension
# ---------------------------------------------------------------------------


def _make_versioned_backend(name: str, version: str) -> FastMCP:
    """A bare backend with a configurable name + version, no tools needed."""
    return FastMCP(name, version=version)


@pytest.mark.anyio
async def test_capture_server_info_middleware_records_on_initialize():
    """``on_initialize`` on the proxy must trigger a one-shot upstream
    capture: the recorded dict carries the upstream's ``Implementation``
    (``name``, ``version``)."""
    from middleware import CaptureServerInfoMiddleware

    upstream = _make_versioned_backend("workiq-stub", "1.4.2-rc.3")
    sink_calls: list[tuple[str, dict | None]] = []

    proxy = FastMCP("proxy")
    proxy.add_middleware(
        CaptureServerInfoMiddleware(
            server_id="workiq",
            upstream_client_factory=lambda: Client(FastMCPTransport(upstream)),
            sink=lambda sid, info: sink_calls.append((sid, info)),
        )
    )

    # A downstream client.list_tools() triggers initialize on the proxy.
    async with Client(FastMCPTransport(proxy)) as client:
        await client.list_tools()

    assert len(sink_calls) == 1
    sid, info = sink_calls[0]
    assert sid == "workiq"
    assert info is not None
    assert info["name"] == "workiq-stub"
    assert info["version"] == "1.4.2-rc.3"


@pytest.mark.anyio
async def test_capture_server_info_middleware_is_idempotent():
    """The middleware captures once per gateway lifetime; reconnecting
    downstream clients (each of which initialize again) must not retrigger
    upstream sessions."""
    from middleware import CaptureServerInfoMiddleware

    upstream = _make_versioned_backend("workiq-stub", "1.0.0")
    sink_calls: list[tuple[str, dict | None]] = []

    mw = CaptureServerInfoMiddleware(
        server_id="workiq",
        upstream_client_factory=lambda: Client(FastMCPTransport(upstream)),
        sink=lambda sid, info: sink_calls.append((sid, info)),
    )
    proxy = FastMCP("proxy")
    proxy.add_middleware(mw)

    for _ in range(3):
        async with Client(FastMCPTransport(proxy)) as client:
            await client.list_tools()

    assert len(sink_calls) == 1


@pytest.mark.anyio
async def test_capture_server_info_middleware_failure_does_not_break_downstream():
    """If the upstream capture raises (auth failure, transport error,
    etc.), the middleware swallows the error, leaves the cache empty,
    and the downstream initialize still succeeds."""
    from middleware import CaptureServerInfoMiddleware

    class _Boom:
        async def __aenter__(self):
            raise RuntimeError("upstream is down")

        async def __aexit__(self, *_):
            return False

    sink_calls: list[tuple[str, dict | None]] = []
    proxy = FastMCP("proxy")
    proxy.add_middleware(
        CaptureServerInfoMiddleware(
            server_id="workiq",
            upstream_client_factory=lambda: _Boom(),
            sink=lambda sid, info: sink_calls.append((sid, info)),
        )
    )

    async with Client(FastMCPTransport(proxy)) as client:
        # Downstream init succeeds despite the upstream capture blowing up.
        tools = await client.list_tools()
        assert isinstance(tools, list)

    # Capture failed → sink never called, cache stays empty.
    assert sink_calls == []


@pytest.mark.anyio
async def test_upstream_server_info_extension_returns_cached_dict():
    """End-to-end: a Rego policy invokes ``upstream.serverInfo()`` and
    sees the dict the middleware captured."""
    from middleware import CaptureServerInfoMiddleware

    upstream = _make_versioned_backend("workiq-stub", "1.4.2-rc.3")
    cache: dict[str, dict | None] = {}

    proxy = FastMCP("proxy")
    proxy.add_middleware(
        CaptureServerInfoMiddleware(
            server_id="workiq",
            upstream_client_factory=lambda: Client(FastMCPTransport(upstream)),
            sink=lambda sid, info: cache.__setitem__(sid, info),
        )
    )
    MCPGateway._register_eval_policy(
        proxy,
        server_info_provider=lambda: cache.get("workiq"),
    )

    policy = """
package policy

import rego.v1

info := upstream.serverInfo()
name := info.name
version := info.version
allow if startswith(info.version, "1.")

decision := {"info": info, "name": name, "version": version, "allow": allow}
"""
    call_args = {
        "call": {
            "name": "Anything",
            "arguments": {},
            "_meta": {
                IFC_LABELS_META_PREFIX: {
                    "$": {"integrity": "trusted", "confidentiality": []},
                }
            },
        },
        "policy": policy,
    }

    async with Client(FastMCPTransport(proxy)) as client:
        # First call triggers the middleware capture during initialize.
        result = await client.call_tool("eval_policy", call_args)

    assert result.structured_content is not None
    assert result.structured_content["info"]["name"] == "workiq-stub"
    assert result.structured_content["info"]["version"] == "1.4.2-rc.3"
    assert result.structured_content["name"] == "workiq-stub"
    assert result.structured_content["version"] == "1.4.2-rc.3"
    assert result.structured_content["allow"] is True


@pytest.mark.anyio
async def test_upstream_server_info_extension_returns_null_before_capture():
    """If a policy is evaluated before the upstream capture has populated
    the cache (e.g. capture is wired but failed), ``upstream.serverInfo()``
    returns Rego null, which policies can guard against."""
    proxy = FastMCP("proxy")
    MCPGateway._register_eval_policy(
        proxy,
        server_info_provider=lambda: None,  # cache empty
    )

    policy = """
package policy

import rego.v1

raw := upstream.serverInfo()
available := raw != null

decision := {"available": available}
"""
    call_args = {
        "call": {
            "name": "Anything",
            "arguments": {},
            "_meta": {
                IFC_LABELS_META_PREFIX: {
                    "$": {"integrity": "trusted", "confidentiality": []},
                }
            },
        },
        "policy": policy,
    }

    async with Client(FastMCPTransport(proxy)) as client:
        result = await client.call_tool("eval_policy", call_args)

    assert result.structured_content is not None
    assert result.structured_content["available"] is False


@pytest.mark.anyio
async def test_upstream_server_info_extension_picks_up_re_capture():
    """The ``server_info_provider`` is consulted on every ``eval_policy``
    call: a value captured (or recaptured) after the proxy was wired
    must be visible to subsequent policy evaluations without rebuilding
    the proxy."""
    cache: dict[str, dict[str, Any] | None] = {"workiq": None}

    proxy = FastMCP("proxy")
    MCPGateway._register_eval_policy(
        proxy,
        server_info_provider=lambda: cache.get("workiq"),
    )

    policy = """
package policy

import rego.v1

raw := upstream.serverInfo()
available := raw != null

default name := ""
name := raw.name if raw != null

decision := {"available": available, "name": name}
"""
    call_args = {
        "call": {
            "name": "Anything",
            "arguments": {},
            "_meta": {
                IFC_LABELS_META_PREFIX: {
                    "$": {"integrity": "trusted", "confidentiality": []},
                }
            },
        },
        "policy": policy,
    }

    async with Client(FastMCPTransport(proxy)) as client:
        # 1. Before any capture: provider returns None → policy sees null.
        before = await client.call_tool("eval_policy", call_args)
        assert before.structured_content is not None
        assert before.structured_content["available"] is False

        # 2. Simulate a successful capture by populating the cache.
        cache["workiq"] = {"name": "workiq-stub", "version": "1.0.0"}
        after_first = await client.call_tool("eval_policy", call_args)
        assert after_first.structured_content is not None
        assert after_first.structured_content["available"] is True
        assert after_first.structured_content["name"] == "workiq-stub"

        # 3. Simulate a re-capture (different upstream identity); the
        #    provider's new return value must reach the next call.
        cache["workiq"] = {"name": "workiq-replaced", "version": "2.0.0"}
        after_recapture = await client.call_tool("eval_policy", call_args)
        assert after_recapture.structured_content is not None
        assert after_recapture.structured_content["available"] is True
        assert after_recapture.structured_content["name"] == "workiq-replaced"


@pytest.mark.anyio
async def test_eval_policy_selects_policy_by_path_argument():
    """A tool configured with path rules resolves a different policy per
    call, from the resource path the call names.

    This is what lets one generic tool (``create_entity``) carry several
    policies: without it, every creation would share whichever single
    policy the tool name is bound to.
    """
    from middleware import resolve_policies, select_by_path

    def _policy(verdict: str) -> str:
        return f"""
package policy

decision := {{"decision": "{verdict}"}}
"""

    configured = resolve_policies(
        {
            "*": {"literal": _policy("deny")},
            "create_entity": {
                "pathArg": "parentUrl",
                "rules": [
                    {"path": "/chats/*/messages", "literal": _policy("teams")},
                    {"path": "/me/events", "literal": _policy("calendar")},
                ],
            },
        }
    )

    def _policy_for(name, arguments):
        spec = configured.get(name)
        policy = select_by_path(spec, arguments) if spec is not None else None
        if policy is not None:
            return policy
        default = configured.get("*")
        return select_by_path(default, arguments) if default is not None else None

    proxy = FastMCP("proxy")
    MCPGateway._register_eval_policy(proxy, policy_provider=_policy_for)

    async def _decide(parent_url: str) -> str:
        call_args = {
            "call": {
                "name": "create_entity",
                "arguments": {"parentUrl": parent_url},
                "_meta": {
                    IFC_LABELS_META_PREFIX: {
                        "$": {"integrity": "trusted", "confidentiality": []},
                    }
                },
            },
        }
        async with Client(FastMCPTransport(proxy)) as client:
            result = await client.call_tool("eval_policy", call_args)
        assert result.structured_content is not None
        return result.structured_content["decision"]

    assert await _decide("/chats/c1/messages") == "teams"
    assert await _decide("/me/events") == "calendar"
    # An unrouted path keeps the server's deny default.
    assert await _decide("/me/drive/root/children") == "deny"
