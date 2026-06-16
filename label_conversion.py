from __future__ import annotations

import json
import logging
from typing import Any

from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools import ToolResult

from mcp.types import CallToolRequestParams, RequestParams

from lattice import Users
from policy_engine import IFC_LABELS_META_PREFIX

logger = logging.getLogger(__name__)


_user_table: dict[str, dict[str, Any]] | None = None
_reverse_table: dict[str, list[str]] | None = None


def _load_tables() -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    """Load (and cache) the forward and reverse user-mapping tables.

    The forward table maps Microsoft user IDs to their entry in
    ``user_mapping.json`` (which must include a ``github`` field). The
    reverse table maps each GitHub handle to the (one or more) Microsoft
    user IDs that share it.
    """
    global _user_table, _reverse_table

    if _user_table is None or _reverse_table is None:
        with open("user_mapping.json", "r") as f:
            mapping = json.load(f)

        if "users" not in mapping:
            raise ValueError("user_mapping.json is missing 'users' key")
        _user_table = mapping["users"]

        reverse: dict[str, list[str]] = {}
        assert _user_table is not None
        for user_id, entry in _user_table.items():
            if "github" not in entry:
                raise ValueError(f"User entry for {user_id!r} missing 'github' field")
            reverse.setdefault(entry["github"], []).append(user_id)
        for ids in reverse.values():
            ids.sort()
        _reverse_table = reverse

    return _user_table, _reverse_table


def microsoft_to_github(userId: str) -> str:
    """Look up a Microsoft userId in ``user_mapping.json`` and return the GitHub handle.

    Raises ``KeyError`` if the userId is unknown.
    """
    forward, _ = _load_tables()
    if userId not in forward:
        raise KeyError(f"userId {userId!r} not found in user_mapping.json")
    return forward[userId]["github"]


def github_to_microsoft(handle: str) -> list[str]:
    """Return all Microsoft user IDs that map to *handle*.

    Multiple Microsoft identities may share a single GitHub handle (e.g.
    a personal and an admin account); this function returns the full
    list, sorted for stability. Raises ``KeyError`` if the handle is
    unknown.
    """
    _, reverse = _load_tables()
    if handle not in reverse:
        raise KeyError(f"GitHub handle {handle!r} not found in user_mapping.json")
    return list(reverse[handle])


def _convert_confidentiality(confidentiality: list[str], direction: str) -> list[str]:
    """Translate a confidentiality list between Microsoft IDs and GitHub handles.

    *direction* is either ``"to_github"`` (Microsoft → GitHub, used on
    outbound results) or ``"to_microsoft"`` (GitHub → Microsoft, used on
    inbound requests).

    Non-principal sentinels (e.g. :attr:`Users.SENTINEL` == ``"public"``)
    are passed through unchanged. Unknown identifiers are *dropped*:
    removing an authorized reader can only shrink the audience, which
    raises the label in the confidentiality lattice (fewer readers ⇒
    more confidential), and is therefore fail-closed. The resulting
    list is deduplicated and sorted for stability.
    """
    forward, reverse = _load_tables()
    out: set[str] = set()
    for value in confidentiality:
        if value == Users.SENTINEL:
            out.add(value)
            continue
        if direction == "to_github":
            if value in forward:
                out.add(forward[value]["github"])
            else:
                logger.warning(
                    "LabelConversionMiddleware: dropping unknown Microsoft "
                    "user ID %r from confidentiality (no mapping to a "
                    "GitHub handle)",
                    value,
                )
        elif direction == "to_microsoft":
            if value in reverse:
                out.update(reverse[value])
            else:
                logger.warning(
                    "LabelConversionMiddleware: dropping unknown GitHub "
                    "handle %r from confidentiality (no mapping to a "
                    "Microsoft user ID)",
                    value,
                )
        else:
            raise ValueError(f"Unknown conversion direction: {direction!r}")
    return sorted(out)


def _convert_labels_block(
    labels_block: Any, direction: str
) -> dict[str, dict[str, Any]] | None:
    """Translate every ``confidentiality`` list inside an IFC labels block.

    The block is the value at ``_meta[IFC_LABELS_META_PREFIX]``: a
    mapping from JSONPath strings to ``IFCLabels``-shaped dicts. Returns
    a new dict with translated confidentiality lists, or ``None`` if the
    input wasn't a dict (in which case the caller should leave the
    original value untouched).
    """
    if not isinstance(labels_block, dict):
        return None
    converted: dict[str, dict[str, Any]] = {}
    for path, labels in labels_block.items():
        if isinstance(labels, dict) and isinstance(labels.get("confidentiality"), list):
            new_labels = dict(labels)
            new_labels["confidentiality"] = _convert_confidentiality(
                [c for c in labels["confidentiality"] if isinstance(c, str)],
                direction,
            )
            converted[path] = new_labels
        else:
            converted[path] = labels
    return converted


def _convert_meta_dict(
    meta: dict[str, Any] | None, direction: str
) -> dict[str, Any] | None:
    """Return a copy of *meta* with its IFC labels block translated.

    Returns *meta* unchanged (same object) when there is nothing to do,
    so callers can use identity comparison to decide whether to write
    back.
    """
    if not meta or IFC_LABELS_META_PREFIX not in meta:
        return meta
    converted_block = _convert_labels_block(meta[IFC_LABELS_META_PREFIX], direction)
    if converted_block is None:
        return meta
    new_meta = dict(meta)
    new_meta[IFC_LABELS_META_PREFIX] = converted_block
    return new_meta


class LabelConversionMiddleware(Middleware):
    """FastMCP middleware that translates principals in IFC labels between
    Microsoft user IDs (used internally by labelers and policies) and
    GitHub handles (the identity the gateway exposes to clients).

    Labels travel in ``_meta[IFC_LABELS_META_PREFIX]`` as a mapping from
    JSONPath strings to :class:`~lattice.IFCLabels`-shaped dicts; only
    each entry's ``confidentiality`` list is touched (other label
    components pass through). The translation is symmetric:

    - **Inbound (GitHub → Microsoft), before** ``call_next`` so downstream
      middleware and any Rego policy evaluated by ``eval_policy`` see
      Microsoft user IDs. Rewriting happens at **two** distinct sites on
      the request:

      1. ``params.meta`` — the request's top-level
         ``_meta[IFC_LABELS_META_PREFIX]``, used by callers to attach
         labels to ``input.name`` / ``input.arguments`` of the tool call
         itself.
      2. ``params.arguments['call']['_meta']`` — the labels nested
         *inside* the ``call`` argument when the request targets the
         gateway-registered ``eval_policy`` tool, whose ``call``
         parameter is a wire-shaped
         :class:`policy_engine.LabeledToolCallParams`. Both ``_meta``
         and the Pydantic-alias-equivalent ``meta`` key are tolerated
         (see :meth:`_translate_eval_policy_call_arg`).

    - **Outbound (Microsoft → GitHub), after** ``call_next``: rewrites
      ``result.meta[IFC_LABELS_META_PREFIX]`` so clients only ever see
      GitHub handles on the wire.

    Both directions delegate to :func:`_convert_meta_dict`, which is a
    no-op (returns the same object) when the meta has no labels block,
    letting callers skip the write-back via identity comparison.

    **Sentinels and unknown principals.** The non-principal sentinel
    :attr:`Users.SENTINEL` (``"public"``) is passed through unchanged in
    both directions. Identifiers that aren't in ``user_mapping.json``
    are **dropped** with a warning — this is deliberately fail-closed:
    removing an authorized reader can only shrink the audience of a
    payload, which monotonically raises its label in the
    confidentiality lattice (fewer readers ⇒ more confidential), so a
    dropped identifier never widens access.
    """

    # Name of the gateway-registered policy-evaluation tool whose ``call``
    # argument is a :class:`policy_engine.LabeledToolCallParams` carrying
    # its own ``_meta[IFC_LABELS_META_PREFIX]`` (see
    # :meth:`fastmcp_proxy.MCPGateway._register_eval_policy`).
    _EVAL_POLICY_TOOL_NAME = "eval_policy"

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        params = context.message
        if getattr(params, "meta", None) is not None:
            assert (
                type(params.meta) is RequestParams.Meta
            ), "Unexpected _meta parameter type"
            meta_dict = params.meta.model_dump(by_alias=True, exclude_none=True)
            translated = _convert_meta_dict(meta_dict, "to_microsoft")
            if translated is not meta_dict:
                params.meta = type(params.meta).model_validate(translated)

        if getattr(params, "name", None) == self._EVAL_POLICY_TOOL_NAME:
            self._translate_eval_policy_call_arg(params)

        result = await call_next(context)
        converted_result_meta = _convert_meta_dict(result.meta, "to_github")
        if converted_result_meta is not result.meta:
            result.meta = converted_result_meta
        return result

    @staticmethod
    def _translate_eval_policy_call_arg(params: CallToolRequestParams) -> None:
        """Translate labels embedded in ``eval_policy``'s ``call`` argument.

        The ``call`` argument is a wire-shaped
        :class:`policy_engine.LabeledToolCallParams` whose IFC labels
        live at ``call._meta[IFC_LABELS_META_PREFIX]`` (with ``meta``
        accepted as an alias-equivalent key per Pydantic's
        ``populate_by_name``). Rewrites the labels in place on
        ``params.arguments`` so that downstream policy evaluation sees
        Microsoft user IDs.
        """
        arguments = getattr(params, "arguments", None)
        if not isinstance(arguments, dict):
            return
        call_arg = arguments.get("call")
        if not isinstance(call_arg, dict):
            return
        # ``LabeledToolCallParams`` aliases ``meta`` to ``_meta`` with
        # ``populate_by_name=True``; tolerate either key on the wire.
        for meta_key in ("_meta", "meta"):
            inner_meta = call_arg.get(meta_key)
            if not isinstance(inner_meta, dict):
                continue
            translated = _convert_meta_dict(inner_meta, "to_microsoft")
            if translated is not inner_meta:
                call_arg[meta_key] = translated
