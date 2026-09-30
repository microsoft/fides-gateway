from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable

from fastmcp import Client
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools import ToolResult
from fastmcp.client.transports.base import ClientTransportT

from mcp.types import CallToolRequestParams

from lattice import IFCLabels, SecurityLattice
from mcp_result import extract_structured_content
from policy_engine import IFC_LABELS_META_PREFIX, LabeledMeta

CallUpstream = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]
"""Async helper passed to labelers that need to call upstream tools.

Signature: ``await call_upstream(tool_name, arguments) -> structured_payload``.
The returned dict is the upstream tool's structured payload, extracted via
:func:`mcp_result.extract_structured_content` (i.e. ``structured_content``
if present, otherwise ``content[0].text`` parsed as JSON).
"""


def _fallback_meta(labels: IFCLabels) -> LabeledMeta:
    """Wrap *labels* as a :class:`LabeledMeta` carrying it as the ``"$"``
    payload-level fallback.

    All current WorkIQ labelers produce a single ``IFCLabels`` for the
    whole result and have no sub-object granularity to express, so they
    attach it at ``"$"`` — the payload-level fallback consulted whenever
    no node-level or ancestor label is available.
    """
    return LabeledMeta(**{IFC_LABELS_META_PREFIX: {"$": labels}})


def _label_from_members(
    members_payload: dict[str, Any] | None, integrity: str
) -> LabeledMeta:
    """Build a :class:`LabeledMeta` whose confidentiality is the
    ``userId`` set of a WorkIQ ``ListChannelMembers``/``ListChatMembers``
    response.

    *members_payload* is expected to be the structured payload of such a
    response (i.e. a dict with a ``"members"`` list of dicts carrying
    ``"userId"``). Missing/non-dict members and missing ``userId`` keys
    are dropped silently. *integrity* is the integrity component of the
    resulting :class:`IFCLabels` — ``"trusted"`` when the roster is the
    payload being labelled, ``"untrusted"`` when the roster is just used
    to scope the audience of an unrelated payload (e.g. chat or channel
    messages). The label is attached at the ``"$"`` payload-level
    fallback.
    """
    members = (members_payload or {}).get("members") or []
    user_ids = [m["userId"] for m in members if isinstance(m, dict) and m.get("userId")]
    return _fallback_meta(IFCLabels(integrity=integrity, confidentiality=user_ids))


class WorkIQLabeling:
    """Labeling functions for WorkIQ MCP tool calls.

    Each ``label<ToolName>`` method takes the tool's input arguments and
    output payload, derives the IFC labels describing the confidentiality
    of the result, and returns a :class:`LabeledMeta` carrying them.

    Current labelers all yield a single :class:`IFCLabels` covering the
    whole result; that label is attached at the ``"$"`` payload-level
    fallback so it applies to every sub-object that doesn't carry a more
    specific label.
    """

    @staticmethod
    def labelListTeams(
        tool_input: dict[str, Any], tool_output: dict[str, Any]
    ) -> LabeledMeta:
        """Label a ``ListTeams`` result.

        Team rosters are treated as non-confidential, so the label is the
        baseline ``integrity=trusted`` with ``confidentiality=public``,
        attached at the ``"$"`` payload-level fallback.
        """
        del tool_input, tool_output
        return _fallback_meta(
            IFCLabels.from_security_lattice(SecurityLattice.default())
        )

    @staticmethod
    def labelListChannels(
        tool_input: dict[str, Any], tool_output: dict[str, Any]
    ) -> LabeledMeta:
        """Label a ``ListChannels`` result.

        Channel listings are treated as non-confidential, so the label is
        the baseline ``integrity=trusted`` with ``confidentiality=public``,
        attached at the ``"$"`` payload-level fallback.
        """
        del tool_input, tool_output
        return _fallback_meta(
            IFCLabels.from_security_lattice(SecurityLattice.default())
        )

    @staticmethod
    def labelListChats(
        tool_input: dict[str, Any], tool_output: dict[str, Any]
    ) -> LabeledMeta:
        """Label a ``ListChats`` result.

        Chat listings are treated as non-confidential, so the label is
        the baseline ``integrity=trusted`` with ``confidentiality=public``,
        attached at the ``"$"`` payload-level fallback.
        """
        del tool_input, tool_output
        # TODO: this returns message previews that may contain confidential info
        # Should be labelled more restrictively.
        return _fallback_meta(
            IFCLabels.from_security_lattice(SecurityLattice.default())
        )

    @staticmethod
    def labelListChannelMembers(
        tool_input: dict[str, Any], tool_output: dict[str, Any]
    ) -> LabeledMeta:
        """Label a ``ListChannelMembers`` result by its members' ``userId``s.

        The resulting :class:`IFCLabels` is attached at the ``"$"``
        payload-level fallback so it applies to the whole result.
        """
        del tool_input  # unused; confidentiality is derived from the output
        return _label_from_members(tool_output, integrity="trusted")

    @staticmethod
    def labelListChatMembers(
        tool_input: dict[str, Any], tool_output: dict[str, Any]
    ) -> LabeledMeta:
        """Label a ``ListChatMembers`` result by its members' ``userId``s.

        The resulting :class:`IFCLabels` is attached at the ``"$"``
        payload-level fallback so it applies to the whole result.
        """
        del tool_input  # unused; confidentiality is derived from the output
        return _label_from_members(tool_output, integrity="trusted")

    @staticmethod
    async def labelListChatMessages(
        tool_input: dict[str, Any],
        tool_output: dict[str, Any],
        call_upstream: CallUpstream,
    ) -> LabeledMeta:
        """Label a ``ListChatMessages`` result by the chat's full member roster.

        The ``ListChatMessages`` response itself does not enumerate
        participants, so we call the upstream ``ListChatMembers`` tool to
        retrieve the roster and use the resulting ``userId``s as the
        confidentiality set. The resulting :class:`IFCLabels` is
        attached at the ``"$"`` payload-level fallback.
        """
        del tool_output  # confidentiality comes from the upstream roster
        chat_id = tool_input.get("chatId")
        if not chat_id:
            raise ValueError("tool_input for ListChatMessages missing required chatId")
        members_payload = await call_upstream("ListChatMembers", {"chatId": chat_id})
        return _label_from_members(members_payload, integrity="untrusted")

    @staticmethod
    async def labelListChannelMessages(
        tool_input: dict[str, Any],
        tool_output: dict[str, Any],
        call_upstream: CallUpstream,
    ) -> LabeledMeta:
        """Label a ``ListChannelMessages`` result by the channel's full member roster.

        The ``ListChannelMessages`` response itself does not enumerate
        participants, so we call the upstream ``ListChannelMembers`` tool to
        retrieve the roster and use the resulting ``userId``s as the
        confidentiality set. The resulting :class:`IFCLabels` is
        attached at the ``"$"`` payload-level fallback.
        """
        del tool_output  # confidentiality comes from the upstream roster
        channel_id = tool_input.get("channelId")
        if not channel_id:
            raise ValueError(
                "tool_input for ListChannelMessages missing required channelId"
            )
        team_id = tool_input.get("teamId")
        if not team_id:
            raise ValueError(
                "tool_input for ListChannelMessages missing required teamId"
            )
        members_payload = await call_upstream(
            "ListChannelMembers", {"teamId": team_id, "channelId": channel_id}
        )
        return _label_from_members(members_payload, integrity="untrusted")


class WorkIQLabellingMiddleware(Middleware):
    """FastMCP middleware that labels tool results from selected WorkIQ
    MCP servers.

    - ``on_call_tool`` stamps every tool result with an ``ifc`` label in
    ``_meta``.

    Labelers may be either sync (``label<Tool>(tool_input, tool_output)``)
    or async (``label<Tool>(tool_input, tool_output, call_upstream)``) and
    return a :class:`LabeledMeta`. Async labelers receive a
    :data:`CallUpstream` helper that issues calls against the same
    upstream MCP server through the configured *upstream_client_factory*.
    This lets a labeler enrich its decision with data that isn't in the
    tool's own response — e.g. ``labelListChatMessages`` calling
    ``ListChatMembers`` to recover the chat's full participant roster.
    """

    def __init__(
        self,
        upstream_client_factory: Callable[[], Client[ClientTransportT]] | None = None,
    ) -> None:
        self._upstream_client_factory = upstream_client_factory

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        result = await call_next(context)
        meta = dict(result.meta) if result.meta else {}

        tool_name = getattr(getattr(context, "message", None), "name", None)
        labeler: Callable[..., LabeledMeta] | None = (
            getattr(WorkIQLabeling, f"label{tool_name}", None) if tool_name else None
        )
        labeled_meta: LabeledMeta | None = None
        if callable(labeler):
            tool_input: dict[str, Any] = (
                getattr(getattr(context, "message", None), "arguments", None) or {}
            )
            try:
                tool_output = extract_structured_content(result)
            except ValueError as e:
                # A tool-specific labeler exists for this tool, but the
                # upstream's response has no usable structured payload.
                # Refuse to label rather than silently fall back to the
                # baseline — falling back could under-label a result that
                # carries sensitive data we just couldn't decode.
                raise ValueError(
                    f"WorkIQLabellingMiddleware: cannot extract structured "
                    f"content from upstream response for tool {tool_name!r}; "
                    f"refusing to label to avoid mislabeling ({e})"
                ) from e
            try:
                if inspect.iscoroutinefunction(labeler):
                    labeled_meta = await self._run_async_labeler(
                        labeler, tool_input, tool_output
                    )
                else:
                    labeled_meta = labeler(tool_input, tool_output)
            except Exception:
                labeled_meta = None
        if labeled_meta is None:
            # No tool-specific labeler (or it failed) — fall back to the
            # default IFC labels (as a "$" payload-level fallback) so
            # every result still carries an ``ifc`` block.
            labeled_meta = _fallback_meta(
                IFCLabels.from_security_lattice(SecurityLattice.default())
            )

        meta[IFC_LABELS_META_PREFIX] = {
            path: labels.model_dump()
            for path, labels in labeled_meta.ifc_labels.items()
        }
        result.meta = meta
        return result

    async def _run_async_labeler(
        self,
        labeler: Callable[..., Awaitable[LabeledMeta]],
        tool_input: dict[str, Any],
        tool_output: dict[str, Any],
    ) -> LabeledMeta:
        """Invoke an async labeler with a :data:`CallUpstream` helper.

        Opens a fresh upstream session from the configured factory and
        exposes a ``call_upstream(name, arguments)`` coroutine that
        forwards to ``session.call_tool`` and returns its structured
        payload via :func:`mcp_result.extract_structured_content`
        (which transparently handles upstreams that ship the payload as
        ``content[0].text`` rather than ``structured_content``). Raises
        ``RuntimeError`` if no factory is configured — async labelers are
        useless without one.
        """
        if self._upstream_client_factory is None:
            raise RuntimeError(
                f"Async labeler {labeler.__qualname__!r} requires an "
                "upstream_client_factory on WorkIQLabellingMiddleware"
            )
        async with self._upstream_client_factory() as session:

            async def call_upstream(
                name: str, arguments: dict[str, Any]
            ) -> dict[str, Any]:
                result = await session.call_tool(name, arguments)
                return extract_structured_content(result)

            return await labeler(tool_input, tool_output, call_upstream)
