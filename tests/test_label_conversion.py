from __future__ import annotations

from typing import Any

import pytest

from fastmcp.server.middleware import MiddlewareContext
from fastmcp.tools import ToolResult
from mcp.types import CallToolRequestParams, RequestParams

from label_conversion import (
    LabelConversionMiddleware,
    _convert_confidentiality,
    _convert_meta_dict,
    github_to_microsoft,
    microsoft_to_github,
)
from policy_engine import IFC_LABELS_META_PREFIX

# Three of the IDs in ``user_mapping.json`` all map to ``bkoepf``; these
# tests exercise the one-to-many reverse mapping using that user.
BKOEPF_IDS = sorted(
    [
        "a5ec5c13-1974-4ad6-b549-9169907d9e32",
        "c7844335-ebd8-4c3a-8dc9-53e198cea9ba",
        "66a558cd-5c66-41ca-90ae-3fd4b672ff4e",
    ]
)
SZANELLA_ID = "9336459d-7269-40d5-8506-cb314cbfab59"
RISHI_ID = "306c0249-7495-4140-bd5f-f476364a9653"
JUHEE_ID = "4720a62a-62ef-46cb-9d61-e207358cbe46"


# ---------------------------------------------------------------------------
# Pure-helper unit tests
# ---------------------------------------------------------------------------


def test_microsoft_to_github_known_user() -> None:
    assert microsoft_to_github(SZANELLA_ID) == "s-zanella"


def test_microsoft_email_to_github_known_user() -> None:
    assert microsoft_to_github("santiago@projectroma.onmicrosoft.com") == "s-zanella"


def test_microsoft_to_github_unknown_raises() -> None:
    with pytest.raises(KeyError, match="not found"):
        microsoft_to_github("00000000-0000-0000-0000-000000000000")


def test_github_to_microsoft_one_to_many() -> None:
    """A single GitHub handle expands to *all* its Microsoft identities."""
    assert github_to_microsoft("bkoepf") == BKOEPF_IDS


def test_github_to_microsoft_unknown_raises() -> None:
    with pytest.raises(KeyError, match="not found"):
        github_to_microsoft("nope-nobody")


def test_convert_confidentiality_to_github_dedupes_multi_id_handle() -> None:
    """Multiple Microsoft IDs that share a handle collapse to one entry."""
    result = _convert_confidentiality(BKOEPF_IDS + [SZANELLA_ID], "to_github")
    assert result == ["bkoepf", "s-zanella"]


def test_convert_confidentiality_dedupes_user_id_and_email_alias() -> None:
    result = _convert_confidentiality(
        [JUHEE_ID, "current.user@example.com"], "to_github"
    )
    assert result == ["t-juheekim_microsoft"]


def test_convert_confidentiality_to_microsoft_expands_handle() -> None:
    """A GitHub handle expands into all corresponding Microsoft IDs."""
    result = _convert_confidentiality(["bkoepf"], "to_microsoft")
    assert result == BKOEPF_IDS


def test_convert_confidentiality_passes_through_public_sentinel() -> None:
    """The ``"public"`` sentinel is not a principal — never translated."""
    assert _convert_confidentiality(["public"], "to_github") == ["public"]
    assert _convert_confidentiality(["public"], "to_microsoft") == ["public"]


def test_convert_confidentiality_drops_unknown_to_github() -> None:
    """Unknown Microsoft IDs are dropped (fail-closed — shrinks readers)."""
    result = _convert_confidentiality(
        [SZANELLA_ID, "00000000-0000-0000-0000-000000000000"], "to_github"
    )
    assert result == ["s-zanella"]


def test_convert_confidentiality_drops_unknown_to_microsoft() -> None:
    """Unknown GitHub handles are dropped (fail-closed — shrinks readers)."""
    result = _convert_confidentiality(["s-zanella", "ghost-handle"], "to_microsoft")
    assert result == [SZANELLA_ID]


def test_convert_confidentiality_drops_all_unknown_yields_empty() -> None:
    """All-unknown input legitimately produces an empty (most-restrictive) list."""
    assert _convert_confidentiality(["ghost-a", "ghost-b"], "to_github") == []


def test_convert_confidentiality_result_is_sorted() -> None:
    """Output is sorted for stability across runs."""
    result = _convert_confidentiality([RISHI_ID, SZANELLA_ID], "to_github")
    assert result == sorted(result)


def test_convert_confidentiality_unknown_direction_raises() -> None:
    with pytest.raises(ValueError, match="direction"):
        _convert_confidentiality([SZANELLA_ID], "sideways")


# ---------------------------------------------------------------------------
# ``_convert_meta_dict`` — the labels-block walker
# ---------------------------------------------------------------------------


def test_convert_meta_dict_no_labels_block_passes_through() -> None:
    """A ``_meta`` that has no labels block is returned untouched."""
    meta = {"other.prefix": {"foo": "bar"}}
    assert _convert_meta_dict(meta, "to_github") is meta


def test_convert_meta_dict_none_passes_through() -> None:
    assert _convert_meta_dict(None, "to_github") is None
    assert _convert_meta_dict({}, "to_github") == {}


def test_convert_meta_dict_translates_multiple_paths() -> None:
    """Every entry in the labels block (any JSONPath key) is translated."""
    meta = {
        IFC_LABELS_META_PREFIX: {
            "$": {
                "integrity": "trusted",
                "confidentiality": [SZANELLA_ID, RISHI_ID],
            },
            "$['structuredContent']['x']": {
                "integrity": "untrusted",
                "confidentiality": BKOEPF_IDS,
            },
        }
    }
    converted = _convert_meta_dict(meta, "to_github")
    assert converted is not None
    block = converted[IFC_LABELS_META_PREFIX]
    assert block["$"] == {
        "integrity": "trusted",
        "confidentiality": ["rishi-s8", "s-zanella"],
    }
    assert block["$['structuredContent']['x']"] == {
        "integrity": "untrusted",
        "confidentiality": ["bkoepf"],
    }


def test_convert_meta_dict_preserves_extra_meta_keys() -> None:
    """Non-IFC ``_meta`` entries are carried through verbatim."""
    meta = {
        "some.other.prefix": {"k": "v"},
        IFC_LABELS_META_PREFIX: {
            "$": {"integrity": "trusted", "confidentiality": [SZANELLA_ID]},
        },
    }
    converted = _convert_meta_dict(meta, "to_github")
    assert converted is not None
    assert converted["some.other.prefix"] == {"k": "v"}
    assert converted[IFC_LABELS_META_PREFIX]["$"]["confidentiality"] == ["s-zanella"]


def test_convert_meta_dict_does_not_mutate_input() -> None:
    """The original dict (and its nested labels block) is left intact."""
    original_block = {
        "$": {"integrity": "trusted", "confidentiality": [SZANELLA_ID]},
    }
    meta: dict[str, Any] = {IFC_LABELS_META_PREFIX: original_block}
    converted = _convert_meta_dict(meta, "to_github")
    assert meta[IFC_LABELS_META_PREFIX] is original_block
    assert original_block["$"]["confidentiality"] == [SZANELLA_ID]
    assert converted is not None
    assert converted is not meta


def test_convert_meta_dict_leaves_malformed_label_entries_alone() -> None:
    """Entries that aren't ``{integrity, confidentiality}`` dicts pass through."""
    meta = {
        IFC_LABELS_META_PREFIX: {
            "$": "not-a-dict",
            "$['x']": {"integrity": "trusted"},  # no confidentiality
            "$['y']": {
                "integrity": "trusted",
                "confidentiality": [SZANELLA_ID],
            },
        }
    }
    converted = _convert_meta_dict(meta, "to_github")
    assert converted is not None
    block = converted[IFC_LABELS_META_PREFIX]
    assert block["$"] == "not-a-dict"
    assert block["$['x']"] == {"integrity": "trusted"}
    assert block["$['y']"]["confidentiality"] == ["s-zanella"]


# ---------------------------------------------------------------------------
# Middleware integration tests
# ---------------------------------------------------------------------------


def _make_context(
    meta: dict[str, Any] | None = None,
    name: str = "AnyTool",
    arguments: dict[str, Any] | None = None,
) -> MiddlewareContext[CallToolRequestParams]:
    """Build a real :class:`MiddlewareContext` carrying a
    :class:`CallToolRequestParams` message whose ``meta`` is a proper
    :class:`RequestParams.Meta` instance (the middleware asserts on its
    concrete type)."""
    request_meta: RequestParams.Meta | None = (
        RequestParams.Meta.model_validate(meta) if meta is not None else None
    )
    message = CallToolRequestParams.model_construct(
        name=name, arguments=arguments or {}, _meta=request_meta
    )
    return MiddlewareContext(message=message, method="tools/call")


@pytest.mark.anyio
async def test_middleware_translates_result_meta_microsoft_to_github() -> None:
    """Outbound: Microsoft IDs stamped by an upstream/labeler become GitHub handles."""
    middleware = LabelConversionMiddleware()
    context = _make_context()

    async def call_next(_ctx: object) -> ToolResult:
        return ToolResult.model_construct(
            content=[],
            meta={
                IFC_LABELS_META_PREFIX: {
                    "$": {
                        "integrity": "trusted",
                        "confidentiality": [SZANELLA_ID, RISHI_ID, "public"],
                    },
                }
            },
        )

    result = await middleware.on_call_tool(context, call_next)
    assert result.meta is not None
    assert result.meta[IFC_LABELS_META_PREFIX] == {
        "$": {
            "integrity": "trusted",
            "confidentiality": ["public", "rishi-s8", "s-zanella"],
        },
    }


@pytest.mark.anyio
async def test_middleware_translates_request_meta_github_to_microsoft() -> None:
    """Inbound: GitHub handles on a request expand to the matching Microsoft IDs."""
    middleware = LabelConversionMiddleware()
    context = _make_context(
        {
            IFC_LABELS_META_PREFIX: {
                "$['arguments']": {
                    "integrity": "trusted",
                    "confidentiality": ["bkoepf", "s-zanella"],
                },
            }
        }
    )
    captured: dict[str, Any] = {}

    async def call_next(ctx: object) -> ToolResult:
        # The middleware must have rewritten ``params.meta`` in place
        # *before* invoking ``call_next``; capture it for inspection.
        assert context.message.meta is not None
        captured["meta"] = context.message.meta.model_dump(
            by_alias=True, exclude_none=True
        )
        return ToolResult.model_construct(content=[], meta=None)

    await middleware.on_call_tool(context, call_next)
    assert captured["meta"][IFC_LABELS_META_PREFIX] == {
        "$['arguments']": {
            "integrity": "trusted",
            "confidentiality": sorted(BKOEPF_IDS + [SZANELLA_ID]),
        },
    }


@pytest.mark.anyio
async def test_middleware_request_meta_is_request_params_meta_after_rewrite() -> None:
    """After translation the rewritten request meta is still a proper
    ``RequestParams.Meta`` so downstream middleware/proxy code can rely
    on its type."""
    middleware = LabelConversionMiddleware()
    context = _make_context(
        {
            IFC_LABELS_META_PREFIX: {
                "$": {"integrity": "trusted", "confidentiality": ["s-zanella"]},
            }
        }
    )

    async def call_next(_ctx: object) -> ToolResult:
        assert type(context.message.meta) is RequestParams.Meta
        return ToolResult.model_construct(content=[], meta=None)

    await middleware.on_call_tool(context, call_next)


@pytest.mark.anyio
async def test_middleware_no_request_meta_is_a_noop_on_request() -> None:
    """Requests without ``_meta`` flow through unmodified."""
    middleware = LabelConversionMiddleware()
    context = _make_context()  # meta=None

    async def call_next(_ctx: object) -> ToolResult:
        assert context.message.meta is None
        return ToolResult.model_construct(content=[], meta=None)

    result = await middleware.on_call_tool(context, call_next)
    assert result.meta is None


@pytest.mark.anyio
async def test_middleware_no_labels_block_on_result_is_noop() -> None:
    """A result whose ``_meta`` has no IFC labels block is returned untouched."""
    middleware = LabelConversionMiddleware()
    context = _make_context()
    original_meta = {"some.other.prefix": {"foo": "bar"}}

    async def call_next(_ctx: object) -> ToolResult:
        return ToolResult.model_construct(content=[], meta=original_meta)

    result = await middleware.on_call_tool(context, call_next)
    # Same object — no rewrite happened.
    assert result.meta is original_meta


@pytest.mark.anyio
async def test_middleware_drops_unknown_principals_on_result() -> None:
    """Unknown Microsoft IDs are dropped on outbound translation."""
    middleware = LabelConversionMiddleware()
    context = _make_context()

    async def call_next(_ctx: object) -> ToolResult:
        return ToolResult.model_construct(
            content=[],
            meta={
                IFC_LABELS_META_PREFIX: {
                    "$": {
                        "integrity": "trusted",
                        "confidentiality": [
                            SZANELLA_ID,
                            "00000000-0000-0000-0000-000000000000",
                        ],
                    },
                }
            },
        )

    result = await middleware.on_call_tool(context, call_next)
    assert result.meta is not None
    assert result.meta[IFC_LABELS_META_PREFIX]["$"]["confidentiality"] == ["s-zanella"]


@pytest.mark.anyio
async def test_middleware_round_trip_microsoft_to_github_and_back() -> None:
    """MS → GH → MS recovers the original set (modulo handle aliasing)."""
    middleware = LabelConversionMiddleware()
    # Send labels with a handle that expands to multiple IDs; the
    # outbound translation collapses them to one handle, and an inbound
    # round-trip re-expands to the full set — confirming the symmetry
    # of the conversion through the lattice's set semantics.
    context = _make_context(
        {
            IFC_LABELS_META_PREFIX: {
                "$": {"integrity": "trusted", "confidentiality": ["bkoepf"]},
            }
        }
    )

    async def call_next(_ctx: object) -> ToolResult:
        # Echo the (now translated) request meta back as the result meta.
        assert context.message.meta is not None
        echoed = context.message.meta.model_dump(by_alias=True, exclude_none=True)
        return ToolResult.model_construct(content=[], meta=echoed)

    result = await middleware.on_call_tool(context, call_next)
    # Inbound expanded "bkoepf" → all three MS IDs; outbound collapses
    # them back to the single handle.
    assert result.meta is not None
    assert result.meta[IFC_LABELS_META_PREFIX]["$"]["confidentiality"] == ["bkoepf"]


# ---------------------------------------------------------------------------
# eval_policy ``call`` argument: nested-_meta translation
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_middleware_translates_eval_policy_call_arg_meta() -> None:
    """When the call targets ``eval_policy``, GitHub handles inside the
    ``call`` argument's ``_meta`` block are expanded to Microsoft IDs
    before the upstream tool sees them."""
    middleware = LabelConversionMiddleware()
    context = _make_context(
        name="eval_policy",
        arguments={
            "call": {
                "name": "SendMessage",
                "arguments": {"to": "alice"},
                "_meta": {
                    IFC_LABELS_META_PREFIX: {
                        "$['arguments']['to']": {
                            "integrity": "trusted",
                            "confidentiality": ["bkoepf", "s-zanella"],
                        },
                    }
                },
            },
            "policy": "package policy\n",
        },
    )
    captured: dict[str, Any] = {}

    async def call_next(_ctx: object) -> ToolResult:
        assert context.message.arguments is not None
        captured["call"] = context.message.arguments["call"]
        return ToolResult.model_construct(content=[], meta=None)

    await middleware.on_call_tool(context, call_next)
    assert captured["call"]["_meta"][IFC_LABELS_META_PREFIX] == {
        "$['arguments']['to']": {
            "integrity": "trusted",
            "confidentiality": sorted(BKOEPF_IDS + [SZANELLA_ID]),
        },
    }


@pytest.mark.anyio
async def test_middleware_accepts_meta_alias_on_eval_policy_call_arg() -> None:
    """``LabeledToolCallParams`` aliases ``meta`` ↔ ``_meta``
    (``populate_by_name=True``); the middleware tolerates either key."""
    middleware = LabelConversionMiddleware()
    context = _make_context(
        name="eval_policy",
        arguments={
            "call": {
                "name": "SendMessage",
                "arguments": {},
                "meta": {
                    IFC_LABELS_META_PREFIX: {
                        "$": {
                            "integrity": "trusted",
                            "confidentiality": ["s-zanella"],
                        },
                    }
                },
            },
        },
    )

    async def call_next(_ctx: object) -> ToolResult:
        return ToolResult.model_construct(content=[], meta=None)

    await middleware.on_call_tool(context, call_next)
    assert context.message.arguments["call"]["meta"][IFC_LABELS_META_PREFIX]["$"][
        "confidentiality"
    ] == [SZANELLA_ID]


@pytest.mark.anyio
async def test_middleware_does_not_touch_call_arg_for_other_tools() -> None:
    """Only ``eval_policy``'s ``call`` argument is treated specially —
    a same-shaped argument to any other tool is left as-is, because
    other tools don't carry IFC labels at that nesting depth."""
    middleware = LabelConversionMiddleware()
    nested_meta = {
        IFC_LABELS_META_PREFIX: {
            "$": {"integrity": "trusted", "confidentiality": ["s-zanella"]},
        }
    }
    context = _make_context(
        name="SomeOtherTool",
        arguments={
            "call": {
                "name": "Whatever",
                "arguments": {},
                "_meta": nested_meta,
            },
        },
    )

    async def call_next(_ctx: object) -> ToolResult:
        return ToolResult.model_construct(content=[], meta=None)

    await middleware.on_call_tool(context, call_next)
    assert context.message.arguments is not None
    # Unchanged: still the literal GitHub handle, not expanded.
    assert context.message.arguments["call"]["_meta"][IFC_LABELS_META_PREFIX]["$"][
        "confidentiality"
    ] == ["s-zanella"]


@pytest.mark.anyio
async def test_middleware_eval_policy_without_call_arg_is_noop() -> None:
    """Malformed ``eval_policy`` invocations (no ``call`` argument, or
    a non-dict one) must not crash the middleware."""
    middleware = LabelConversionMiddleware()

    async def call_next(_ctx: object) -> ToolResult:
        return ToolResult.model_construct(content=[], meta=None)

    # No ``call`` key at all.
    context = _make_context(name="eval_policy", arguments={"policy": "x"})
    await middleware.on_call_tool(context, call_next)

    # ``call`` present but not a dict.
    context = _make_context(name="eval_policy", arguments={"call": "not-a-dict"})
    await middleware.on_call_tool(context, call_next)

    # ``call`` is a dict but has no ``_meta``.
    context = _make_context(
        name="eval_policy",
        arguments={"call": {"name": "X", "arguments": {}}},
    )
    await middleware.on_call_tool(context, call_next)


@pytest.mark.anyio
async def test_middleware_eval_policy_call_arg_drops_unknown_handles() -> None:
    """Unknown GitHub handles inside the ``call`` argument are dropped,
    consistent with the request- and result-level conversion paths."""
    middleware = LabelConversionMiddleware()
    context = _make_context(
        name="eval_policy",
        arguments={
            "call": {
                "name": "X",
                "arguments": {},
                "_meta": {
                    IFC_LABELS_META_PREFIX: {
                        "$": {
                            "integrity": "trusted",
                            "confidentiality": ["s-zanella", "ghost-handle"],
                        },
                    }
                },
            },
        },
    )

    async def call_next(_ctx: object) -> ToolResult:
        return ToolResult.model_construct(content=[], meta=None)

    await middleware.on_call_tool(context, call_next)
    assert context.message.arguments is not None
    assert context.message.arguments["call"]["_meta"][IFC_LABELS_META_PREFIX]["$"][
        "confidentiality"
    ] == [SZANELLA_ID]
