from __future__ import annotations

import json
from typing import Any

from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools import ToolResult
from mcp.types import CallToolRequestParams, TextContent

from lattice import IFCLabels
from policy_engine import IFC_LABELS_META_PREFIX

_TRUSTED_METADATA_FIELDS = {
    "additions",
    "ahead_by",
    "author_association",
    "behind_by",
    "changed_files",
    "closed",
    "comments",
    "commits",
    "created",
    "databaseid",
    "deletions",
    "forks",
    "id",
    "incomplete_results",
    "locked",
    "maintainer_can_modify",
    "mergeable",
    "merged",
    "number",
    "open_issues",
    "private",
    "public",
    "score",
    "size",
    "state",
    "status",
    "total",
    "total_count",
    "updated",
    "watchers",
}

_TRUSTED_METADATA_CONTAINERS = {
    "permissions",
    "reactions",
}

_TRUSTED_METADATA_SUFFIXES = (
    "_at",
    "_count",
    "_id",
    "_url",
)

_TRUSTED_METADATA_NAMES = {
    "etag",
    "git_url",
    "html_url",
    "node_id",
    "sha",
    "ssh_url",
    "svn_url",
    "url",
}


def _labels(integrity: str) -> IFCLabels:
    # Repository visibility and membership are not available in every tool
    # result, so confidentiality remains fail-closed until an audience-aware
    # GitHub policy widens it.
    return IFCLabels(integrity=integrity, confidentiality=[])


def _path(parent: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{parent}[{key}]"
    escaped = key.replace("\\", "\\\\").replace("'", "\\'")
    return f"{parent}['{escaped}']"


def _is_trusted_metadata(
    field: str | None, value: Any, trusted_container: bool
) -> bool:
    if trusted_container:
        return True
    if field is None:
        return False
    normalized = field.lower()
    return (
        normalized in _TRUSTED_METADATA_FIELDS
        or normalized in _TRUSTED_METADATA_NAMES
        or normalized.endswith(_TRUSTED_METADATA_SUFFIXES)
        or normalized.startswith(("has_", "is_"))
        or normalized.endswith("_sha")
        or isinstance(value, bool)
    )


def _label_payload(
    value: Any,
    path: str,
    labels: dict[str, IFCLabels],
    field: str | None = None,
    trusted_container: bool = False,
) -> None:
    current_trusted = _is_trusted_metadata(field, value, trusted_container)
    if isinstance(value, dict):
        if not value:
            labels[path] = _labels("trusted" if current_trusted else "untrusted")
            return
        child_trusted = current_trusted or (
            field is not None and field.lower() in _TRUSTED_METADATA_CONTAINERS
        )
        for key, child in value.items():
            _label_payload(
                child,
                _path(path, key),
                labels,
                key,
                child_trusted,
            )
        return
    if isinstance(value, list):
        if not value:
            labels[path] = _labels("trusted" if current_trusted else "untrusted")
            return
        for index, child in enumerate(value):
            _label_payload(
                child,
                _path(path, index),
                labels,
                field,
                current_trusted,
            )
        return
    labels[path] = _labels("trusted" if current_trusted else "untrusted")


def _github_payload(result: ToolResult) -> dict[str, Any] | None:
    if result.structured_content is not None:
        return result.structured_content
    if not result.content or not isinstance(result.content[0], TextContent):
        return None
    try:
        parsed = json.loads(result.content[0].text)
    except json.JSONDecodeError:
        return None
    payload = parsed if isinstance(parsed, dict) else {"result": parsed}
    result.structured_content = payload
    return payload


class GitHubLabellingMiddleware(Middleware):
    """Label GitHub-controlled metadata as trusted and all other data as untrusted."""

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next: CallNext[CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        result = await call_next(context)
        labels: dict[str, IFCLabels] = {"$": _labels("untrusted")}
        payload = _github_payload(result)
        if payload is not None:
            _label_payload(payload, "$['structuredContent']", labels)

        meta = dict(result.meta) if result.meta else {}
        meta[IFC_LABELS_META_PREFIX] = {
            path: label.model_dump() for path, label in labels.items()
        }
        result.meta = meta
        return result
