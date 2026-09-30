from __future__ import annotations

import contextlib
import json

from pathlib import Path
from typing import Any, Callable

from fastmcp import Client, FastMCP
from fastmcp.client.auth import OAuth
from fastmcp.client.transports import StreamableHttpTransport
from fastmcp.exceptions import ToolError
from fastmcp.server import create_proxy
from fastmcp.server.middleware import Middleware

from starlette.applications import Starlette
from starlette.routing import Mount

from msal_auth import MSALBearerAuth
from policy_engine import LabeledToolCallParams

import policy_engine

from workiq_labeller import WorkIQLabellingMiddleware
from label_conversion import LabelConversionMiddleware

from middleware import (
    CaptureServerInfoMiddleware,
    MetaPrefixTranslationMiddleware,
    StripFastmcpMetaMiddleware,
    ToolAnnotationsMiddleware,
    PolicyMiddleware,
    resolve_policies,
)
from output_schema import OutputSchemaMiddleware


def load_config(config_path: Path) -> dict[str, Any]:
    """Load and validate the proxy configuration from a JSON file."""

    with open(config_path) as f:
        mcp_config = json.load(f)

    if "mcpServers" not in mcp_config:
        raise ValueError("Configuration must have a top-level 'mcpServers' key")

    server_meta: dict[str, Any] = {}
    for server_id, cfg in mcp_config["mcpServers"].items():
        if cfg["type"] != "http":
            raise ValueError(
                f"Unsupported server type '{cfg['type']}' for server '{server_id}'"
            )

        if "url" not in cfg:
            raise ValueError(f"Server '{server_id}' is missing required 'url' field")

        server_meta[server_id] = {"type": cfg["type"], "url": cfg["url"]}

        if "headers" in cfg:
            if not isinstance(cfg["headers"], dict):
                raise ValueError(
                    f"Server '{server_id}' 'headers' field must be an object"
                )
            for hname, hvalue in cfg["headers"].items():
                if not isinstance(hvalue, str):
                    raise ValueError(
                        f"Server '{server_id}' header '{hname}' must be a string"
                    )
            server_meta[server_id]["headers"] = dict(cfg["headers"])

        if "msal" in cfg and "oauth" in cfg:
            raise ValueError(
                f"Server '{server_id}' has both 'msal' and 'oauth' blocks; "
                "they are mutually exclusive"
            )

        if "msal" in cfg:
            server_meta[server_id]["msal"] = {
                "tenant_id": cfg["msal"]["tenantId"],
                "client_id": cfg["msal"]["clientId"],
                "scopes": cfg["msal"].get("scopes"),
                "callback_port": cfg["msal"].get("callbackPort", 8080),
            }

        if "oauth" in cfg:
            server_meta[server_id]["oauth"] = {
                "client_id": cfg["oauth"].get("clientId"),
                "client_secret": cfg["oauth"].get("clientSecret"),
                "scopes": cfg["oauth"].get("scopes"),
                "callback_port": cfg["oauth"].get("callbackPort"),
            }

        if "middleware" in cfg:
            server_meta[server_id]["middleware"] = cfg["middleware"]

    return server_meta


class MCPGateway:
    """FastMCP-based gateway proxy with per-server middleware.

    Sits between an MCP client and one or more MCP servers, forwarding
    requests through ``fastmcp.server.create_proxy(...)`` while providing a
    hook surface for per-server FastMCP middleware. Each upstream listed in
    the configuration gets its own :class:`fastmcp.FastMCP` proxy with the
    middleware chain assembled by :meth:`_build_proxy`; the resulting
    per-upstream apps are mounted under ``/mcp/<server_id>/`` by
    :meth:`asgi_app`.
    """

    def __init__(self, config_path: Path, token_cache_path: Path) -> None:
        """Initialize the gateway with configuration and token cache paths."""
        self.config = load_config(config_path)
        self.token_cache_path = token_cache_path

        # Per-upstream cache of ``serverInfo`` (the MCP
        # :class:`mcp.types.Implementation` dict: ``name``, ``title``,
        # ``version``, ``websiteUrl``, ``icons``). Populated lazily by
        # :class:`CaptureServerInfoMiddleware` on the first downstream
        # ``initialize`` per upstream, and exposed to Rego policies as
        # ``upstream.serverInfo()`` by :func:`policy_engine.eval_policy`.
        # ``None`` while uncaptured; remains ``None`` if the upstream
        # capture failed (the extension surfaces ``None`` to the policy).
        self._upstream_server_info: dict[str, dict[str, Any] | None] = {}

        # Build one FastMCP proxy per upstream
        self._proxies: dict[str, FastMCP] = {
            server_id: self._build_proxy(server_id) for server_id in self.config
        }

    def _record_server_info(self, server_id: str, info: dict[str, Any] | None) -> None:
        """Sink invoked by :class:`CaptureServerInfoMiddleware`."""
        self._upstream_server_info[server_id] = info

    @staticmethod
    def _register_eval_policy(
        mcp: FastMCP,
        upstream_client_factory: (
            Callable[[], Client[StreamableHttpTransport]] | None
        ) = None,
        server_info_provider: Callable[[], dict[str, Any] | None] | None = None,
        policy_provider: Callable[[str], str | None] | None = None,
    ) -> None:
        """Register the gateway-implemented policy-evaluation tool,
        backed by :func:`_eval_policy`:

        - ``eval_policy`` takes a :class:`ProposedToolCall` with optional
            IFC labels and a Rego policy string, evaluates the policy against
            the proposed call, and returns a decision.

        The tool is advertised alongside the proxied upstream tools in every
        ``list_tools`` response with an ``inputSchema`` derived from its Pydantic
        model.

        If *upstream_client_factory* is provided, each invocation instantiates
        a fresh upstream client from the factory and passes it to
        :func:`_eval_policy`, enabling policies to call upstream MCP tools
        dynamically via ``upstream.<ToolName>(args)``.

        If *server_info_provider* is provided, its (synchronous) result is
        passed to :func:`_eval_policy` for each invocation so the
        ``upstream.serverInfo()`` Rego extension can return the upstream's
        most recently captured :class:`mcp.types.Implementation` dict
        (``None`` if not yet captured).

        If *policy_provider* is provided, it is consulted (with the
        proposed tool call's ``name``) whenever the caller omits the
        ``policy`` argument, supplying the recommended Rego snippet
        configured for that tool (typically by ``PolicyMiddleware``).
        When neither is available the call returns an MCP tool error
        (``isError=true``) via :class:`fastmcp.exceptions.ToolError`.
        """

        @mcp.tool
        async def eval_policy(  # pyright: ignore[reportUnusedFunction]
            call: LabeledToolCallParams, policy: str | None = None
        ) -> Any:
            """Evaluate a Rego policy against a labelled MCP tool call.

            Consumes the wire-level :class:`mcp.types.CallToolRequestParams`
            shape: arguments are raw values (no per-argument
            ``{value, labels}`` wrapper) and IFC labels travel in
            ``_meta[IFC_LABELS_META_PREFIX]`` keyed by RFC 9535 JSONPath
            singular-query strings rooted at the call — e.g.
            ``"$['name']"``, ``"$['arguments']['foo']"``,
            ``"$['arguments']['foo']['bar']"``. Keys may be supplied in
            any equivalent singular form (e.g. ``$.arguments.foo`` and
            ``$['arguments']['foo']`` refer to the same node); they are
            normalized to RFC 9535 Normalized Path form internally. The
            ``"$"`` key is the call-level fallback. Wildcards, descendant
            segments, slices, filters, and multi-selector segments are
            rejected.

            ``name`` and ``arguments`` are exposed to Rego as ``input.name``
            and ``input.arguments`` (flattened — there is no ``input.call``
            wrapper). Inside the policy, an ``ifc.label(path)`` function is
            available where ``path`` is an RFC 9535 JSONPath
            singular-query string rooted at ``$`` — the same syntax used
            to key labels in ``_meta[IFC_LABELS_META_PREFIX]``::

                ifc.label("$['name']")
                ifc.label("$.arguments.foo")
                ifc.label("$['arguments']['foo']['bar']")
                ifc.label("$.arguments.items[0].v")
                ifc.label("$")                       # call-level fallback

            The lookup resolves the *effective* label per the four rules
            documented on :func:`_make_label_extension`: explicit label at
            the queried path, otherwise the join of descendants' effective
            labels, otherwise the nearest labelled ancestor, otherwise the
            call-level fallback at ``"$"`` (if one is configured).

            Upstream tools are exposed to the policy as
            ``upstream.<ToolName>(args)`` when an upstream client is wired
            up at registration time.

            Parameters
            ----------
            call:
                The labelled tool call. ``call.name``, ``call.arguments``,
                and ``call._meta[IFC_LABELS_META_PREFIX]`` follow the schema in
                :class:`LabeledToolCallParams`.
            policy:
                The Rego policy text to evaluate. Must declare
                ``package policy``. Optional: if omitted, the policy
                configured for ``call.name`` in the gateway's
                ``PolicyMiddleware`` (with ``"*"`` as a per-server
                fallback) is used. A :class:`ToolError` is raised — and
                surfaced as an MCP tool result with ``isError=true`` —
                when no ``policy`` argument is supplied and no policy
                is configured for the tool.

            Returns
            -------
            The ``policy`` object produced by the policy (i.e. the value
            of ``data.policy`` after evaluation).
            """
            if policy is None:
                policy = (
                    policy_provider(call.name) if policy_provider is not None else None
                )
                if policy is None:
                    raise ToolError(
                        f"No policy provided and no policy configured for tool "
                        f"{call.name!r}."
                    )
            upstream_client = (
                upstream_client_factory()
                if upstream_client_factory is not None
                else None
            )
            server_info = (
                server_info_provider() if server_info_provider is not None else None
            )
            return await policy_engine.eval_policy(
                call.model_dump(by_alias=True),
                policy,
                upstream_client,
                server_info=server_info,
                query="data.policy.decision",
            )

    def _build_proxy(self, server_id: str) -> FastMCP:
        config = self.config[server_id]
        headers = config.get("headers")
        if "msal" in config:
            transport = StreamableHttpTransport(
                url=config["url"],
                headers=headers,
                auth=MSALBearerAuth(
                    token_cache_file=self.token_cache_path,
                    scopes=config["msal"]["scopes"],
                    client_id=config["msal"]["client_id"],
                    tenant_id=config["msal"]["tenant_id"],
                    callback_port=config["msal"]["callback_port"],
                ),
            )
            client = Client(transport)
        elif "oauth" in config:
            # GitHub-style providers don't implement OAuth 2.0 Dynamic Client
            # Registration, so we must use pre-registered client credentials
            # rather than auth="oauth" (which would attempt DCR and 404).
            oauth_cfg = config["oauth"]
            auth = OAuth(
                mcp_url=config["url"],
                scopes=oauth_cfg["scopes"],
                callback_port=oauth_cfg["callback_port"],
                client_id=oauth_cfg["client_id"],
                client_secret=oauth_cfg["client_secret"],
            )
            transport = StreamableHttpTransport(
                url=config["url"], headers=headers, auth=auth
            )
            client = Client(transport)
        else:
            transport = StreamableHttpTransport(url=config["url"], headers=headers)
            client = Client(transport)
        proxy = create_proxy(client, name=server_id)
        proxy.add_middleware(
            CaptureServerInfoMiddleware(
                server_id=server_id,
                upstream_client_factory=lambda: Client(transport),
                sink=self._record_server_info,
            )
        )

        # Extract policies configured for this server's PolicyMiddleware
        # (if any) so eval_policy can default to the per-tool recommended
        # policy when the caller omits the ``policy`` argument. If multiple
        # PolicyMiddleware entries are configured they are merged in order
        # (later entries win on key conflicts), mirroring the order they're
        # added to the proxy.
        configured_policies: dict[str, str] = {}
        for middleware in config.get("middleware", []):
            if middleware["type"] == PolicyMiddleware.__name__:
                configured_policies.update(resolve_policies(middleware.get("policies")))

        def _policy_for(name: str) -> str | None:
            return configured_policies.get(name) or configured_policies.get("*")

        self._register_eval_policy(
            proxy,
            upstream_client_factory=lambda: Client(transport),
            server_info_provider=lambda: self._upstream_server_info.get(server_id),
            policy_provider=_policy_for,
        )

        # Add middleware from configuration
        for middleware in config.get("middleware", []):
            print(f"Adding middleware {middleware['type']} to server {server_id}")
            if middleware["type"] == MetaPrefixTranslationMiddleware.__name__:
                proxy.add_middleware(
                    MetaPrefixTranslationMiddleware(
                        prefix_map=middleware.get("prefixMap")
                    )
                )
            elif middleware["type"] == LabelConversionMiddleware.__name__:
                # Translate IFC-label principals between the GitHub handles
                # exposed to clients and the Microsoft user IDs used internally
                # by labelers and policies.
                proxy.add_middleware(LabelConversionMiddleware())
            elif middleware["type"] == ToolAnnotationsMiddleware.__name__:
                proxy.add_middleware(
                    ToolAnnotationsMiddleware(
                        annotations=middleware.get("toolAnnotations")
                    )
                )
            elif middleware["type"] == PolicyMiddleware.__name__:
                proxy.add_middleware(
                    PolicyMiddleware(policies=middleware.get("policies"))
                )
            elif middleware["type"] == StripFastmcpMetaMiddleware.__name__:
                proxy.add_middleware(StripFastmcpMetaMiddleware())
            elif middleware["type"] == OutputSchemaMiddleware.__name__:
                proxy.add_middleware(
                    OutputSchemaMiddleware(schemas=middleware.get("outputSchemas"))
                )
            elif middleware["type"] == WorkIQLabellingMiddleware.__name__:
                proxy.add_middleware(
                    WorkIQLabellingMiddleware(
                        upstream_client_factory=lambda: Client(transport)
                    )
                )
            else:
                raise ValueError(
                    f"Unsupported middleware type '{middleware['type']}' "
                    f"in server '{server_id}'"
                )

        return proxy

    def asgi_app(self) -> Starlette:
        print(f"Mounting proxies: {list(self._proxies.keys())}")

        mcp_apps = {
            sid: proxy.http_app(path="/") for sid, proxy in self._proxies.items()
        }

        @contextlib.asynccontextmanager
        async def lifespan(app: Starlette):
            # Each mounted FastMCP app owns a StreamableHTTPSessionManager task
            # group that must be started via its lifespan; without this the
            # mounted apps respond 500 ("Task group is not initialized").
            async with contextlib.AsyncExitStack() as stack:
                for mcp_app in mcp_apps.values():
                    await stack.enter_async_context(mcp_app.lifespan(app))
                yield

        return Starlette(
            routes=[
                Mount(f"/mcp/{sid}/", app=mcp_app) for sid, mcp_app in mcp_apps.items()
            ],
            lifespan=lifespan,
        )

    # Public hook API for users of the gateway:
    def add_middleware(self, server_id: str, middleware: Middleware) -> None:
        self._proxies[server_id].add_middleware(middleware)
