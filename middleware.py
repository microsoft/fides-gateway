from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from fastmcp import Client
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools import Tool, ToolResult
from fastmcp.client.transports.base import ClientTransportT

from mcp.types import RequestParams, ToolAnnotations, CallToolRequestParams

logger = logging.getLogger(__name__)


IFC_POLICY_META_PREFIX = "com.github.ifc/policy"


# ---------------------------------------------------------------------------
# Middleware to inject tool annotations into the tool metadata returned
# by ``tools/list``.
# ---------------------------------------------------------------------------


def _merge_annotations(
    tools: Sequence[Tool], annotations: dict[str, dict[str, Any]]
) -> Sequence[Tool]:
    """Merge configured ``ToolAnnotations`` into *tools* in place.

    *annotations* mirrors the ``toolAnnotations`` block of the proxy
    configuration file. The special ``"*"`` key supplies defaults applied to
    every tool, per-tool entries override those defaults, and any annotation
    already set on a tool by the upstream server takes precedence over both —
    so configuration only fills in / supplements what the upstream did not
    provide.
    """
    defaults = annotations.get("*", {})
    for tool in tools:
        overrides = annotations.get(tool.name, {})
        configured = {**defaults, **overrides}
        if not configured:
            continue
        existing = (
            tool.annotations.model_dump(exclude_none=True, by_alias=True)
            if tool.annotations is not None
            else {}
        )
        # Upstream-provided annotations win over configured ones.
        merged = {**configured, **existing}
        tool.annotations = ToolAnnotations(**merged)
    return tools


class ToolAnnotationsMiddleware(Middleware):
    """FastMCP middleware that injects tool annotations into the tool metadata.

    - ``on_list_tools`` merges the
      configured ``ToolAnnotations`` into every ``list_tools`` reply.

    The annotations mapping is supplied at construction time from the
    gateway's startup config (the ``toolAnnotations`` block).
    """

    def __init__(self, annotations: dict[str, dict[str, Any]] | None = None) -> None:
        self.annotations = annotations or {}

    async def on_list_tools(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Sequence[Tool]],
    ) -> Sequence[Tool]:
        tools = await call_next(context)
        tools = _merge_annotations(tools, self.annotations)
        return tools


# ---------------------------------------------------------------------------
# Middleware to inject policies into the tool metadata returned
# by ``tools/list``.
# ---------------------------------------------------------------------------


def _merge_policies(tools: Sequence[Tool], policies: dict[str, str]) -> Sequence[Tool]:
    """Inject IFC_POLICY_META_PREFIX into each tool's ``_meta`` in place.

    *policies* mirrors the ``policies`` block of the proxy
    configuration file: a mapping of tool name to a recommended default
    policy (typically a short Rego snippet) that the gateway advertises to
    clients via the tool's ``_meta`` field. Tools without an entry are left
    untouched. Any IFC_LABELS_META_PREFIX = "com.github.ifc/labels" already
    present on the upstream tool's ``_meta`` is preserved (upstream wins).
    """
    default = policies.get("*")
    for tool in tools:
        override = policies.get(tool.name)
        meta = dict(tool.meta) if tool.meta else {}
        policy = override or default
        if policy is not None:
            meta.setdefault(IFC_POLICY_META_PREFIX, policy)
        tool.meta = meta
    return tools


def _resolve_policy_spec(spec: Any) -> str:
    """Resolve a single policy specification to its Rego source text.

    A spec is a mapping with exactly one of two keys:

    - ``{"literal": "<rego source>"}`` — the value is used verbatim.
    - ``{"file": "<path/to/policy.rego>"}`` — the file is read and its
      contents are returned. Relative paths are resolved against the
      current working directory.
    """
    if not isinstance(spec, Mapping):
        raise TypeError(
            "PolicyMiddleware: each policy entry must be a mapping with "
            "either a 'literal' or a 'file' key, got "
            f"{type(spec).__name__}: {spec!r}"
        )
    keys = set(spec.keys())
    extra = keys - {"literal", "file"}
    if extra:
        raise ValueError(
            "PolicyMiddleware: unsupported keys in policy entry: "
            f"{sorted(extra)}; expected 'literal' or 'file'"
        )
    if keys == {"literal", "file"}:
        raise ValueError(
            "PolicyMiddleware: policy entry must specify exactly one of "
            "'literal' or 'file', not both"
        )
    if "literal" in spec:
        value = spec["literal"]
        if not isinstance(value, str):
            raise TypeError(
                "PolicyMiddleware: 'literal' value must be a string, got "
                f"{type(value).__name__}"
            )
        return value
    if "file" in spec:
        path = spec["file"]
        if not isinstance(path, str):
            raise TypeError(
                "PolicyMiddleware: 'file' value must be a string path, got "
                f"{type(path).__name__}"
            )
        return Path(path).read_text()
    raise ValueError(
        "PolicyMiddleware: policy entry must specify either 'literal' or " "'file'"
    )


def resolve_policies(
    policies: Mapping[str, Any] | None,
) -> dict[str, str]:
    """Resolve a ``policies`` config block to a ``{tool_name: rego_text}`` map.

    Each value in *policies* must be a mapping accepted by
    :func:`_resolve_policy_spec` (``{"literal": ...}`` or
    ``{"file": ...}``).
    """
    if not policies:
        return {}
    return {name: _resolve_policy_spec(spec) for name, spec in policies.items()}


class PolicyMiddleware(Middleware):
    """FastMCP middleware that injects tool policies into the tool metadata.

    - ``on_list_tools`` merges the
      configured ``policies`` into every ``tools/list`` reply.

    The policies mapping is supplied at construction time from the
    gateway's middleware config (the ``policies`` block). Each value is
    a mapping with either a ``"literal"`` key (the Rego source as a
    string, used verbatim) or a ``"file"`` key (a path to a ``.rego``
    file whose contents are read at construction time).
    """

    def __init__(self, policies: Mapping[str, Any] | None = None) -> None:
        self.policies: dict[str, str] = resolve_policies(policies)

    async def on_list_tools(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Sequence[Tool]],
    ) -> Sequence[Tool]:
        tools = await call_next(context)
        tools = _merge_policies(tools, self.policies)
        return tools


# ---------------------------------------------------------------------------
# Middleware that strips the FastMCP-injected ``fastmcp`` metadata.
# ---------------------------------------------------------------------------


class StripFastmcpMetaMiddleware(Middleware):
    """Remove the FastMCP-injected ``fastmcp`` namespace from tool metadata.

    Starting with FastMCP 3.0, ``Tool.get_meta()`` always injects a
    ``meta['fastmcp'] = {"tags": [...], ...}`` entry into every tool returned
    by ``list_tools``. There is no built-in opt-out. Because the injection
    happens at serialization time inside ``Tool.to_mcp_tool()`` (after the
    middleware chain returns) mutating ``tool.meta`` from a middleware would
    be silently overwritten. Instead, we rebind ``get_meta`` on each returned
    tool instance to call the original and then pop the ``fastmcp`` (and
    legacy ``_fastmcp``) keys.
    """

    async def on_list_tools(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Sequence[Tool]],
    ) -> Sequence[Tool]:
        tools = await call_next(context)
        for tool in tools:
            original_get_meta = tool.get_meta

            def stripped_get_meta(
                _orig: Callable[[], dict[str, Any]] = original_get_meta,
            ) -> dict[str, Any]:
                meta = _orig()
                if meta:
                    meta.pop("fastmcp", None)
                    meta.pop("_fastmcp", None)
                return meta

            # FastMCP's Tool is a Pydantic model and rejects attribute
            # assignment, so bypass validation via object.__setattr__.
            object.__setattr__(tool, "get_meta", stripped_get_meta)
        return tools


# ---------------------------------------------------------------------------
# Middleware that captures the upstream's ``serverInfo`` on the first
# downstream ``initialize`` and stores it on the gateway.
# ---------------------------------------------------------------------------


class CaptureServerInfoMiddleware(Middleware):
    """Capture the upstream MCP server's ``serverInfo`` on first init.

    FastMCP's ``create_proxy`` hides the upstream's identity from
    downstream clients (the proxy advertises itself with the
    ``name=server_id`` we pass it). To make the upstream's
    :class:`mcp.types.Implementation` (``name``, ``title``, ``version``,
    ``websiteUrl``, ``icons``) available to Rego policies as
    ``upstream.serverInfo()``, this middleware hooks ``on_initialize``:
    on the first downstream ``initialize`` it opens a transient upstream
    session via *upstream_client_factory*, reads
    ``session.initialize_result.serverInfo``, dumps it to a plain dict,
    and hands it to *sink*. Subsequent ``initialize`` calls are no-ops.

    The capture is wrapped in an :class:`asyncio.Lock` so concurrent
    first-time inits don't open multiple upstream sessions, and in a
    ``try/except`` so a transient upstream failure (auth, network, etc.)
    doesn't break the downstream handshake — we just leave the cache
    empty and the Rego ``upstream.serverInfo()`` extension returns
    ``None`` until a later ``initialize`` succeeds.

    Lazy by design: this middleware only opens an upstream session to
    capture ``serverInfo``; it intentionally doesn't do it at startup so
    interactive MSAL auth is not forced before the first downstream
    request arrives.
    """

    def __init__(
        self,
        server_id: str,
        upstream_client_factory: Callable[[], Client[ClientTransportT]],
        sink: Callable[[str, dict[str, Any] | None], None],
    ) -> None:
        self._server_id = server_id
        self._upstream_client_factory = upstream_client_factory
        self._sink = sink
        self._captured = False
        self._lock = asyncio.Lock()

    async def on_initialize(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Any],
    ) -> Any:
        # Let the proxy handle the downstream handshake first; we only
        # piggy-back to grab the upstream's identity.
        result = await call_next(context)
        if self._captured:
            return result
        async with self._lock:
            if self._captured:
                return result
            try:
                async with self._upstream_client_factory() as session:
                    init = session.initialize_result
                    info = getattr(init, "serverInfo", None) if init else None
                    self._sink(
                        self._server_id,
                        info.model_dump(by_alias=True) if info else None,
                    )
            except Exception:
                logger.exception(
                    "CaptureServerInfoMiddleware: failed to capture "
                    "upstream serverInfo for server %r",
                    self._server_id,
                )
                # Leave the cache empty; a later successful initialize
                # will populate it.
                return result
            self._captured = True
        return result


# ---------------------------------------------------------------------------
# Middleware that rewrites ``_meta`` key prefixes between client and proxy
# conventions.
# ---------------------------------------------------------------------------


def _translate_meta_keys(
    meta: dict[str, Any] | None,
    mapping: list[tuple[str, str]],
) -> dict[str, Any] | None:
    """Return a copy of *meta* with every key prefix rewritten per *mapping*.

    *mapping* is a list of ``(src_prefix, dst_prefix)`` pairs sorted by
    descending ``src_prefix`` length so longer prefixes match first
    (e.g. ``"a/b/"`` beats ``"a/"``). At most one rewrite is applied
    per key; the translated key is never re-translated.

    Returns ``None`` unchanged so callers can pass the result straight
    back to a Pydantic model that uses ``None`` to mean "no metadata".
    """
    if not meta:
        return meta
    out: dict[str, Any] = {}
    for k, v in meta.items():
        new_k = k
        for src, dst in mapping:
            if k.startswith(src):
                new_k = dst + k[len(src) :]
                break
        out[new_k] = v
    return out


class MetaPrefixTranslationMiddleware(Middleware):
    """Translate ``_meta`` key prefixes between client and proxy conventions.

    Configured with a mapping of ``{client_prefix: proxy_prefix}``. The
    middleware rewrites ``_meta`` keys in both directions:

    - On *incoming* tool calls, any ``_meta`` key starting with a
      configured ``client_prefix`` is rewritten so that prefix is
      replaced by the corresponding ``proxy_prefix`` before the call is
      handed off to the rest of the chain.
    - On *outgoing* tool listings and tool-call results, any ``_meta``
      key starting with a configured ``proxy_prefix`` is rewritten so
      that prefix is replaced by the corresponding ``client_prefix``
      before it is returned to the client.

    The main use is interoperating with clients that speak a shorter
    or different namespace than the gateway's canonical one — e.g. a
    client that uses ``"ifc/labels"`` and ``"ifc/policy"`` while the
    gateway internally uses ``"com.github.ifc/labels"`` and
    ``"com.github.ifc/policy"``. Configuring
    ``{"ifc/": "com.github.ifc/"}`` makes the two ends interoperate
    transparently.

    Matching is by string ``startswith``: configure each prefix with
    whatever delimiter (typically ``"/"``) you want at the boundary.
    When multiple ``client_prefix`` strings would match the same key,
    the longest match wins; the rewritten key is never re-translated.
    Each ``proxy_prefix`` must be unique across the mapping so the
    reverse direction is unambiguous.

    Middleware ordering
    -------------------
    This middleware MUST be registered **first** on the proxy so it is
    the outermost wrapper of the chain. FastMCP runs the response chain
    in reverse-registration order, so "outermost on registration" means
    "innermost on the request and last to touch the response". In
    practice that gives the two properties we want:

    - On a request, the client-prefixed ``_meta`` keys are translated
      to the canonical proxy form *before* any downstream middleware
      (e.g. a policy or labelling middleware) inspects them.
    - On a response, every other middleware has already finished
      injecting / mutating the canonical proxy keys by the time this
      middleware runs, so a single translation pass at the very end
      is enough to ensure the client only ever sees client-prefixed
      keys.

    Registering this middleware anywhere else lets canonical-prefixed
    keys injected by later middleware (most commonly ``PolicyMiddleware``)
    leak through to the client unchanged.
    """

    def __init__(self, prefix_map: dict[str, str]) -> None:
        proxy_values = list(prefix_map.values())
        if len(set(proxy_values)) != len(proxy_values):
            raise ValueError(
                "MetaPrefixTranslationMiddleware: proxy_prefix values "
                "must be unique across the mapping"
            )
        self._client_to_proxy: list[tuple[str, str]] = sorted(
            prefix_map.items(), key=lambda kv: len(kv[0]), reverse=True
        )
        self._proxy_to_client: list[tuple[str, str]] = sorted(
            ((v, k) for k, v in prefix_map.items()),
            key=lambda kv: len(kv[0]),
            reverse=True,
        )

    async def on_call_tool(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        params = context.message
        # CallToolRequestParams.meta is an MCP ``RequestParams.Meta``
        # Pydantic model (with ``extra='allow'``), not a plain dict.
        # Dump it to a dict, rewrite keys, then assign back; the field is
        # ``extra='allow'`` so a dict revalidates cleanly.
        if params.meta is not None:
            assert (
                type(params.meta) is RequestParams.Meta
            ), "Unexpected _meta parameter type"
            meta_dict = params.meta.model_dump(by_alias=True, exclude_none=True)
            translated = _translate_meta_keys(meta_dict, self._client_to_proxy)
            params.meta = type(params.meta).model_validate(translated)
        result = await call_next(context)
        # Rewrite the outbound _meta on the result (proxy → client).
        result.meta = _translate_meta_keys(result.meta, self._proxy_to_client)
        return result

    async def on_list_tools(
        self,
        context: MiddlewareContext[Any],
        call_next: CallNext[Any, Sequence[Tool]],
    ) -> Sequence[Tool]:
        tools = await call_next(context)
        for tool in tools:
            if tool.meta:
                tool.meta = _translate_meta_keys(tool.meta, self._proxy_to_client)
        return tools
