"""Rego policy evaluation against labelled MCP tool calls.

This module owns the policy-evaluation half of the gateway: the
wire-level Pydantic models for a labelled tool call
(:class:`LabeledToolCallParams`, :class:`LabeledMeta`) and the
symmetric (currently unused) result-side model
(:class:`LabeledToolResult`), the path parser and canonicalizer used to
address sub-objects of ``input``, the effective-label resolver
(:func:`_make_label_extension`), and :func:`eval_policy` itself.

Keeping this layer separate from the FastMCP proxy plumbing in
:mod:`fastmcp_proxy` lets policy-evaluation logic be reused and tested
independently of the gateway wiring.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

import jsonpath_rfc9535
import regorus
from mcp.types import ContentBlock
from jsonpath_rfc9535.selectors import IndexSelector, NameSelector
from jsonpath_rfc9535.serialize import canonical_string
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from fastmcp import Client
from fastmcp.client.transports.base import ClientTransportT


from lattice import IFCLabels, join_label_dicts, labels_equal
from mcp_result import extract_structured_content

IFC_LABELS_META_PREFIX = "com.github.ifc/labels"


class LabeledMeta(BaseModel):
    """The ``_meta`` field of a labelled MCP payload.

    Used both for request payloads (e.g. ``CallToolRequestParams``) and
    for result payloads (e.g. ``CallToolResult``): it carries the
    gateway-specific ``IFC_LABELS_META_PREFIX`` mapping plus any
    metadata the caller chose to attach (``extra="allow"``). The
    mapping keys are
    `RFC 9535 <https://www.rfc-editor.org/rfc/rfc9535>`_ JSONPath
    singular-query strings rooted at the payload — ``"$"`` (the
    payload-level fallback, equivalently the root node ``input``),
    plus keys addressing any sub-object reachable from it
    (e.g. ``"$['name']"``, ``"$['arguments']['foo']"``,
    ``"$['structuredContent']['x']"``, ``"$['content'][0]"``) — and
    the values are :class:`~lattice.IFCLabels`.

    The ``"$"`` entry, when present, is the *payload-level fallback*:
    it is returned when a queried path has no explicit, no implicit
    (descendants-lub), and no ancestor effective label. It is *not*
    required to upper-bound the labels of any specific sub-object on
    its own.

    No single entry is required at the Pydantic level. The stricter
    requirement — that the payload's designated *root nodes* each end
    up with a resolvable effective label — is payload-specific and is
    enforced when the :func:`label` extension is built (see
    :func:`_build_effective_labels`). For a labelled tool-call request
    the required roots are ``$['name']`` and ``$['arguments']``; for a
    labelled tool-call result the required root is
    ``$['structuredContent']``.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    ifc_labels: dict[str, IFCLabels] = Field(
        alias=IFC_LABELS_META_PREFIX,
        description=(
            "Mapping of RFC 9535 JSONPath string (e.g. '$', \"$['name']\","
            " \"$['arguments']\", \"$['arguments']['foo']\","
            " \"$['arguments']['foo']['bar']\","
            " \"$['arguments']['items'][0]\","
            " \"$['structuredContent']['x']\") to the IFC labels"
            " attached at that location. Only singular-path JSONPath"
            " queries are accepted; wildcards, descendant segments,"
            " slices, filters, and multi-selector segments are"
            " rejected. Keys may be given in any equivalent singular"
            " form (e.g. '$.arguments.foo' and"
            " \"$['arguments']['foo']\" refer to the same node) and"
            " are normalized to RFC 9535 Normalized Path form. The '$'"
            " key is the payload-level fallback. The payload's"
            " designated root nodes (e.g. $['name'] and $['arguments']"
            " for a tool-call request, $['structuredContent'] for a"
            " tool-call result) must each end up with a resolvable"
            " effective label (explicit, descendants-derived, or via"
            " the '$' fallback)."
        ),
    )


class LabeledToolCallParams(BaseModel):
    """An MCP ``CallToolRequestParams`` augmented with IFC labels in ``_meta``.

    Mirrors :class:`mcp.types.CallToolRequestParams` so an existing client
    can hand it straight through. Labels travel as
    ``_meta[IFC_LABELS_META_PREFIX]``, keyed by RFC 9535 JSONPath strings
    rooted at the call (see
    :class:`LabeledMeta`).
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(description="The name of the MCP tool to be called.")
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description=("Mapping of argument name to its raw value."),
    )
    meta: LabeledMeta | None = Field(
        alias="_meta",
        description=(
            "Per-MCP-spec request metadata. Must carry "
            f"'{IFC_LABELS_META_PREFIX}' so that an effective label can be "
            "resolved for 'name' and 'arguments'."
        ),
    )


class LabeledToolResult(BaseModel):
    """An MCP ``CallToolResult`` augmented with IFC labels in ``_meta``.

    Mirrors :class:`mcp.types.CallToolResult` so an existing client can
    consume it directly. Labels travel as
    ``_meta[IFC_LABELS_META_PREFIX]``, keyed by RFC 9535 JSONPath strings
    rooted at the result (see :class:`LabeledMeta`).

    .. note::

       Currently unused at runtime: the gateway only *stamps*
       (:class:`workiq_labeller.WorkIQLabellingMiddleware`) and
       *translates* (:class:`label_conversion.LabelConversionMiddleware`)
       result-side labels on raw ``_meta`` dicts, and never parses an
       upstream result back into a Pydantic model. This class is kept
       to document the labelled-result wire shape — symmetric with
       :class:`LabeledToolCallParams` — for clients and tests that want
       to validate it, and as a ready-made input for
       :func:`_build_effective_labels` should a result-label validation
       middleware be added.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    content: list[ContentBlock] = Field(
        default_factory=list,
        description=("The unstructured content blocks returned by the tool call."),
    )
    structured_content: dict[str, Any] | None = Field(
        default=None,
        alias="structuredContent",
        description=(
            "An optional JSON object that represents the structured result"
            " of the tool call."
        ),
    )
    is_error: bool = Field(
        default=False,
        alias="isError",
        description=(
            "Whether the tool call resulted in an error (as reported by"
            " the upstream server)."
        ),
    )
    meta: LabeledMeta | None = Field(
        alias="_meta",
        description=(
            "Per-MCP-spec result metadata. Must carry "
            f"'{IFC_LABELS_META_PREFIX}' so that an effective label can be "
            "resolved for the result payload."
        ),
    )


def _parse_jsonpath_key(s: str) -> list[str | int]:
    """Parse an RFC 9535 JSONPath singular-query string into a segment list.

    Used both for the keys of ``_meta[IFC_LABELS_META_PREFIX]`` and for
    the string argument of the ``ifc.label("…")`` Rego extension. Accepts
    any RFC 9535 JSONPath query that resolves to a single node — i.e.
    one whose segments are all child segments with exactly one
    name-selector or index-selector. Non-singular queries (wildcards,
    descendant segments, slices, filters, multi-selector segments) are
    rejected, as are non-JSONPath strings that lack the ``$`` root.
    Examples::

        "$"                                  -> []
        "$['name']"                          -> ["name"]
        "$.name"                             -> ["name"]
        "$['arguments']['foo']"              -> ["arguments", "foo"]
        "$.arguments.foo"                    -> ["arguments", "foo"]
        "$['arguments']['items'][0]"         -> ["arguments", "items", 0]
        '$.arguments["items"][0].v'          -> ["arguments", "items", 0, "v"]
        "$['arguments']['items'][0]['v']"    -> ["arguments", "items", 0, "v"]
    """
    try:
        query = jsonpath_rfc9535.compile(s)
    except jsonpath_rfc9535.JSONPathError as e:
        raise ValueError(f"Invalid JSONPath key {s!r}: {e}") from e
    if not query.singular_query():
        raise ValueError(
            f"ifc key {s!r} is not a singular JSONPath (wildcards, "
            "descendant segments, slices, filters, and multi-selector "
            "segments are not allowed)"
        )
    segments: list[str | int] = []
    for seg in query.segments:
        # ``singular_query`` guarantees a single name- or index-selector per
        # child-segment.
        sel = seg.selectors[0]
        if isinstance(sel, NameSelector):
            segments.append(sel.name)
        elif isinstance(sel, IndexSelector):
            segments.append(sel.index)
        else:  # pragma: no cover - defensive; singular_query excludes others
            raise ValueError(
                f"ifc key {s!r}: unsupported selector " f"{type(sel).__name__}"
            )
    return segments


def _jsonpath_normalize(segments: list[str | int]) -> str:
    """Format *segments* as an RFC 9535 Normalized Path string.

    Name segments are bracketed with single-quoted, escaped strings;
    integer segments are bracketed without quotes; the empty segment
    list (``input`` itself, used as the call-level fallback label key
    in ``ifc``) normalizes to ``"$"``::

        []                                  -> "$"
        ["name"]                            -> "$['name']"
        ["arguments"]                       -> "$['arguments']"
        ["arguments", "foo"]                -> "$['arguments']['foo']"
        ["arguments", "items", 0]           -> "$['arguments']['items'][0]"
        ["arguments", "items", 0, "v"]      -> "$['arguments']['items'][0]['v']"
    """
    parts = ["$"]
    for seg in segments:
        if isinstance(seg, int):
            parts.append(f"[{seg}]")
        else:
            parts.append(f"[{canonical_string(seg)}]")
    return "".join(parts)


def _canonicalize_labels(labels: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *labels* with every key rewritten to canonical form.

    Keys must be RFC 9535 JSONPath singular-query strings rooted at
    ``$``. Different equivalent spellings (``$.arguments.foo`` and
    ``$['arguments']['foo']``) are accepted and normalized to a single
    canonical Normalized Path key (``$['arguments']['foo']``). If two
    distinct input keys canonicalize to the same path with conflicting
    values, that's an ambiguous label and we fail loudly.
    """
    canonical: dict[str, Any] = {}
    for raw_key, value in labels.items():
        segments = _parse_jsonpath_key(raw_key)
        key = _jsonpath_normalize(segments)
        if key in canonical and not labels_equal(canonical[key], value):
            raise ValueError(
                f"{IFC_LABELS_META_PREFIX}: duplicate label entries for path {key!r} "
                f"(from {raw_key!r}) with conflicting values"
            )
        canonical[key] = value
    return canonical


def _build_effective_labels(
    roots: dict[str, Any], labels: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Walk the payload bottom-up and compute the effective label of every node.

    *roots* is a mapping from the canonical JSONPath (in RFC 9535
    Normalized Path form, e.g. ``"$['name']"``, ``"$['arguments']"``,
    ``"$['structuredContent']"``) of each *root node* the caller wants
    visited to the corresponding subtree value. The bottom-up traversal
    starts independently at each root; the synthetic payload root
    (canonical path ``"$"``) is *not* traversed because its label, if
    any, lives in ``labels["$"]`` purely as a fallback.

    The effective label of a node is:

    - its explicit label, if one is attached at the node's canonical path; or
    - the join (lub) of its descendants' effective labels (an array's label
      is the lub over its elements; a dict's label is the lub over its
      entries); or
    - omitted from the returned map if the subtree carries no labels at all.

    The payload-level fallback (``labels["$"]``, attached to ``input``
    itself) is *not* part of the bottom-up traversal — it is a fallback
    consulted only when no node-level or ancestor label is available, and
    it is explicitly **not** required to upper-bound the labels of any
    specific root node.

    Two restrictions are enforced and raise ``ValueError`` on violation:

    1. *Well-formedness.* At every node that carries an explicit label, the
       label must be above (≥) the lub of its descendants' effective labels
       in the lattice. Equivalently,
       ``join(explicit, descendants_lub) == explicit``.
    2. *Total coverage.* Every root in *roots* must end up with an
       effective label. That can be supplied by an explicit label at the
       root's path, an implicit (descendants-lub) label, or the
       payload-level fallback at ``"$"``. Without one of these, policy
       evaluation has no label to hand back, so we fail at construction
       time rather than at query time.
    """
    effective: dict[str, dict[str, Any]] = {}

    def visit(value: JsonValue, canonical_path: str | None) -> dict[str, Any] | None:
        descendants_lub: dict[str, Any] | None = None
        if isinstance(value, dict):
            for k, v in value.items():
                assert isinstance(k, str), "JSON object keys are always strings"
                sub = (
                    f"{canonical_path}[{canonical_string(k)}]"
                    if canonical_path is not None
                    else None
                )
                child = visit(v, sub)
                if child is not None:
                    descendants_lub = (
                        child
                        if descendants_lub is None
                        else join_label_dicts(descendants_lub, child)
                    )
        elif isinstance(value, list):
            for idx, v in enumerate(value):
                sub = f"{canonical_path}[{idx}]" if canonical_path is not None else None
                child = visit(v, sub)
                if child is not None:
                    descendants_lub = (
                        child
                        if descendants_lub is None
                        else join_label_dicts(descendants_lub, child)
                    )

        explicit = labels.get(canonical_path) if canonical_path is not None else None
        if explicit is not None:
            if descendants_lub is not None:
                if not labels_equal(
                    join_label_dicts(explicit, descendants_lub), explicit
                ):
                    raise ValueError(
                        f"Inconsistent label at {canonical_path!r}: explicit "
                        f"label {explicit!r} is not above the join of its "
                        f"descendants' labels {descendants_lub!r}"
                    )
            node_effective: dict[str, Any] | None = explicit
        else:
            node_effective = descendants_lub

        if canonical_path is not None and node_effective is not None:
            effective[canonical_path] = node_effective
        return node_effective

    for root_path, root_value in roots.items():
        visit(root_value, root_path)

    # Total-coverage check: every queryable path needs *some* resolvable
    # label, and the resolver bottoms out at either an ancestor effective
    # label or the ``"$"`` fallback. So every root in *roots* must have an
    # effective label, OR ``labels`` must provide the ``"$"`` fallback.
    has_fallback = "$" in labels
    for required in roots:
        if required not in effective and not has_fallback:
            raise ValueError(
                f"{IFC_LABELS_META_PREFIX}: {required!r} has no effective label (no explicit "
                "label, no labelled descendants) and no payload-level fallback "
                "label ('$' entry) is provided"
            )
    return effective


def _resolve_effective_label(
    segments: list[str | int],
    labels: dict[str, Any],
    effective: dict[str, dict[str, Any]],
    diagnostic: str,
) -> Any:
    """Apply the four-rule effective-label resolution to *segments*.

    Called by the ``ifc.label("<jsonpath>")`` Rego extension. *labels* must
    already be canonicalized; *effective* is the map built by
    :func:`_build_effective_labels`. *diagnostic* is the textual call
    (e.g. ``ifc.label("$['arguments']['x']")``) used in the error message
    if resolution fails — only reachable for unusual queries when no
    call-level fallback is configured.
    """
    canonical = _jsonpath_normalize(segments)
    # Rules 1 + 2: explicit-at-path or implicit-from-descendants.
    if canonical in effective:
        return effective[canonical]
    # Orphan explicit label (path doesn't exist in the call but a label
    # was attached for it anyway). Also covers queries for the empty
    # path when the call-level fallback is queried directly.
    if canonical in labels:
        return labels[canonical]
    # Rule 3: nearest ancestor that has any effective label — either an
    # explicit one or one computed as the lub of its descendants. The
    # effective map already captures both, so consult it here so an
    # unlabelled descendant of an implicitly-labelled container picks
    # up the container's lub.
    for end in range(len(segments) - 1, 0, -1):
        ancestor = _jsonpath_normalize(segments[:end])
        if ancestor in effective:
            return effective[ancestor]
    # Rule 4: call-level fallback at ``"$"`` (i.e. ``input`` itself).
    # Guaranteed to be available by the total-coverage check in
    # ``_build_effective_labels`` for any path under ``name`` /
    # ``arguments`` that didn't hit an earlier rule.
    if "$" in labels:
        return labels["$"]
    raise ValueError(
        f"{diagnostic} failed: no effective label resolvable and no "
        "call-level fallback ('$' entry) provided"
    )


def _make_label_extension(
    call: dict[str, Any], labels: dict[str, Any]
) -> Callable[[Any], Any]:
    """Build the ``ifc.label`` Rego extension for :func:`eval_policy`.

    The returned callable accepts an RFC 9535 JSONPath singular-query
    string — the same syntax used to key labels in
    ``_meta[IFC_LABELS_META_PREFIX]`` — and resolves its *effective*
    IFC label as follows:

    1. If an explicit label is attached at the queried path, return it.
    2. Otherwise, return the implicit label of the node — the join of the
       effective labels of all descendants (a dict's label is the lub over
       its entries; an array's label is the lub over its elements).
    3. Otherwise (neither the queried node nor any of its descendants
       carry an explicit label), walk up the ancestor chain and return
       the effective label of the nearest ancestor that has one. An
       ancestor's effective label may itself be implicit (lub-derived),
       so this propagates container-level taint down to unlabelled
       siblings/descendants of labelled subtrees.
    4. As a final fallback, return the call-level label attached at
       ``"$"`` (i.e. ``input`` itself). This fallback is *not*
       required to upper-bound the labels of ``name`` or ``arguments``;
       it is consulted only when no node- or ancestor-level label is
       available.

    The JSONPath argument is rooted at ``input``: ``$`` denotes the
    call as a whole, and ``$['name']`` and ``$['arguments']`` are its
    only children. The argument is parsed by :func:`_parse_jsonpath_key`
    and then normalized to the same canonical key used to store labels.

    See :func:`_build_effective_labels` for the construction-time checks
    (well-formedness of explicit labels and total coverage of ``name`` /
    ``arguments``).
    """
    labels = _canonicalize_labels(labels)
    roots: dict[str, Any] = {
        "$['name']": call.get("name"),
        "$['arguments']": call.get("arguments") or {},
    }
    effective = _build_effective_labels(roots, labels)

    def ifc_label(path: Any) -> Any:
        if not isinstance(path, str):
            raise ValueError(
                f"ifc.label() expects a JSONPath string, got {type(path).__name__}"
            )
        segments = _parse_jsonpath_key(path)
        return _resolve_effective_label(
            segments, labels, effective, f"ifc.label({path!r})"
        )

    return ifc_label


def _make_upstream_extension(
    session: Client[ClientTransportT],
    tool_name: str,
    loop: asyncio.AbstractEventLoop,
) -> Callable[[Any], Any]:
    """Build a synchronous Rego extension that calls *tool_name* on *session*.

    Rego calls extensions synchronously, but MCP tool calls are async. The
    returned callable receives the policy's single dict argument, schedules
    the corresponding ``session.call_tool(...)`` coroutine on *loop* via
    :func:`asyncio.run_coroutine_threadsafe`, blocks on the result, and
    returns the tool's structured payload as a plain dict (via
    :func:`mcp_result.extract_structured_content`, which falls back to
    parsing ``content[0].text`` as JSON when the upstream does not set
    ``structured_content``) so regorus can convert it back into a Rego
    value.
    """

    def call_tool(args: dict[str, Any]) -> Any:
        future = asyncio.run_coroutine_threadsafe(
            session.call_tool(tool_name, args), loop
        )
        result = future.result()
        try:
            return extract_structured_content(result)
        except ValueError as exc:
            raise ValueError(
                f"Failed to extract structured content from upstream tool "
                f"{tool_name!r}"
            ) from exc

    return call_tool


async def eval_policy(
    call: dict[str, Any],
    policy: str,
    upstream_client: Client[ClientTransportT] | None = None,
    *,
    server_info: dict[str, Any] | None = None,
    query: str | None = None,
) -> Any:
    """Evaluate a Rego *policy* against a labelled MCP tool *call*.

    The call's ``name`` and ``arguments`` are exposed to Rego as
    ``input.name`` and ``input.arguments`` (flattened — there is no
    ``input.call`` wrapper). A single ``ifc.label("<jsonpath>")`` Rego
    extension is registered, which resolves the *effective* IFC label
    of any sub-object of ``input``. The path is an RFC 9535 JSONPath
    singular-query string rooted at ``$`` (e.g. ``"$['name']"``,
    ``"$.arguments.foo"``, ``"$['arguments']['items'][0]"``). See
    :func:`_make_label_extension` for the four-rule resolution
    semantics (explicit, descendants-lub, nearest ancestor, call-level
    fallback at ``"$"``).

    The extension takes a literal string, but Rego's
    :func:`sprintf` can render a JSONPath from runtime values when a
    policy needs to resolve a label at a dynamic path::

        field := "to"
        l := ifc.label(sprintf("$.arguments.%s", [field]))

    The extension is built from the labels carried in
    ``call["_meta"][IFC_LABELS_META_PREFIX]`` (a mapping of RFC 9535
    JSONPath singular-query string to IFC label dict). Keys may be
    supplied in any equivalent singular JSONPath form
    (``"$.arguments.foo"`` and ``"$['arguments']['foo']"`` are
    accepted as the same key) and are canonicalized internally.

    If *upstream_client* is provided, each upstream tool is also exposed
    to the policy as the extension ``upstream.<ToolName>(args)``.

    If *server_info* is provided, it is exposed to the policy as the
    arity-0 extension ``upstream.serverInfo()`` returning the dict (the
    upstream MCP server's :class:`mcp.types.Implementation`: ``name``,
    ``title``, ``version``, ``websiteUrl``, ``icons``). ``None`` is also
    accepted and surfaces to the policy as Rego null, signalling that
    the upstream identity has not been captured yet.

    If *query* is provided, that Rego expression is evaluated and its
    raw value is returned (e.g. ``"data.example.allow"`` returns the
    boolean rule value). If *query* is ``None`` (the default — the
    gateway's production convention), the engine evaluates ``data`` and
    returns the ``policy`` sub-key, i.e. the result of the ``package
    policy`` block.
    """
    policy_input: dict[str, Any] = {
        "name": call["name"],
        "arguments": call["arguments"],
    }
    meta: dict[str, Any] = call.get("_meta") or {}
    labels: dict[str, dict[str, Any]] = meta.get(IFC_LABELS_META_PREFIX) or {}
    base_extensions: dict[str, tuple[int, Callable[..., Any]]] = {
        "ifc.label": (1, _make_label_extension(call, labels)),
    }
    # Always register ``upstream.serverInfo()`` so the policy can call it
    # unconditionally; the closure captures ``server_info`` so a ``None``
    # cache surfaces to Rego as null.
    captured_server_info = server_info

    def _server_info_ext() -> Any:
        return captured_server_info

    base_extensions["upstream.serverInfo"] = (0, _server_info_ext)

    if upstream_client is None:
        return await asyncio.to_thread(
            _run_policy_sync, policy_input, policy, base_extensions, query
        )

    loop = asyncio.get_running_loop()
    async with upstream_client as session:
        tools = await session.list_tools()
        extensions: dict[str, tuple[int, Callable[..., Any]]] = {
            **base_extensions,
            **{
                f"upstream.{tool.name}": (
                    1,
                    _make_upstream_extension(session, tool.name, loop),
                )
                for tool in tools
            },
        }
        return await asyncio.to_thread(
            _run_policy_sync, policy_input, policy, extensions, query
        )


def _run_policy_sync(
    policy_input: dict[str, Any],
    policy: str,
    extensions: dict[str, tuple[int, Callable[..., Any]]],
    query: str | None = None,
) -> Any:
    """Configure a fresh ``regorus.Engine`` and evaluate *policy*.

    Runs synchronously; intended to be invoked from
    :func:`asyncio.to_thread` so the extension callbacks can block on
    :func:`asyncio.run_coroutine_threadsafe` without stalling the event
    loop.

    If *query* is ``None``, evaluates ``data`` and returns the
    ``policy`` sub-key (the gateway's production convention). If
    *query* is given, evaluates that expression and returns its raw
    value.
    """
    engine = regorus.Engine()  # pyright: ignore[reportAttributeAccessIssue]
    for path, (arity, fn) in extensions.items():
        engine.add_extension(path, arity, fn)
    engine.add_policy("policy.rego", policy)
    engine.set_input(policy_input)
    if query is None:
        result = engine.eval_query("data")
        value = result["result"][0]["expressions"][0]["value"]
        return value["policy"]
    result = engine.eval_query(query)
    return result["result"][0]["expressions"][0]["value"]
